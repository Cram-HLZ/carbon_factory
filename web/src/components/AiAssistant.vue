<template>
  <!-- 悬浮按钮 -->
  <button class="ai-fab" :title="open ? '收起 AI 助手' : 'AI 助手'" @click="open = !open">
    <span v-if="!open">💬</span>
    <span v-else>✕</span>
  </button>

  <!-- 聊天面板 -->
  <transition name="pop">
    <div v-if="open" class="ai-panel card shadow">
      <div class="ai-header">
        <strong>🌿 碳排 AI 助手</strong>
        <button class="btn-close btn-close-white" @click="open = false"></button>
      </div>

      <div ref="bodyRef" class="ai-body">
        <div v-if="messages.length === 0" class="text-muted small text-center mt-4">
          问我：碳排总览、告警、设备溯源、降碳方案…
        </div>
        <div
          v-for="(m, i) in messages"
          :key="i"
          class="ai-msg"
          :class="m.role === 'user' ? 'ai-user' : 'ai-bot'"
        >
          <div class="ai-msg-inner">
            <div v-if="m.tools && m.tools.length" class="ai-tools">
              <div v-for="(t, j) in m.tools" :key="j">🛠 {{ t }}</div>
            </div>
            <div class="ai-bubble" :class="{ 'ai-thinking': m.role === 'assistant' && !m.content }">
              {{ m.content || (m.role === 'assistant' ? '思考中…' : '') }}
            </div>
          </div>
        </div>
      </div>

      <div class="ai-footer">
        <textarea
          v-model="draft"
          class="form-control form-control-sm"
          rows="2"
          placeholder="输入问题，Enter 发送，Shift+Enter 换行"
          @keydown.enter.exact.prevent="send"
        ></textarea>
        <button class="btn btn-sm btn-primary" :disabled="loading || !draft.trim()" @click="send">
          发送
        </button>
      </div>
    </div>
  </transition>
</template>

<script setup>
import { nextTick, ref } from 'vue'
import { chatStream } from '../api'

const open = ref(false)
const messages = ref([])
const draft = ref('')
const loading = ref(false)
const bodyRef = ref(null)

function scrollToBottom() {
  nextTick(() => {
    const el = bodyRef.value
    if (el) el.scrollTop = el.scrollHeight
  })
}

async function send() {
  const text = draft.value.trim()
  if (!text || loading.value) return
  loading.value = true
  draft.value = ''
  // 用户消息 + 空白的 assistant 消息（流式逐块填充）
  messages.value.push({ role: 'user', content: text })
  const botIndex = messages.value.length
  messages.value.push({ role: 'assistant', content: '', tools: [] })
  scrollToBottom()
  try {
    // 发送当前 assistant 之前的完整历史，让模型记住上下文
    const history = messages.value
      .slice(0, botIndex)
      .map((m) => ({ role: m.role, content: m.content }))
    await chatStream(history, (evt) => {
      if (!evt) return
      if (evt.type === 'delta') {
        messages.value[botIndex].content += evt.content || ''
      } else if (evt.type === 'status') {
        messages.value[botIndex].tools.push(evt.content || '')
      }
      scrollToBottom()
    })
    if (!messages.value[botIndex].content) messages.value[botIndex].content = '（无回复）'
  } catch (e) {
    messages.value[botIndex].content = '请求失败：' + (e.message || e)
  } finally {
    loading.value = false
    scrollToBottom()
  }
}
</script>

<style scoped>
.ai-fab {
  position: fixed;
  right: 20px;
  bottom: 20px;
  width: 56px;
  height: 56px;
  border-radius: 50%;
  border: none;
  background: #0f766e;
  color: #fff;
  font-size: 22px;
  box-shadow: 0 4px 14px rgba(0, 0, 0, 0.2);
  cursor: pointer;
  z-index: 1060;
}
.ai-panel {
  position: fixed;
  right: 20px;
  bottom: 88px;
  width: 380px;
  max-width: 92vw;
  height: 520px;
  max-height: 70vh;
  display: flex;
  flex-direction: column;
  z-index: 1060;
  overflow: hidden;
}
.ai-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  background: #0f766e;
  color: #fff;
  padding: 10px 14px;
  font-size: 14px;
}
.ai-body {
  flex: 1;
  overflow-y: auto;
  padding: 12px;
  display: flex;
  flex-direction: column;
  gap: 8px;
  background: #fff;
}
.ai-footer {
  display: flex;
  gap: 6px;
  padding: 8px;
  border-top: 1px solid #e5e7eb;
  background: #f9fafb;
}
.ai-msg {
  display: flex;
}
.ai-user {
  justify-content: flex-end;
}
.ai-bot {
  justify-content: flex-start;
}
.ai-msg-inner {
  max-width: 82%;
  display: flex;
  flex-direction: column;
}
.ai-tools {
  font-size: 11px;
  color: #6b7280;
  margin-bottom: 4px;
}
.ai-bubble {
  padding: 8px 12px;
  border-radius: 12px;
  font-size: 13px;
  line-height: 1.5;
  white-space: pre-wrap;
  word-break: break-word;
}
.ai-thinking {
  color: #9ca3af;
  font-style: italic;
}
.ai-user .ai-bubble {
  background: #0f766e;
  color: #fff;
  border-bottom-right-radius: 4px;
}
.ai-bot .ai-bubble {
  background: #f3f4f6;
  color: #111827;
  border-bottom-left-radius: 4px;
}
.pop-enter-active,
.pop-leave-active {
  transition: opacity 0.15s ease, transform 0.15s ease;
}
.pop-enter-from,
.pop-leave-to {
  opacity: 0;
  transform: translateY(10px);
}
</style>