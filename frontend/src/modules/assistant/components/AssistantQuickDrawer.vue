<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { RouterLink, useRoute } from 'vue-router'
import { PhArrowClockwise as Retry, PhBroom as Clear, PhSparkle as Sparkle } from '@phosphor-icons/vue'
import GlassDrawer from '../../../components/glass/GlassDrawer.vue'
import { useAuthStore } from '../../../stores/auth.store'
import { valuationApi } from '../../valuation/valuation.api'
import AnswerMessage from './AnswerMessage.vue'
import {
  ASSISTANT_QUESTION_MIN_LENGTH,
  assistantApi,
  canAskAssistantQuestion,
  canAskGeneralAssistantQuestion,
  canStartAssistantSession,
  safeAssistantErrorMessage,
} from '../assistant.api'
import { mapAssistantQuestion } from '../assistant.mappers'
import type { AssistantAnswerModel, AssistantSessionModel } from '../assistant.types'

const props = withDefaults(defineProps<{ open?: boolean }>(), { open: false })
const emit = defineEmits<{ close: [] }>()
const route = useRoute()
const auth = useAuthStore()

interface ConversationItem {
  id: number
  question: string
  answer: AssistantAnswerModel | null
  failed?: boolean
}

const session = ref<AssistantSessionModel | null>(null)
const items = ref<ConversationItem[]>([])
const question = ref('')
const loading = ref(false)
const sending = ref(false)
const error = ref('')
const contextCaseId = ref('')
const contextFormId = ref('')
let serial = 0

const canStart = computed(() => canStartAssistantSession(auth.permissions))
const canAskGeneral = computed(() => canAskGeneralAssistantQuestion(auth.permissions))
const canAsk = computed(() => (
  session.value
    ? canAskAssistantQuestion(auth.permissions)
    : canAskGeneral.value
))
const contextReady = computed(() => Boolean(contextCaseId.value && contextFormId.value))
const currentContextLabel = computed(() => {
  if (!contextCaseId.value) return '一般知識模式 · 不帶入案件資料'
  if (!contextFormId.value) return '已取得案件，但尚無可用 F03 估價表'
  return `案件 ${contextCaseId.value.slice(0, 8)}… · F03`
})

function routeString(value: unknown): string {
  return typeof value === 'string' ? value.trim() : ''
}

async function resolveContext(): Promise<{ caseId: string; formId: string }> {
  const caseId = routeString(route.query.caseId)
    || routeString(route.query.case_id)
    || routeString(route.params.caseId)
  let formId = routeString(route.query.formId) || routeString(route.query.form_id)
  contextCaseId.value = caseId
  contextFormId.value = formId

  if (!caseId || formId || !auth.permissions.includes('valuation.read')) return { caseId, formId }
  const forms = await valuationApi.listForms(caseId)
  const f03 = forms
    .filter((form) => form.form_code === 'F03')
    .sort((left, right) => right.version_no - left.version_no)[0]
  formId = f03?.form_instance_id ?? ''
  contextFormId.value = formId
  return { caseId, formId }
}

async function ensureSession(forceNew = false): Promise<void> {
  const token = ++serial
  error.value = ''
  if (!canStart.value) {
    session.value = null
    return
  }
  loading.value = true
  try {
    const context = await resolveContext()
    if (token !== serial) return
    if (!context.caseId || !context.formId) {
      session.value = null
      return
    }
    if (
      !forceNew
      && session.value?.caseId === context.caseId
      && session.value.formInstanceId === context.formId
    ) return
    session.value = await assistantApi.createSession({
      caseId: context.caseId,
      formId: context.formId,
      routeName: String(route.name ?? 'assistant-drawer'),
    })
    if (forceNew) items.value = []
  } catch (caught) {
    if (token === serial) {
      session.value = null
      error.value = safeAssistantErrorMessage(caught)
    }
  } finally {
    if (token === serial) loading.value = false
  }
}

async function send(value = question.value): Promise<void> {
  const content = value.trim()
  if (!content || content.length < ASSISTANT_QUESTION_MIN_LENGTH || !canAsk.value || sending.value) return
  question.value = ''
  error.value = ''
  const item: ConversationItem = { id: Date.now(), question: content, answer: null }
  items.value.push(item)
  sending.value = true
  try {
    const response = session.value
      ? await assistantApi.askQuestion(session.value.assistantSessionId, { question: content })
      : await assistantApi.askGeneralQuestion({ question: content })
    item.answer = mapAssistantQuestion(response)
  } catch (caught) {
    item.failed = true
    error.value = safeAssistantErrorMessage(caught)
  } finally {
    sending.value = false
  }
}

async function retryLast(): Promise<void> {
  const last = [...items.value].reverse().find((item) => item.question)
  if (last) await send(last.question)
}

async function clearConversation(): Promise<void> {
  items.value = []
  question.value = ''
  await ensureSession(true)
}

watch(
  () => props.open,
  (open) => {
    if (open) void ensureSession()
  },
)

watch(
  () => route.fullPath,
  () => {
    serial += 1
    session.value = null
    contextCaseId.value = ''
    contextFormId.value = ''
    items.value = []
    if (props.open) void ensureSession()
  },
)
</script>

<template>
  <GlassDrawer :open="open" title="估價審查知識助手" width="520px" @close="emit('close')">
    <div class="assistant-quick">
      <section class="assistant-quick__context" data-testid="assistant-quick-context">
        <Sparkle :size="18" weight="duotone" aria-hidden="true" />
        <div><strong>目前提問脈絡</strong><span>{{ currentContextLabel }}</span></div>
      </section>

      <p v-if="loading" class="assistant-quick__notice" role="status">正在建立安全工作階段…</p>
      <p v-else-if="!canStart && !canAskGeneral" class="assistant-quick__notice" role="status">
        此帳號沒有啟用 AI 助理或知識資料讀取權限。
      </p>
      <p v-else-if="!contextReady" class="assistant-quick__notice" role="status">
        目前為一般知識模式，可直接查詢法規、條文與知識文件，不會帶入案件資料。
      </p>
      <p v-if="error" class="assistant-quick__error" role="alert">{{ error }}</p>

      <div v-if="items.length" class="assistant-quick__messages" aria-live="polite">
        <article v-for="item in items" :key="item.id" class="assistant-quick__exchange">
          <div class="assistant-quick__user"><span>問題</span><p>{{ item.question }}</p></div>
          <AnswerMessage v-if="item.answer" :answer="item.answer" />
          <p v-else-if="item.failed" class="assistant-quick__failed">這次提問未完成，可重新提問。</p>
          <p v-else class="assistant-quick__thinking">正在查找可授權引用的資料…</p>
        </article>
      </div>
      <div v-else class="assistant-quick__empty">
        <strong>尚無對話</strong>
        <span>回答會標示可驗證的法規、基準或文件來源；找不到足夠資料時會明確告知。</span>
      </div>

      <form class="assistant-quick__composer" @submit.prevent="send()">
        <label for="assistant-quick-question">輸入問題</label>
        <textarea
          id="assistant-quick-question"
          v-model="question"
          rows="4"
          maxlength="2000"
          :disabled="!canAsk || loading || sending"
          :placeholder="contextReady
            ? '例如：這筆案件採用的估價基準依據是什麼？'
            : '例如：土地估價相關規定有哪些適用條件？'"
        />
        <div class="assistant-quick__composer-actions">
          <button type="button" class="assistant-quick__secondary" :disabled="!items.length || sending" @click="retryLast">
            <Retry :size="16" aria-hidden="true" />重新提問
          </button>
          <button type="button" class="assistant-quick__secondary" :disabled="!items.length || sending" @click="clearConversation">
            <Clear :size="16" aria-hidden="true" />清除對話
          </button>
          <button type="submit" class="assistant-quick__send" :disabled="!canAsk || sending || question.trim().length < ASSISTANT_QUESTION_MIN_LENGTH">
            {{ sending ? '送出中…' : '送出' }}
          </button>
        </div>
      </form>

      <RouterLink class="assistant-quick__full" :to="contextReady
        ? { name: 'assistant', query: { caseId: contextCaseId, formId: contextFormId } }
        : { name: 'assistant' }" @click="emit('close')">
        開啟完整助理工作區
      </RouterLink>
      <p class="assistant-quick__disclaimer">AI 建議僅供輔助；可見來源與可執行操作仍由後端權限決定。</p>
    </div>
  </GlassDrawer>
</template>

<style scoped>
.assistant-quick { display: grid; gap: 14px; min-height: 100%; }
.assistant-quick__context,
.assistant-quick__empty,
.assistant-quick__composer,
.assistant-quick__exchange {
  border: 1px solid rgba(255,255,255,.82);
  border-radius: 16px;
  background: rgba(255,255,255,.58);
  box-shadow: 0 12px 28px rgba(45,65,95,.07);
}
.assistant-quick__context { display: flex; align-items: center; gap: 10px; padding: 12px 14px; color: var(--app-blue); }
.assistant-quick__context div { display: grid; gap: 2px; }
.assistant-quick__context strong { color: var(--app-ink); font-size: 12px; }
.assistant-quick__context span { color: var(--app-muted); font-size: 11px; }
.assistant-quick__notice,
.assistant-quick__error { margin: 0; padding: 12px 14px; border-radius: 12px; font-size: 12px; line-height: 1.65; }
.assistant-quick__notice { color: var(--app-ink-soft); background: rgba(233,240,248,.72); }
.assistant-quick__error { color: #8a3c34; background: rgba(255,245,243,.84); }
.assistant-quick__messages { display: grid; gap: 12px; }
.assistant-quick__exchange { display: grid; gap: 12px; padding: 14px; }
.assistant-quick__user { display: grid; gap: 5px; }
.assistant-quick__user span { color: var(--app-accent-deep); font-size: 10px; font-weight: 900; letter-spacing: .12em; }
.assistant-quick__user p { margin: 0; color: var(--app-ink); line-height: 1.65; }
.assistant-quick__thinking,
.assistant-quick__failed { margin: 0; color: var(--app-muted); font-size: 12px; }
.assistant-quick__empty { display: grid; gap: 5px; padding: 24px 18px; text-align: center; }
.assistant-quick__empty strong { color: var(--app-ink); }
.assistant-quick__empty span { color: var(--app-muted); font-size: 12px; line-height: 1.65; }
.assistant-quick__composer { display: grid; gap: 8px; margin-top: auto; padding: 14px; }
.assistant-quick__composer label { color: var(--app-ink); font-size: 12px; font-weight: 900; }
.assistant-quick__composer textarea { width: 100%; min-height: 96px; padding: 11px 12px; border: 1px solid var(--app-line); border-radius: 12px; color: var(--app-ink); background: rgba(255,255,255,.8); font: inherit; resize: vertical; }
.assistant-quick__composer textarea:focus { outline: 0; border-color: var(--app-accent); box-shadow: 0 0 0 3px var(--app-accent-soft); }
.assistant-quick__composer-actions { display: flex; flex-wrap: wrap; gap: 8px; }
.assistant-quick__composer-actions button { min-height: 40px; border-radius: 999px; cursor: pointer; font-weight: 800; }
.assistant-quick__secondary { display: inline-flex; align-items: center; gap: 5px; padding: 0 11px; border: 1px solid var(--app-line); color: var(--app-ink-soft); background: rgba(255,255,255,.66); }
.assistant-quick__send { margin-left: auto; padding: 0 18px; border: 1px solid var(--app-accent); color: #fff; background: var(--app-accent); }
.assistant-quick__composer-actions button:disabled { cursor: not-allowed; opacity: .5; }
.assistant-quick__full { justify-self: end; color: var(--app-blue); font-size: 12px; font-weight: 800; }
.assistant-quick__disclaimer { margin: 0; color: var(--app-muted); font-size: 10px; line-height: 1.55; text-align: center; }
</style>