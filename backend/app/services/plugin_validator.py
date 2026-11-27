from __future__ import annotations
import hashlib
import io
import json
import posixpath
import re
import tarfile
from dataclasses import dataclass, field
from pathlib import PurePosixPath
from typing import Any, Dict, List

MAX_PLUGIN_TGZ_BYTES = 20 * 1024 * 1024  # 20 MB

PACKAGE_NAME_RE = re.compile(r"^@rgone/[a-z0-9][a-z0-9._-]{0,120}$")
SEMVER_RE = re.compile(
    r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)"
    r"(?:-[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?"
    r"(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?$"
)
LIFECYCLE_SCRIPT_KEYS = {
    "preinstall",
    "install",
    "postinstall",
    "preuninstall",
    "uninstall",
    "postuninstall",
    "prepare",
}


class PluginValidationError(ValueError):
    """插件包结构或安全校验异常"""


@dataclass
class ValidatedPluginPackage:
    name: str
    version: str
    description: str
    sha256: str
    size_bytes: int
    package_json: Dict[str, Any]
    has_lifecycle_scripts: bool = False
    detected_scripts: List[str] = field(default_factory=list)


def validate_package_name(name: str) -> str:
    cleaned = (name or "").strip()
    if not PACKAGE_NAME_RE.match(cleaned):
        raise PluginValidationError("插件包名必须符合 @rgone/<lowercase-name> 规范")
    return cleaned


def validate_semver(version: str) -> str:
    cleaned = (version or "").strip()
    if not SEMVER_RE.match(cleaned):
        raise PluginValidationError("版本号必须符合标准 SemVer 规范（例如 1.0.0）")
    return cleaned


def _validate_tar_member_safe(member: tarfile.TarInfo) -> str:
    if member.issym() or member.islnk():
        raise PluginValidationError(f"禁止包含符号链接或硬链接: {member.name}")
    if member.isdev() or member.ischr() or member.isblk() or member.isfifo():
        raise PluginValidationError(f"禁止包含特殊设备文件: {member.name}")

    raw_name = member.name.replace("\\", "/")
    if raw_name.startswith("/"):
        raise PluginValidationError(f"禁止包含绝对路径文件: {member.name}")

    parts = PurePosixPath(raw_name).parts
    if any(part == ".." for part in parts):
        raise PluginValidationError(f"检测到路径穿越字符 (..): {member.name}")

    normalized = posixpath.normpath(raw_name)
    if normalized.startswith("..") or normalized.startswith("/"):
        raise PluginValidationError(f"检测到非法归档路径: {member.name}")
    return normalized


def validate_plugin_tgz(
    raw_bytes: bytes,
    *,
    allow_lifecycle_scripts: bool = False,
) -> ValidatedPluginPackage:
    """
    纯 Python tarfile 校验 .tgz 插件包：
    1. 限制大小 <= 20MB
    2. 严防路径穿越 (..) / 绝对路径 / 符号链接
    3. 强制包含 package/package.json 且校验 @rgone/* 包名与 semver 版本
    4. 默认拒绝 preinstall/postinstall/install 等生命周期脚本
    """
    if not raw_bytes:
        raise PluginValidationError("上传的 .tgz 文件不能为空")
    if len(raw_bytes) > MAX_PLUGIN_TGZ_BYTES:
        raise PluginValidationError("插件包体积超出 20MB 上限")

    sha256 = hashlib.sha256(raw_bytes).hexdigest()

    try:
        tf = tarfile.open(fileobj=io.BytesIO(raw_bytes), mode="r:gz")
    except (tarfile.TarError, OSError) as exc:
        raise PluginValidationError(f"无效的 .tgz 压缩包: {exc}") from exc

    pkg_json_bytes: bytes | None = None
    with tf:
        for member in tf.getmembers():
            normalized = _validate_tar_member_safe(member)
            if normalized == "package/package.json" and member.isfile():
                extracted = tf.extractfile(member)
                if extracted is not None:
                    pkg_json_bytes = extracted.read()

    if pkg_json_bytes is None:
        raise PluginValidationError("压缩包必须包含标准 npm 目录结构 package/package.json")

    try:
        pkg_json = json.loads(pkg_json_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PluginValidationError(f"package/package.json 解析失败: {exc}") from exc

    if not isinstance(pkg_json, dict):
        raise PluginValidationError("package/package.json 顶层必须是 JSON 对象")

    name = validate_package_name(str(pkg_json.get("name") or ""))
    version = validate_semver(str(pkg_json.get("version") or ""))
    description = str(pkg_json.get("description") or "").strip()

    scripts = pkg_json.get("scripts")
    detected_scripts: List[str] = []
    if isinstance(scripts, dict):
        detected_scripts = sorted(
            key for key in scripts.keys() if str(key).strip().lower() in LIFECYCLE_SCRIPT_KEYS
        )

    has_lifecycle = len(detected_scripts) > 0
    if has_lifecycle and not allow_lifecycle_scripts:
        raise PluginValidationError(
            f"检测到高危生命周期脚本 ({', '.join(detected_scripts)})，默认拒绝直接发布"
        )

    return ValidatedPluginPackage(
        name=name,
        version=version,
        description=description,
        sha256=sha256,
        size_bytes=len(raw_bytes),
        package_json=pkg_json,
        has_lifecycle_scripts=has_lifecycle,
        detected_scripts=detected_scripts,
    )
