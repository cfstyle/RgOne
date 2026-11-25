from __future__ import annotations
import csv
import io
from typing import List, Optional
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from fastapi.responses import StreamingResponse
import openpyxl
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from backend.app.core.database import get_db
from backend.app.api.deps import get_current_admin
from backend.app.models.employee import Employee
from backend.app.models.admin_user import AdminUser
from backend.app.models.token import UserToken
from backend.app.services.new_api_client import new_api_client

router = APIRouter(prefix="/admin/employees", tags=["管理员员工白名单管理"])


class EmployeeCreate(BaseModel):
    emp_no: str = Field(..., min_length=1, max_length=64)
    name: str = Field(..., min_length=1, max_length=64)
    department: str = Field(..., min_length=1, max_length=128)
    phone_last4: Optional[str] = Field(None, max_length=4)
    is_active: bool = True


class EmployeeUpdate(BaseModel):
    name: Optional[str] = None
    department: Optional[str] = None
    phone_last4: Optional[str] = None
    is_active: Optional[bool] = None


@router.get("", summary="分页获取员工名单列表")
def list_employees(
    page: int = Query(1, ge=1),
    page_size: int = Query(15, ge=1, le=100),
    keyword: Optional[str] = Query(None),
    is_active: Optional[bool] = Query(None),
    admin: AdminUser = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    query = db.query(Employee)
    if keyword:
        kw = f"%{keyword.strip()}%"
        query = query.filter((Employee.emp_no.ilike(kw)) | (Employee.name.ilike(kw)) | (Employee.department.ilike(kw)))
    if is_active is not None:
        query = query.filter(Employee.is_active == is_active)

    total = query.count()
    records = query.order_by(Employee.id.desc()).offset((page - 1) * page_size).limit(page_size).all()

    items = []
    for r in records:
        items.append({
            "id": r.id,
            "emp_no": r.emp_no,
            "name": r.name,
            "department": r.department,
            "phone_last4": r.phone_last4,
            "is_active": r.is_active,
            "has_token": r.token is not None,
            "token_id": r.token.id if r.token else None,
            "token_status": r.token.status if r.token else None,
            "created_at": r.created_at.strftime("%Y-%m-%d %H:%M:%S"),
        })

    return {
        "success": True,
        "total": total,
        "page": page,
        "page_size": page_size,
        "items": items,
    }


@router.post("", summary="单条新增员工")
def create_employee(
    emp_data: EmployeeCreate,
    admin: AdminUser = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    emp_no = emp_data.emp_no.strip()
    exists = db.query(Employee).filter(Employee.emp_no == emp_no).first()
    if exists:
        raise HTTPException(status_code=400, detail=f"工号 {emp_no} 已存在")

    new_emp = Employee(
        emp_no=emp_no,
        name=emp_data.name.strip(),
        department=emp_data.department.strip(),
        phone_last4=emp_data.phone_last4.strip() if emp_data.phone_last4 else None,
        is_active=emp_data.is_active
    )
    db.add(new_emp)
    db.commit()
    db.refresh(new_emp)

    return {"success": True, "message": "员工已新增", "id": new_emp.id}


@router.put("/{emp_id}", summary="修改员工信息")
async def update_employee(
    emp_id: int,
    emp_data: EmployeeUpdate,
    admin: AdminUser = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    emp = db.query(Employee).filter(Employee.id == emp_id).first()
    if not emp:
        raise HTTPException(status_code=404, detail="员工记录未找到")

    updates = emp_data.model_dump(exclude_unset=True)
    status_warning = ""

    # 状态变更与网关联动
    if "is_active" in updates:
        target_active = updates["is_active"]
        if target_active is False and emp.is_active is True:
            # 停用员工：立即联动禁用网关 Token
            if emp.token and emp.token.new_api_token_id:
                try:
                    await new_api_client.update_token_status(emp.token.new_api_token_id, 2)
                    emp.token.status = "disabled"
                except Exception as e:
                    # 保留本地停用状态与网关 Token ID，标记待重试状态
                    emp.token.status = "gateway_disable_pending"
                    status_warning = f"；但网关禁用失败 ({str(e)})，已标记为待重试"
        elif target_active is True and emp.is_active is False:
            # 显式复职员工：联动恢复网关 Token
            if emp.token and emp.token.new_api_token_id and emp.token.status in ("disabled", "gateway_disable_pending"):
                try:
                    await new_api_client.update_token_status(emp.token.new_api_token_id, 1)
                    emp.token.status = "active"
                except Exception as e:
                    status_warning = f"；但网关恢复启用失败 ({str(e)})"

    for k, v in updates.items():
        setattr(emp, k, v)

    db.commit()
    msg = "员工信息已修改" + status_warning
    return {"success": True, "message": msg}


@router.post("/{emp_id}/retry-disable-token", summary="重试吊销/禁用停用员工的网关 Token")
async def retry_disable_employee_token(
    emp_id: int,
    admin: AdminUser = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    emp = db.query(Employee).filter(Employee.id == emp_id).first()
    if not emp:
        raise HTTPException(status_code=404, detail="员工记录未找到")
    if emp.is_active:
        raise HTTPException(status_code=400, detail="该员工处于在职启用状态，无需重试吊销")
    if not emp.token or not emp.token.new_api_token_id:
        return {"success": True, "message": "该员工无关联网关 Token，无需处理"}

    try:
        await new_api_client.update_token_status(emp.token.new_api_token_id, 2)
        emp.token.status = "disabled"
        db.commit()
        return {"success": True, "message": "网关 Token 已成功禁用"}
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"网关调用失败: {str(e)}")


@router.delete("/{emp_id}", summary="删除员工")
async def delete_employee(
    emp_id: int,
    admin: AdminUser = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    emp = db.query(Employee).filter(Employee.id == emp_id).first()
    if not emp:
        raise HTTPException(status_code=404, detail="员工记录未找到")

    # 安全检查：若有网关 Token，必须先成功吊销网关上的 Token，严禁残留孤儿 Token
    if emp.token and emp.token.new_api_token_id:
        try:
            await new_api_client.delete_token(emp.token.new_api_token_id)
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"网关关联 Token 吊销失败，已中止删除以防止残留孤儿 Token: {str(e)}"
            )

    db.delete(emp)
    db.commit()
    return {"success": True, "message": "员工及关联网关凭证已彻底删除"}


@router.get("/template", summary="下载员工名单 Excel 批量导入模板")
def download_import_template(admin: AdminUser = Depends(get_current_admin)):
    """生成并导出标准的 .xlsx 格式模版"""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "员工白名单导入"

    # 表头
    headers = ["工号*", "姓名*", "所属部门*", "手机号后4位(可选)"]
    ws.append(headers)

    # 示范数据（行内 8 位工号格式）
    ws.append(["06700956", "陈飞", "金融科技部 · 核心架构组", "0956"])
    ws.append(["06701099", "李华", "运营管理部 · 结算清算组", "1099"])

    # 调整列宽
    for col in ws.columns:
        max_len = max(len(str(cell.value or '')) for cell in col)
        col_letter = openpyxl.utils.get_column_letter(col[0].column)
        ws.column_dimensions[col_letter].width = max(max_len * 2 + 4, 15)

    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)

    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": 'attachment; filename="employee_import_template.xlsx"'
        }
    )


@router.post("/import", summary="批量导入员工白名单 (支持 .xlsx 与 .csv)")
async def import_employees(
    file: UploadFile = File(...),
    admin: AdminUser = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    """
    解析 Excel 或 CSV 文件，支持增量新建与已有工号覆盖更新
    返回导入报告：新建数、更新数、跳过数及错误明细
    """
    filename = file.filename or ""
    content = await file.read()

    created_count = 0
    updated_count = 0
    skipped_count = 0
    errors: List[str] = []

    rows: List[List[str]] = []

    if filename.endswith(".xlsx") or filename.endswith(".xls"):
        try:
            wb = openpyxl.load_workbook(io.BytesIO(content), data_only=True)
            ws = wb.active
            for row in ws.iter_rows(values_only=True):
                rows.append([str(c).strip() if c is not None else "" for c in row])
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"解析 Excel 失败: {str(e)}")
    elif filename.endswith(".csv"):
        try:
            text = content.decode("utf-8-sig")
            reader = csv.reader(io.StringIO(text))
            for row in reader:
                rows.append([c.strip() for c in row])
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"解析 CSV 失败: {str(e)}")
    else:
        raise HTTPException(status_code=400, detail="仅支持上传 .xlsx 或 .csv 格式的文件")

    if not rows or len(rows) < 2:
        raise HTTPException(status_code=400, detail="文件内容为空或仅包含表头")

    # 跳过第 1 行表头
    for idx, r in enumerate(rows[1:], start=2):
        if not r or not any(r):
            continue
        emp_no = r[0] if len(r) > 0 else ""
        name = r[1] if len(r) > 1 else ""
        dept = r[2] if len(r) > 2 else "科技部"
        phone = r[3] if len(r) > 3 else None

        if not emp_no or not name:
            skipped_count += 1
            errors.append(f"第 {idx} 行：工号或姓名为空，已跳过")
            continue

        emp = db.query(Employee).filter(Employee.emp_no == emp_no).first()
        if emp:
            emp.name = name
            emp.department = dept
            if phone:
                emp.phone_last4 = phone[:4]
            # 保持原有 is_active 状态，严禁普通名册批量导入自动复职！复职必须通过显式操作
            updated_count += 1
        else:
            new_emp = Employee(
                emp_no=emp_no,
                name=name,
                department=dept,
                phone_last4=phone[:4] if phone else None,
                is_active=True
            )
            db.add(new_emp)
            created_count += 1

    db.commit()

    return {
        "success": True,
        "message": f"导入完成：新增 {created_count} 条，更新 {updated_count} 条，跳过 {skipped_count} 条",
        "data": {
            "created": created_count,
            "updated": updated_count,
            "skipped": skipped_count,
            "errors": errors[:10],
        }
    }
