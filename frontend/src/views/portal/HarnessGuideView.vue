<script setup lang="ts">
import { ArrowLeft } from 'lucide-vue-next'

const steps = [
  { number: 1, width: 1022, height: 601, title: '打开客户端设置', text: '打开 DeepSeek Harness，点击左下角「更多」，再点击「设置」。' },
  { number: 2, width: 1022, height: 601, title: '进入模型设置', text: '在设置窗口的左侧点击「模型」。' },
  { number: 3, width: 1022, height: 601, title: '添加模型提供商', text: '在模型提供商列表底部点击「添加模型提供商」。' },
  { number: 4, width: 1045, height: 607, title: '选择自定义模型 API', text: '切换到「自定义模型 API」，从门户首页复制 Provider ID、显示名称和 API 地址。' },
  { number: 5, width: 1043, height: 606, title: '填写 Key 并获取可用模型', text: '选择 OpenAI Chat Completions，粘贴专属 Key，然后点「获取可用模型」。完成下一步添加模型后，才能创建提供商。' },
  { number: 6, width: 1043, height: 606, title: '勾选并添加模型', text: '在弹出的列表里勾选所需模型，点击「添加所选」。' },
  { number: 7, width: 1043, height: 606, title: '创建提供商', text: '确认模型目录中出现了刚添加的模型，点击底部「创建提供商」。' },
  { number: 8, width: 1043, height: 606, title: '在会话里选择模型', text: '返回会话，打开输入框右下角的模型菜单，在刚创建的提供商分组中选择一个模型。' },
  { number: 9, width: 1043, height: 606, title: '发送文本测试', text: '发送一条简短消息，确认模型能正常返回回复。' },
  { number: 10, width: 1043, height: 606, title: '展开模型选项', text: '回到「设置 → 模型」，编辑刚创建的提供商，点击支持图文的模型右侧箭头，展开「模型选项」。' },
  { number: 11, width: 1043, height: 606, title: '勾选图片并保存', text: '在「输入类型」中保留「文本」，勾选「图片」，然后点击「保存」。使用配置补丁时，受支持的模型已启用图片输入。' },
  { number: 12, width: 1089, height: 703, title: '发送图片验证', text: '选择已开启图片输入的模型，附上一张测试图片并发送「识别图片里的文字」，确认模型能读取图片。' },
]
</script>

<template>
  <div class="harness-guide">
    <header class="guide-header">
      <RouterLink :to="{ name: 'home-guide', hash: '#harness-config' }" class="guide-nav-link md-state-layer">
        <ArrowLeft :size="16" />
        <span>返回首页配置</span>
      </RouterLink>
      <h1 class="type-title-lg">DeepSeek Harness 图文操作手册</h1>
      <p class="type-body">先安装客户端，并在门户用工号登录领取专属 Key。按图完成模型接入和验证。</p>
      <nav class="guide-jumps" aria-label="手册章节">
        <RouterLink :to="{ hash: '#step-1' }" class="guide-nav-link md-state-layer">打开设置并填写配置</RouterLink>
        <RouterLink :to="{ hash: '#step-5' }" class="guide-nav-link md-state-layer">获取模型并保存</RouterLink>
        <RouterLink :to="{ hash: '#step-10' }" class="guide-nav-link md-state-layer">启用并验证图片输入</RouterLink>
      </nav>
    </header>

    <ol class="guide-steps">
      <li v-for="step in steps" :id="`step-${step.number}`" :key="step.number" class="guide-step">
        <h2 class="type-title-md">第 {{ step.number }} 步 · {{ step.title }}</h2>
        <p class="type-body">{{ step.text }}</p>
        <a
          class="guide-screenshot"
          :href="`/harness-guide-images/step-${step.number}.png`"
          target="_blank"
          rel="noopener noreferrer"
          :aria-label="`查看第 ${step.number} 步原图（新窗口）`"
        >
          <img
            :src="`/harness-guide-images/step-${step.number}.png`"
            :alt="`DeepSeek Harness 中的「${step.title}」操作截图`"
            :width="step.width"
            :height="step.height"
            loading="lazy"
            decoding="async"
          />
        </a>
      </li>
    </ol>
  </div>
</template>

<style scoped>
.harness-guide {
  display: grid;
  gap: 24px;
  max-width: 1040px;
  margin-inline: auto;
  padding-bottom: 24px;
}

.guide-header,
.guide-steps,
.guide-step {
  display: grid;
  gap: 12px;
}

.guide-header :is(h1, p),
.guide-step :is(h2, p) {
  margin: 0;
}

.guide-header p,
.guide-step p {
  color: var(--md-sys-color-on-surface-variant);
}

.guide-jumps {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.guide-nav-link {
  display: inline-flex;
  align-items: center;
  justify-self: start;
  gap: 8px;
  min-height: 44px;
  padding-inline: 12px;
  border-radius: var(--md-sys-shape-corner-full);
  color: var(--md-sys-color-primary);
  text-decoration: underline;
  text-underline-offset: 3px;
}

.guide-steps {
  margin: 0;
  padding: 0;
  list-style: none;
  gap: 20px;
}

.guide-step {
  padding: clamp(14px, 3vw, 24px);
  border: 1px solid var(--md-sys-color-outline-variant);
  border-radius: var(--md-sys-shape-corner-large);
  background: var(--md-sys-color-surface-container-lowest);
}

.guide-screenshot {
  display: block;
  border-radius: var(--md-sys-shape-corner-medium);
}

.guide-screenshot img {
  display: block;
  width: 100%;
  height: auto;
  border-radius: inherit;
}

.guide-screenshot:focus-visible,
.guide-nav-link:focus-visible {
  outline: 2px solid var(--md-sys-color-primary);
  outline-offset: 3px;
}
</style>
