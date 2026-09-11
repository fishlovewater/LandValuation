<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import GlassModal from '../../../components/glass/GlassModal.vue'
import AnswerMessage from './AnswerMessage.vue'
import type { AssistantAnswerModel } from '../assistant.types'
import { ASSISTANT_QUESTION_MIN_LENGTH, ASSISTANT_QUESTION_VALIDATION_MESSAGE } from '../assistant.api'

const props = withDefaults(
  defineProps<{
    open?: boolean
    answer?: AssistantAnswerModel | null
    loading?: boolean
    sending?: boolean
    error?: string
    canAsk?: boolean
  }>(),
  { open: false, answer: null, loading: false, sending: false, error: '', canAsk: false },
)

const emit = defineEmits<{
  close: []
  submit: [question: string]
}>()

const question = ref('')
const questionValidationMessage = computed(() => {
  if (!question.value || question.value.trim().length >= ASSISTANT_QUESTION_MIN_LENGTH) return ''
  return ASSISTANT_QUESTION_VALIDATION_MESSAGE
})

watch(() => props.open, (open) => {
  if (open) question.value = ''
})

function submit(): void {
  const value = question.value.trim()
  if (!value || props.sending || props.loading) return
  if (value.length < ASSISTANT_QUESTION_MIN_LENGTH) return
  emit('submit', value)
  question.value = ''
}
</script>

<template>
  <GlassModal
    :open="open"
    title="智能助理"
    id="assistant-drawer"
    class="assistant-drawer"
    aria-describedby="assistant-drawer-description"
    @close="emit('close')"
  >
    <div class="assistant-drawer__content">
      <p id="assistant-drawer-description" class="assistant-drawer__description">
        可針對目前案件提問；回答只會使用你有權查看的案件資料與可核對來源。
      </p>
      <div v-if="loading" class="assistant-drawer__state" role="status" aria-live="polite">正在載入智能助理…</div>
      <p v-else-if="error" class="assistant-drawer__error" role="alert">{{ error }}</p>
      <AnswerMessage v-if="answer" :answer="answer" />
      <form class="assistant-drawer__form" @submit.prevent="submit">
        <label for="assistant-drawer-question">問題</label>
        <textarea
          id="assistant-drawer-question"
          data-testid="assistant-drawer-question"
          v-model="question"
          rows="4"
          maxlength="2000"
          :disabled="!canAsk || loading || sending"
          :aria-invalid="questionValidationMessage ? 'true' : undefined"
          :aria-describedby="questionValidationMessage ? 'assistant-drawer-question-validation' : undefined"
          placeholder="請輸入要核對的問題"
        />
        <p
          v-if="questionValidationMessage"
          id="assistant-drawer-question-validation"
          class="assistant-drawer__validation"
          data-testid="assistant-drawer-question-validation"
          role="alert"
        >
          {{ questionValidationMessage }}
        </p>
        <p v-if="!canAsk" class="assistant-drawer__permission" data-testid="assistant-drawer-permission" role="status">
          目前帳號沒有查看案件來源與知識文件的權限。
        </p>
        <button data-testid="assistant-drawer-submit" type="submit" :disabled="!canAsk || loading || sending || question.trim().length < ASSISTANT_QUESTION_MIN_LENGTH" @click.prevent="submit">
          {{ sending ? '送出中…' : '送出問題' }}
        </button>
      </form>
      <p class="assistant-disclaimer">AI 建議僅供輔助，最終由專業人員判斷。</p>
    </div>
  </GlassModal>
</template>

<style scoped>
.assistant-drawer__content {
  display: grid;
  gap: 16px;
}

.assistant-drawer__description,
.assistant-drawer__state,
.assistant-drawer__error,
.assistant-disclaimer {
  margin: 0;
  color: var(--app-ink-soft);
  font-size: 13px;
  line-height: 1.65;
}

.assistant-drawer__error {
  padding: 11px 13px;
  border: 1px solid #efcfca;
  border-radius: 9px;
  color: #8a3c34;
  background: #fff5f3;
}

.assistant-drawer__form {
  display: grid;
  gap: 8px;
  padding: 16px;
  border: 1px solid var(--app-line);
  border-radius: 10px;
  background: var(--app-paper-strong);
}

.assistant-drawer__form label {
  color: var(--app-ink);
  font-size: 13px;
  font-weight: 800;
}

.assistant-drawer__form textarea {
  width: 100%;
  min-height: 104px;
  padding: 10px 12px;
  border: 1px solid var(--app-line);
  border-radius: 8px;
  color: var(--app-ink);
  background: #fff;
  font: inherit;
  line-height: 1.6;
  resize: vertical;
}

.assistant-drawer__permission {
  margin: 0;
  color: var(--app-muted);
  font-size: 12px;
  line-height: 1.5;
}

.assistant-drawer__validation {
  margin: 0;
  color: #8a3c34;
  font-size: 12px;
  line-height: 1.5;
}

.assistant-drawer__form button {
  min-height: 44px;
  padding: 8px 14px;
  border: 1px solid var(--app-accent);
  border-radius: 8px;
  color: #fff;
  background: var(--app-accent);
  cursor: pointer;
  font-weight: 800;
}

.assistant-drawer__form button:disabled {
  cursor: not-allowed;
  opacity: 0.55;
}

.assistant-disclaimer {
  color: var(--app-muted);
  font-size: 11px;
}

:deep(.assistant-drawer) {
  width: min(640px, calc(100vw - 32px));
}

:deep(.assistant-drawer .lg-modal__body) {
  max-height: min(75vh, 780px);
  overflow: auto;
}
</style>
