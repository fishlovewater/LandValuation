<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { RouterLink, useRoute } from 'vue-router'
import {
  PhArrowClockwise as Retry,
  PhBriefcase as Briefcase,
  PhClockCounterClockwise as History,
  PhDatabase as Database,
  PhPlus as Plus,
  PhSparkle as Sparkle,
} from '@phosphor-icons/vue'
import GlassDrawer from '../../../components/glass/GlassDrawer.vue'
import { useAuthStore } from '../../../stores/auth.store'
import { reviewApi } from '../../review/review.api'
import AnswerMessage from './AnswerMessage.vue'
import { assistantRouteContext, conversationMatchesAssistantContext } from '../assistant.context'
import {
  ASSISTANT_QUESTION_MIN_LENGTH,
  assistantApi,
  canUseAssistant,
  mapKnowledgeQuestionResponse,
  safeAssistantErrorMessage,
} from '../assistant.api'
import { mapAssistantQuestion } from '../assistant.mappers'
import type {
  AssistantAnswerModel,
  AssistantConversationContextDto,
  KnowledgeConversationDto,
  KnowledgeConversationMessageDto,
} from '../assistant.types'

const props = withDefaults(defineProps<{ open?: boolean }>(), { open: false })
const emit = defineEmits<{ close: [] }>()
const route = useRoute()
const auth = useAuthStore()

interface ConversationItem {
  id: number | string
  question: string
  answer: AssistantAnswerModel | null
  failed?: boolean
}

const conversationId = ref('')
const conversations = ref<KnowledgeConversationDto[]>([])
const items = ref<ConversationItem[]>([])
const question = ref('')
const loading = ref(false)
const sending = ref(false)
const error = ref('')
const historyOpen = ref(false)
const resolvedReviewCaseId = ref('')
let serial = 0

const canUse = computed(() => canUseAssistant(auth.permissions))

const routeContext = computed(() => assistantRouteContext(route, resolvedReviewCaseId.value))
const context = computed(() => {
  const value = routeContext.value
  return {
    caseId: value.case_id ?? '',
    reviewId: value.review_id ?? '',
    findingId: value.finding_id ?? '',
    workspace: value.workspace ?? '',
  }
})

const currentContextLabel = computed(() => {
  const active = activeConversation.value
  if (active && !conversationMatchesContext(active)) {
    if (active.review_id) return '正在查看一筆歷史審查案件對話；提問會沿用該對話已授權的案件情境。'
    if (active.case_id) return '正在查看一筆歷史案件對話；提問會沿用該對話已授權的案件情境。'
    return '正在查看一般歷史對話；需要正式依據時，系統會自動查詢可用知識資料。'
  }
  if (context.value.caseId && context.value.reviewId) {
    return context.value.findingId
      ? '已連結目前審查案件與選取疑點；系統會依問題自動判斷是否需要案件資料、知識資料或兩者。'
      : '已連結目前審查案件；系統會依問題自動判斷資料來源。'
  }
  if (context.value.caseId && context.value.workspace === 'history') {
    return '已連結目前案件歷程；系統會依問題自動判斷是否需要歷程案件資料、知識來源或兩者。'
  }
  if (context.value.caseId) return '已連結目前案件；一般問答直接回答，涉及案件或正式依據時會自動取得可用資料。'
  return '一般問題直接回答；需要正式依據時，系統會自動查詢可用知識資料。'
})
const emptyTitle = computed(() => '開始對話')
const emptyCopy = computed(() => context.value.caseId
  ? '直接輸入問題。系統會依問題與目前工作情境，自動判斷是否需要案件資料、知識來源或兩者。'
  : '直接輸入問題。一般問答不會啟動知識檢索；需要正式依據時才會自動查詢知識資料。')

function routeString(value: unknown): string {
  return typeof value === 'string' ? value.trim() : ''
}

function contextPayload(): AssistantConversationContextDto {
  return { ...routeContext.value }
}

const activeConversation = computed(() =>
  conversations.value.find((item) => item.conversation_id === conversationId.value) ?? null,
)

function conversationMatchesContext(conversation: KnowledgeConversationDto): boolean {
  return conversationMatchesAssistantContext(conversation, routeContext.value)
}

function activeQuestionContext(): AssistantConversationContextDto {
  const active = activeConversation.value
  if (!active) return contextPayload()
  return {
    case_id: active.case_id,
    review_id: active.review_id,
    finding_id: active.finding_id,
    workspace: active.workspace,
  }
}

function restoreConversation(rows: KnowledgeConversationMessageDto[]): void {
  const restored: ConversationItem[] = []
  let current: ConversationItem | null = null
  for (const row of rows) {
    if (row.role === 'USER') {
      current = { id: row.message_id, question: row.content, answer: null }
      restored.push(current)
      continue
    }
    if (row.role === 'ASSISTANT' && row.answer && current) {
      current.answer = mapAssistantQuestion(mapKnowledgeQuestionResponse(row.answer))
    }
  }
  items.value = restored
}

async function refreshConversations(): Promise<void> {
  if (!canUse.value) {
    conversations.value = []
    return
  }
  conversations.value = await assistantApi.listKnowledgeConversations()
}

async function loadConversation(targetId: string): Promise<void> {
  conversationId.value = targetId
  const rows = await assistantApi.getKnowledgeConversationMessages(targetId)
  restoreConversation(rows)
}

async function ensureConversation(forceNew = false): Promise<void> {
  await refreshConversations()
  let selected = forceNew
    ? undefined
    : conversations.value.find((item) => item.conversation_id === conversationId.value && conversationMatchesContext(item))
      ?? conversations.value.find(conversationMatchesContext)

  if (!selected) {
    selected = await assistantApi.createKnowledgeConversation(contextPayload())
    conversations.value = [selected, ...conversations.value]
  }
  await loadConversation(selected.conversation_id)
}

async function resolveReviewCaseContext(): Promise<void> {
  const reviewId = routeString(route.params.reviewId)
    || routeString(route.query.reviewId)
    || routeString(route.query.review_id)
  const directCaseId = routeString(route.query.caseId)
    || routeString(route.query.case_id)
    || routeString(route.params.caseId)
  if (!reviewId || directCaseId || resolvedReviewCaseId.value) return
  if (!auth.permissions.includes('review.execute') || !auth.permissions.includes('case.read')) return
  const detail = await reviewApi.getCase(reviewId)
  resolvedReviewCaseId.value = detail.case.case_id
}

async function initializeAssistant(): Promise<void> {
  const token = ++serial
  error.value = ''
  loading.value = true
  historyOpen.value = false
  try {
    if (!canUse.value) return
    await resolveReviewCaseContext()
    if (token !== serial) return
    await ensureConversation()
  } catch (caught) {
    if (token === serial) error.value = safeAssistantErrorMessage(caught)
  } finally {
    if (token === serial) loading.value = false
  }
}

async function send(value = question.value): Promise<void> {
  const content = value.trim()
  if (!content || content.length < ASSISTANT_QUESTION_MIN_LENGTH || !canUse.value || !conversationId.value || sending.value) return
  question.value = ''
  error.value = ''
  const item: ConversationItem = { id: Date.now(), question: content, answer: null }
  items.value.push(item)
  sending.value = true
  try {
    const response = await assistantApi.askKnowledgeConversation(conversationId.value, {
      question: content,
      ...activeQuestionContext(),
    })
    item.answer = mapAssistantQuestion(response)
    void refreshConversations().catch(() => undefined)
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

async function startNewConversation(): Promise<void> {
  if (!canUse.value || loading.value || sending.value) return
  question.value = ''
  error.value = ''
  historyOpen.value = false
  loading.value = true
  try {
    conversationId.value = ''
    items.value = []
    await ensureConversation(true)
  } catch (caught) {
    error.value = safeAssistantErrorMessage(caught)
  } finally {
    loading.value = false
  }
}

async function toggleHistory(): Promise<void> {
  historyOpen.value = !historyOpen.value
  if (!historyOpen.value || !canUse.value) return
  try {
    await refreshConversations()
  } catch (caught) {
    error.value = safeAssistantErrorMessage(caught)
  }
}

async function selectConversation(target: KnowledgeConversationDto): Promise<void> {
  if (!canUse.value) return
  historyOpen.value = false
  question.value = ''
  error.value = ''
  loading.value = true
  try {
    await loadConversation(target.conversation_id)
  } catch (caught) {
    error.value = safeAssistantErrorMessage(caught)
  } finally {
    loading.value = false
  }
}
function conversationTitle(conversation: KnowledgeConversationDto): string {
  return conversation.title.trim() || '新對話'
}

function conversationContextLabel(conversation: KnowledgeConversationDto): string {
  if (conversation.workspace === 'review') return '審查案件'
  if (conversation.workspace === 'valuation') return '估價案件'
  if (conversation.workspace === 'history') return '案件歷程'
  if (conversation.case_id) return '案件對話'
  return '一般對話'
}

function conversationTime(value: string): string {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return ''
  return date.toLocaleString('zh-TW', {
    month: 'numeric',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

function citationLabel(citation: AssistantAnswerModel['citations'][number]): string {
  const title = citation.documentName || citation.documentCode || '來源文件'
  const locations: string[] = []
  if (citation.articleNo) locations.push(citation.articleNo)
  if (citation.pageStart) locations.push(`第 ${citation.pageStart} 頁`)
  return locations.length ? `${title} · ${locations.join(' · ')}` : title
}

function fullPageQuery(): Record<string, string> {
  const query: Record<string, string> = {}
  if (conversationId.value) query.conversationId = conversationId.value
  const active = activeConversation.value
  const resolved = activeQuestionContext()
  if (resolved.case_id) query.caseId = resolved.case_id
  if (resolved.review_id) query.reviewId = resolved.review_id
  if (resolved.finding_id) query.findingId = resolved.finding_id
  if (resolved.workspace) query.workspace = resolved.workspace
  if (!active && context.value.caseId) query.caseId = context.value.caseId
  return query
}

const sourceContext = computed(() => activeQuestionContext())

watch(
  () => props.open,
  (open) => {
    if (open) void initializeAssistant()
    else historyOpen.value = false
  },
)

watch(() => route.fullPath, () => {
  if (!props.open) return
  serial += 1
  resolvedReviewCaseId.value = ''
  conversationId.value = ''
  items.value = []
  question.value = ''
  historyOpen.value = false
  void initializeAssistant()
})
</script>

<template>
  <GlassDrawer :open="open" title="AI 助手" width="460px" floating @close="emit('close')">
    <div class="assistant-quick">
      <div class="assistant-quick__toolbar">
        <span class="assistant-quick__auto-note">依問題自動判斷資料來源</span>
        <div class="assistant-quick__history-wrap">
          <button
            class="assistant-quick__history-trigger"
            type="button"
            aria-label="開始新對話"
            title="開始新對話"
            :disabled="loading || sending || !canUse"
            @click="startNewConversation"
          >
            <Plus :size="18" weight="bold" aria-hidden="true" />
          </button>
          <button
            class="assistant-quick__history-trigger"
            type="button"
            aria-label="歷史對話"
            title="歷史對話"
            :aria-expanded="historyOpen"
            aria-controls="assistant-history-popover"
            @click="toggleHistory"
          >
            <History :size="18" weight="bold" aria-hidden="true" />
          </button>
          <section
            v-if="historyOpen"
            id="assistant-history-popover"
            class="assistant-quick__history"
            role="dialog"
            aria-label="歷史對話"
          >
            <header>
              <div><strong>歷史對話</strong><span>依目前登入帳號顯示</span></div>
              <button type="button" :disabled="loading || sending || !canUse" @click="startNewConversation">
                <Plus :size="14" weight="bold" aria-hidden="true" />新增
              </button>
            </header>
            <button
              v-for="conversation in conversations"
              :key="conversation.conversation_id"
              type="button"
              :class="['assistant-quick__history-item', { 'is-current': conversation.conversation_id === conversationId }]"
              @click="selectConversation(conversation)"
            >
              <div>
                <strong>{{ conversationTitle(conversation) }}</strong>
                <small>{{ conversationContextLabel(conversation) }}</small>
              </div>
              <span>{{ conversationTime(conversation.updated_at) }}</span>
            </button>
            <p v-if="!conversations.length" class="assistant-quick__history-empty">
              {{ canUse ? '目前還沒有對話紀錄。' : '此帳號沒有可讀取的對話紀錄。' }}
            </p>
          </section>
        </div>
      </div>

      <section class="assistant-quick__context" data-testid="assistant-quick-context">
        <Sparkle :size="18" weight="duotone" aria-hidden="true" />
        <div><strong>目前工作內容</strong><span>{{ currentContextLabel }}</span></div>
      </section>

      <p v-if="loading" class="assistant-quick__notice" role="status">正在準備 AI 助手…</p>
      <p v-else-if="!canUse" class="assistant-quick__notice" role="status">
        此帳號沒有使用 AI 助手的權限。
      </p>
      <p v-if="error" class="assistant-quick__error" role="alert">{{ error }}</p>

      <div v-if="items.length" class="assistant-quick__messages" aria-live="polite">
        <article v-for="item in items" :key="item.id" class="assistant-quick__exchange">
          <div class="assistant-quick__user"><span>你</span><p>{{ item.question }}</p></div>
          <template v-if="item.answer">
            <AnswerMessage :answer="item.answer" />
            <section
              v-if="item.answer.answerRoute === 'CASE' || item.answer.answerRoute === 'HYBRID' || item.answer.citations.length"
              class="assistant-quick__sources"
              aria-label="資料來源"
            >
              <div class="assistant-quick__sources-heading">
                <Database :size="14" weight="bold" aria-hidden="true" />
                <strong>資料來源</strong>
              </div>
              <ul>
                <li v-if="item.answer.answerRoute === 'CASE' || item.answer.answerRoute === 'HYBRID'">
                  <Briefcase :size="12" weight="bold" aria-hidden="true" />
                  {{ sourceContext.review_id ? (sourceContext.finding_id ? '審查案件與選取疑點' : '審查案件資料') : '案件系統資料' }}
                </li>
                <li v-for="citation in item.answer.citations" :key="citation.citationId">
                  {{ citationLabel(citation) }}
                </li>
              </ul>
            </section>
          </template>
          <p v-else-if="item.failed" class="assistant-quick__failed">這次提問未完成，可重新提問。</p>
          <p v-else class="assistant-quick__thinking">正在判斷問題並準備回答…</p>
        </article>
      </div>
      <div v-else-if="!loading" class="assistant-quick__empty">
        <Sparkle :size="28" weight="duotone" aria-hidden="true" />
        <strong>{{ emptyTitle }}</strong>
        <span>{{ emptyCopy }}</span>
      </div>
    </div>

    <template #footer>
      <div class="assistant-quick__footer">
        <form class="assistant-quick__composer" @submit.prevent="send()">
          <label class="sr-only" for="assistant-quick-question">輸入問題</label>
          <textarea
            id="assistant-quick-question"
            v-model="question"
            rows="3"
            maxlength="2000"
            :disabled="!canUse || loading || sending"
            placeholder="輸入問題；需要案件或正式依據時會自動查找…"
          />
          <div class="assistant-quick__composer-actions">
            <button type="button" class="assistant-quick__icon-action" aria-label="重新提問" title="重新提問" :disabled="!items.length || sending" @click="retryLast">
              <Retry :size="17" weight="bold" aria-hidden="true" />
            </button>
            <RouterLink
              class="assistant-quick__full"
              :to="{ name: 'assistant', query: fullPageQuery() }"
              @click="emit('close')"
            >
              完整頁面
            </RouterLink>
            <button type="submit" class="assistant-quick__send" :disabled="!canUse || sending || question.trim().length < ASSISTANT_QUESTION_MIN_LENGTH">
              {{ sending ? '送出中…' : '送出' }}
            </button>
          </div>
        </form>
        <p class="assistant-quick__disclaimer">身分與資料權限沿用目前登入帳號；AI 只會使用後端授權可讀的資料。</p>
      </div>
    </template>
  </GlassDrawer>
</template>

<style scoped>
.assistant-quick { display:grid; gap:12px; min-height:100%; align-content:start; }
.assistant-quick__toolbar { position:relative; display:flex; align-items:center; justify-content:space-between; gap:8px; }
.assistant-quick__auto-note { color:var(--app-muted); font-size:9px; font-weight:750; }
.assistant-quick__history-wrap { position:relative; display:flex; align-items:center; gap:6px; }
.assistant-quick__history-trigger { display:grid; width:34px; height:34px; place-items:center; border:1px solid #d4dde6; border-radius:8px; color:#607388; background:#fff; cursor:pointer; }
.assistant-quick__history { position:absolute; z-index:3; top:40px; right:0; display:grid; width:min(320px, calc(100vw - 64px)); max-height:390px; overflow:auto; padding:8px; border:1px solid #d5dfe8; border-radius:10px; background:#fff; box-shadow:0 16px 36px rgba(31,48,78,.18); }
.assistant-quick__history header { display:flex; align-items:center; justify-content:space-between; gap:8px; padding:5px 5px 8px; border-bottom:1px solid #edf1f4; }
.assistant-quick__history header>div { display:grid; gap:2px; }.assistant-quick__history header strong{color:var(--app-ink);font-size:11px}.assistant-quick__history header span{color:var(--app-muted);font-size:9px}
.assistant-quick__history header button { display:inline-flex; min-height:28px; align-items:center; gap:4px; padding:4px 7px; border:1px solid #d2dce5; border-radius:7px; color:#2e5984; background:#f7fafe; cursor:pointer; font-size:9px; font-weight:850; }
.assistant-quick__history-item { display:grid; gap:3px; width:100%; padding:9px 8px; border:0; border-bottom:1px solid #f0f3f6; color:inherit; background:#fff; cursor:pointer; text-align:left; }.assistant-quick__history-item:hover,.assistant-quick__history-item.is-current{background:#f2f7fc}.assistant-quick__history-item strong{overflow:hidden;color:#354b61;font-size:10px;text-overflow:ellipsis;white-space:nowrap}.assistant-quick__history-item span{color:var(--app-muted);font-size:8px}
.assistant-quick__history-empty { margin:0; padding:14px 8px; color:var(--app-muted); font-size:10px; line-height:1.55; text-align:center; }
.assistant-quick__case-session { display:flex; align-items:flex-start; gap:6px; margin-top:6px; padding:8px; border-radius:7px; color:#526b82; background:#f5f8fb; font-size:9px; line-height:1.45; }
.assistant-quick__context,.assistant-quick__empty,.assistant-quick__exchange { border:1px solid #e0e6ed; border-radius:10px; background:#fff; }
.assistant-quick__context { display:flex; align-items:center; gap:10px; padding:10px 12px; color:#2e5984; background:#f7fafe; }.assistant-quick__context div{display:grid;gap:2px}.assistant-quick__context strong{color:var(--app-ink);font-size:11px}.assistant-quick__context span{color:var(--app-muted);font-size:9px;line-height:1.45}
.assistant-quick__notice,.assistant-quick__error { margin:0; padding:10px 12px; border-radius:9px; font-size:10px; line-height:1.55; }.assistant-quick__notice{color:var(--app-ink-soft);background:#f2f6fa}.assistant-quick__error{color:#8a3c34;background:#fff5f3}
.assistant-quick__messages { display:grid; gap:12px; }.assistant-quick__exchange{display:grid;gap:10px;padding:12px}.assistant-quick__user{display:grid;gap:4px;justify-items:end}.assistant-quick__user span{color:var(--app-muted);font-size:8px;font-weight:850}.assistant-quick__user p{max-width:88%;margin:0;padding:9px 11px;border-radius:10px 10px 2px 10px;color:#fff;background:#2e5984;font-size:11px;line-height:1.55}
.assistant-quick__thinking,.assistant-quick__failed { margin:0; color:var(--app-muted); font-size:10px; }.assistant-quick__empty{display:grid;gap:6px;min-height:220px;place-items:center;align-content:center;padding:32px 22px;color:#60778e;text-align:center}.assistant-quick__empty strong{color:var(--app-ink);font-size:12px}.assistant-quick__empty span{max-width:320px;color:var(--app-muted);font-size:10px;line-height:1.6}
.assistant-quick__sources { display:grid; gap:6px; padding:8px 10px; border:1px solid #e1e8ee; border-radius:8px; background:#f8fafc; }.assistant-quick__sources-heading{display:flex;align-items:center;gap:5px;color:#536b83}.assistant-quick__sources-heading strong{color:#40576e;font-size:9px}.assistant-quick__sources-heading span{margin-left:auto;color:var(--app-muted);font-size:8px}.assistant-quick__sources ul{display:grid;gap:3px;margin:0;padding-left:17px;color:#627589;font-size:8px;line-height:1.45}
.assistant-quick__footer { display:grid; gap:7px; }.assistant-quick__composer{display:grid;gap:8px}.assistant-quick__composer textarea{width:100%;min-height:72px;max-height:140px;padding:9px 10px;border:1px solid #cdd8e3;border-radius:9px;color:var(--app-ink);background:#fff;font:inherit;font-size:11px;line-height:1.5;resize:vertical}.assistant-quick__composer textarea:focus{outline:0;border-color:#2e5984;box-shadow:0 0 0 3px rgba(46,89,132,.1)}
.assistant-quick__composer-actions{display:flex;align-items:center;gap:6px}.assistant-quick__composer-actions button{cursor:pointer;font-weight:850}.assistant-quick__icon-action{display:grid;width:32px;height:32px;place-items:center;border:1px solid #d4dde6;border-radius:8px;color:#607388;background:#fff}.assistant-quick__send{min-width:68px;min-height:32px;margin-left:auto;padding:0 12px;border:1px solid #2e5984;border-radius:8px;color:#fff;background:#2e5984}.assistant-quick__composer-actions button:disabled{cursor:not-allowed;opacity:.5}.assistant-quick__full{margin-left:3px;color:#2e5984;font-size:9px;font-weight:850;text-decoration:none}.assistant-quick__disclaimer{margin:0;color:var(--app-muted);font-size:8px;line-height:1.4;text-align:center}
.sr-only{position:absolute;width:1px;height:1px;padding:0;margin:-1px;overflow:hidden;clip:rect(0,0,0,0);white-space:nowrap;border:0}
@media(max-width:640px){.assistant-quick__history{position:fixed;top:116px;right:16px;left:16px;width:auto;max-height:45vh}.assistant-quick__full{display:none}}
</style>
