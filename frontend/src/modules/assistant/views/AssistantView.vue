<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import { RouterLink, useRoute, useRouter } from 'vue-router'
import EmptyState from '../../../components/common/EmptyState.vue'
import ErrorState from '../../../components/common/ErrorState.vue'
import LoadingSkeleton from '../../../components/common/LoadingSkeleton.vue'
import PageHeader from '../../../components/common/PageHeader.vue'
import GlassCard from '../../../components/glass/GlassCard.vue'
import { useAuthStore } from '../../../stores/auth.store'
import AnswerMessage from '../components/AnswerMessage.vue'
import AssistantDrawer from '../components/AssistantDrawer.vue'
import {
  ASSISTANT_QUESTION_MIN_LENGTH,
  ASSISTANT_QUESTION_VALIDATION_MESSAGE,
  assistantApi,
  canAskAssistantQuestion,
  canAskGeneralAssistantQuestion,
  canStartAssistantSession,
  canUpdateAssistantValuation,
  mapKnowledgeQuestionResponse,
  safeAssistantErrorMessage,
} from '../assistant.api'
import {
  isUsableAssistantContext,
  mapAssistantQuestion,
  sanitizeAssistantContext,
} from '../assistant.mappers'
import type {
  AssistantAnswerModel,
  AssistantChatMessage,
  AssistantContext,
  AssistantMessageRequestDto,
  AssistantMessageResponseDto,
  AssistantQuestionRequestDto,
  AssistantQuestionResponseDto,
  AssistantSessionModel,
  KnowledgeConversationDto,
} from '../assistant.types'

const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()

const session = ref<AssistantSessionModel | null>(null)
const knowledgeConversationId = ref('')
const knowledgeConversations = ref<KnowledgeConversationDto[]>([])
const messages = ref<AssistantChatMessage[]>([])
const loading = ref(false)
const sending = ref(false)
const error = ref('')
const question = ref('')
const drawerOpen = ref(false)
const drawerTrigger = ref<HTMLButtonElement | null>(null)
const workflowResponse = ref<AssistantMessageResponseDto | null>(null)
const workflowSending = ref(false)
const loadSerial = ref(0)
const messageSerial = ref(0)
let activeController: AbortController | null = null
let activeMessageController: AbortController | null = null
let activeWorkflowController: AbortController | null = null
let skipSessionReload: string | null = null

const routeSessionId = computed(() => {
  const value = route.params.sessionId
  return typeof value === 'string' ? value.trim() : ''
})

const canStartSession = computed(() => canStartAssistantSession(authStore.permissions))
const canAskCaseQuestion = computed(() => canAskAssistantQuestion(authStore.permissions))
const canAskGeneralQuestion = computed(() => canAskGeneralAssistantQuestion(authStore.permissions))
const canUpdateValuation = computed(() => canUpdateAssistantValuation(authStore.permissions))
const canRunWorkflow = computed(() => Boolean(session.value && canUpdateValuation.value))
const permissionKey = computed(() => authStore.permissions.join('|'))
const questionValidationMessage = computed(() => {
  if (!question.value || question.value.trim().length >= ASSISTANT_QUESTION_MIN_LENGTH) return ''
  return ASSISTANT_QUESTION_VALIDATION_MESSAGE
})

function queryValue(...names: string[]): string {
  for (const name of names) {
    const value = route.query[name]
    if (typeof value === 'string' && value.trim()) return value.trim()
  }
  return ''
}

const context = computed<AssistantContext>(() => {
  const acceptedFields = canStartSession.value
    ? (['caseId', 'formId', 'routeName'] as const)
    : (['routeName'] as const)
  return sanitizeAssistantContext(
    {
      caseId: queryValue('caseId', 'case_id'),
      formId: queryValue('formId', 'form_id'),
      routeName: String(route.name ?? 'assistant'),
    },
    acceptedFields,
  )
})

const hasContext = computed(() => isUsableAssistantContext(context.value))
const generalKnowledgeMode = computed(() => !routeSessionId.value && !hasContext.value)
const canAskQuestion = computed(() => (
  session.value
    ? canAskCaseQuestion.value
    : generalKnowledgeMode.value
      && canAskGeneralQuestion.value
      && Boolean(knowledgeConversationId.value)
))
const latestAnswer = computed<AssistantAnswerModel | null>(() => {
  for (let index = messages.value.length - 1; index >= 0; index -= 1) {
    const item = messages.value[index]
    if (item.role === 'assistant' && item.answer) return item.answer
  }
  return null
})
const suggestedQuestions = computed(() => generalKnowledgeMode.value
  ? [
      '土地徵收補償市價查估的主要流程是什麼？',
      '比準地在查估流程中的用途是什麼？',
      '正式查估書通常需要核對哪些資料？',
    ]
  : [
      '目前這筆案件還缺少哪些資料？',
      '這筆案件下一步應該做什麼？',
      '目前有哪些來源文件可以核對？',
    ])
const assistantContextText = computed(() => {
  if (session.value) return '目前案件資料已載入'
  if (generalKnowledgeMode.value) return '可查詢法規、條文與知識文件'
  return '尚未帶入案件資料'
})
const emptyConversationDescription = computed(() => generalKnowledgeMode.value
  ? '可直接詢問法規、條文、查估流程或知識文件內容；回答會附上可核對來源。'
  : '可詢問目前案件缺件、處理進度、來源依據或下一步作業。')

function assistantStepLabel(step: string): string {
  return ({
    COLLECT_FIELDS: '補齊必要欄位',
    COLLECT_DOCUMENTS: '補齊必要文件',
    REVIEW_EXTRACTION: '確認 AI／OCR 辨識結果',
    READY_TO_SUBMIT: '必要資料已齊，可進行後續估價作業',
  } as Record<string, string>)[step] ?? '依目前案件資料接續處理'
}

function isCurrent(serial: number): boolean {
  return serial === loadSerial.value
}

function currentQuery(): Record<string, string> {
  const query: Record<string, string> = {}
  const caseId = context.value.caseId
  const formId = context.value.formId
  if (caseId) query.caseId = caseId
  if (formId) query.formId = formId
  return query
}

const routeConversationId = computed(() => queryValue('conversationId', 'conversation_id'))

function restoreKnowledgeMessages(rows: Awaited<ReturnType<typeof assistantApi.getKnowledgeConversationMessages>>): void {
  messages.value = rows.flatMap((row): AssistantChatMessage[] => {
    if (row.role === 'USER') {
      return [{ id: row.message_id, role: 'user', content: row.content }]
    }
    if (!row.answer) return []
    return [{
      id: row.message_id,
      role: 'assistant',
      answer: mapAssistantQuestion(mapKnowledgeQuestionResponse(row.answer)),
    }]
  })
}

async function loadKnowledgeConversation(controller: AbortController, serial: number): Promise<void> {
  const conversations = await assistantApi.listKnowledgeConversations(controller.signal)
  if (!isCurrent(serial)) return
  knowledgeConversations.value = conversations
  const requestedId = routeConversationId.value
  let selected = conversations.find((item) => item.conversation_id === requestedId) ?? conversations[0]
  if (!selected) {
    selected = await assistantApi.createKnowledgeConversation(controller.signal)
    if (!isCurrent(serial)) return
    knowledgeConversations.value = [selected]
  }
  knowledgeConversationId.value = selected.conversation_id
  const rows = await assistantApi.getKnowledgeConversationMessages(selected.conversation_id, controller.signal)
  if (!isCurrent(serial)) return
  restoreKnowledgeMessages(rows)
  if (routeConversationId.value !== selected.conversation_id) {
    await router.replace({ name: 'assistant', query: { conversationId: selected.conversation_id } })
  }
}

async function createNewKnowledgeConversation(): Promise<void> {
  if (loading.value || sending.value || !canAskGeneralQuestion.value) return
  loading.value = true
  error.value = ''
  try {
    const created = await assistantApi.createKnowledgeConversation()
    knowledgeConversations.value = [created, ...knowledgeConversations.value]
    knowledgeConversationId.value = created.conversation_id
    messages.value = []
    await router.replace({ name: 'assistant', query: { conversationId: created.conversation_id } })
  } catch (caught: unknown) {
    error.value = safeAssistantErrorMessage(caught)
  } finally {
    loading.value = false
  }
}

async function selectKnowledgeConversation(event: Event): Promise<void> {
  const target = event.target as HTMLSelectElement
  const conversationId = target.value
  if (!conversationId || conversationId === knowledgeConversationId.value) return
  await router.replace({ name: 'assistant', query: { conversationId } })
}

function restoreCaseMessages(rows: Awaited<ReturnType<typeof assistantApi.getSessionMessages>>): void {
  messages.value = rows.flatMap((row): AssistantChatMessage[] => {
    if (row.role === 'USER') {
      return [{ id: row.assistant_message_id, role: 'user', content: row.content }]
    }
    const payload = row.response_payload as Partial<AssistantQuestionResponseDto>
    if (!payload.answer_status || typeof payload.answer !== 'string') return []
    return [{
      id: row.assistant_message_id,
      role: 'assistant',
      answer: mapAssistantQuestion(payload as AssistantQuestionResponseDto),
    }]
  })
}

async function loadSession(): Promise<void> {
  const serial = ++loadSerial.value
  const requestedSessionId = routeSessionId.value
  if (requestedSessionId && skipSessionReload === requestedSessionId && session.value?.assistantSessionId === requestedSessionId) {
    skipSessionReload = null
    loading.value = false
    return
  }
  activeController?.abort()
  activeMessageController?.abort()
  activeWorkflowController?.abort()
  const controller = new AbortController()
  activeController = controller
  loading.value = true
  sending.value = false
  workflowSending.value = false
  error.value = ''
  question.value = ''
  drawerOpen.value = false
  messages.value = []
  workflowResponse.value = null
  session.value = null
  knowledgeConversationId.value = ''

  try {
    if (generalKnowledgeMode.value) {
      if (!canAskGeneralQuestion.value) return
      await loadKnowledgeConversation(controller, serial)
      return
    }

    if (!canStartSession.value) return

    if (requestedSessionId) {
      const loaded = await assistantApi.getSession(requestedSessionId, controller.signal)
      if (!isCurrent(serial)) return
      session.value = loaded
      const rows = await assistantApi.getSessionMessages(loaded.assistantSessionId, controller.signal)
      if (!isCurrent(serial)) return
      restoreCaseMessages(rows)
    } else if (hasContext.value) {
      const created = await assistantApi.createSession(context.value, controller.signal)
      if (!isCurrent(serial)) return
      session.value = created
      skipSessionReload = created.assistantSessionId
      await router.replace({
        name: 'assistant-session',
        params: { sessionId: created.assistantSessionId },
        query: currentQuery(),
      })
    }
  } catch (caught: unknown) {
    if (isCurrent(serial) && !controller.signal.aborted) error.value = safeAssistantErrorMessage(caught)
  } finally {
    if (isCurrent(serial)) loading.value = false
  }
}

async function sendQuestion(value = question.value): Promise<void> {
  const content = value.trim()
  const currentSession = session.value
  if (!content || !canAskQuestion.value || sending.value || loading.value) return
  if (content.length < ASSISTANT_QUESTION_MIN_LENGTH) {
    error.value = ASSISTANT_QUESTION_VALIDATION_MESSAGE
    return
  }

  question.value = ''
  error.value = ''
  const messageId = `assistant-user-${++messageSerial.value}`
  messages.value.push({ id: messageId, role: 'user', content })
  sending.value = true
  activeMessageController?.abort()
  const controller = new AbortController()
  activeMessageController = controller
  const serial = loadSerial.value
  const request: AssistantQuestionRequestDto = { question: content }
  try {
    const response = currentSession
      ? await assistantApi.askQuestion(currentSession.assistantSessionId, request, controller.signal)
      : await assistantApi.askKnowledgeConversation(knowledgeConversationId.value, request, controller.signal)
    if (!isCurrent(serial)) return
    if (currentSession && session.value?.assistantSessionId !== currentSession.assistantSessionId) return
    if (!currentSession && !generalKnowledgeMode.value) return
    const answer = mapAssistantQuestion(response)
    messages.value.push({ id: `assistant-answer-${messageSerial.value}`, role: 'assistant', answer })
    if (!currentSession) {
      knowledgeConversations.value = await assistantApi.listKnowledgeConversations(controller.signal)
    }
  } catch (caught: unknown) {
    if (isCurrent(serial) && !controller.signal.aborted) error.value = safeAssistantErrorMessage(caught)
  } finally {
    if (isCurrent(serial) && activeMessageController === controller) sending.value = false
  }
}

function submitQuestion(): void {
  void sendQuestion()
}

type WorkflowAction = 'calculation' | 'validation' | 'report'

const workflowActionLabels: Record<WorkflowAction, string> = {
  calculation: '執行正式計算',
  validation: '執行製作前檢核',
  report: '產生正式報告 PDF',
}

function workflowRequest(action: WorkflowAction): AssistantMessageRequestDto {
  if (action === 'calculation') {
    return { content: workflowActionLabels[action], run_calculation: true, confirm_action: true }
  }
  if (action === 'validation') {
    return { content: workflowActionLabels[action], run_validation: true }
  }
  return { content: workflowActionLabels[action], generate_report_pdf: true, confirm_action: true }
}

async function runWorkflowAction(action: WorkflowAction): Promise<void> {
  const currentSession = session.value
  if (!currentSession || !canRunWorkflow.value || workflowSending.value || loading.value || sending.value) return

  error.value = ''
  workflowResponse.value = null
  workflowSending.value = true
  activeWorkflowController?.abort()
  const controller = new AbortController()
  activeWorkflowController = controller
  const serial = loadSerial.value
  try {
    const response = await assistantApi.sendMessage(
      currentSession.assistantSessionId,
      workflowRequest(action),
      controller.signal,
    )
    if (!isCurrent(serial) || session.value?.assistantSessionId !== currentSession.assistantSessionId) return
    workflowResponse.value = response
  } catch (caught: unknown) {
    if (isCurrent(serial) && !controller.signal.aborted) error.value = safeAssistantErrorMessage(caught)
  } finally {
    if (isCurrent(serial) && activeWorkflowController === controller) workflowSending.value = false
  }
}

function workflowToolLabel(toolName: string): string {
  const labels: Record<string, string> = {
    run_calculation: '正式計算',
    run_validation: '製作前檢核',
    generate_report_pdf: '正式報告 PDF',
  }
  return labels[toolName] ?? '系統作業'
}

function workflowStatusLabel(status: string): string {
  const labels: Record<string, string> = {
    SUCCESS: '已完成',
    PENDING: '等待確認',
    DENIED: '未執行',
    FAILED: '失敗',
  }
  return labels[status] ?? '狀態待確認'
}

function workflowToolSummary(tool: AssistantMessageResponseDto['tools'][number]): string {
  const result = tool.result
  if (!result || typeof result !== 'object' || Array.isArray(result)) return ''
  if (tool.tool_name === 'run_calculation') {
    const value = result.result
    return typeof value === 'string' || typeof value === 'number' ? `計算結果：${value}` : '系統已完成計算。'
  }
  if (tool.tool_name === 'run_validation') {
    const failed = typeof result.failed_count === 'number' ? result.failed_count : null
    const warnings = typeof result.warning_count === 'number' ? result.warning_count : null
    if (failed !== null || warnings !== null) {
      return `檢核結果：錯誤 ${failed ?? 0} 項，警示 ${warnings ?? 0} 項。`
    }
    return '系統已完成製作前檢核。'
  }
  if (tool.tool_name === 'generate_report_pdf') {
    return tool.status === 'SUCCESS' ? '系統已產生正式報告。' : '目前尚未產生正式報告。'
  }
  return ''
}

function openDrawer(): void {
  if (session.value) drawerOpen.value = true
}

function closeDrawer(): void {
  drawerOpen.value = false
  void nextTick(() => {
    void nextTick(() => drawerTrigger.value?.focus())
  })
}

function submitDrawerQuestion(value: string): void {
  drawerOpen.value = false
  void sendQuestion(value)
}

watch(
  [routeSessionId, () => route.query.caseId, () => route.query.case_id, () => route.query.formId, () => route.query.form_id, routeConversationId, permissionKey],
  () => { void loadSession() },
  { immediate: true },
)

onBeforeUnmount(() => {
  activeController?.abort()
  activeMessageController?.abort()
  activeWorkflowController?.abort()
})
</script>

<template>
  <div class="assistant-view" data-testid="assistant-view">
    <PageHeader
      eyebrow="智能助理"
      title="智能助理"
      :description="generalKnowledgeMode
        ? '可直接查詢法規、條文與知識文件，回答會附上可核對來源。'
        : '可針對目前案件提問，並以系統中的案件資料與來源協助核對。'"
      >
      <template #actions>
        <RouterLink
          v-if="session && context.caseId"
          class="assistant-view__case-link"
          data-testid="assistant-return-case"
          :to="{ name: 'valuation-prepare', params: { caseId: context.caseId } }"
        >
          返回目前案件
        </RouterLink>
        <button
          v-if="session"
          class="assistant-view__drawer-button"
          ref="drawerTrigger"
          type="button"
          data-testid="assistant-open-drawer"
          aria-controls="assistant-drawer"
          :aria-expanded="drawerOpen ? 'true' : 'false'"
          @click="openDrawer"
        >
          開啟側邊助理
        </button>
      </template>
    </PageHeader>

    <GlassCard class="assistant-frame">
      <template #title>智能助理問答</template>
      <template #meta>
        {{ generalKnowledgeMode
          ? '只使用知識庫中可核對的來源回答。'
          : '目前已帶入案件資料；回答仍以可核對的系統資料與來源為準。' }}
      </template>

      <LoadingSkeleton v-if="loading" :rows="4" label="正在載入智能助理" />
      <ErrorState v-else-if="error && !session && !generalKnowledgeMode" :message="error" @retry="loadSession" />
      <EmptyState
        v-else-if="!generalKnowledgeMode && !hasContext && !session"
        title="尚未選取可用的比準地地價估計表案件"
        :description="canStartSession ? '請先從可查看的估價案件開啟智能助理。' : '目前帳號沒有查看估價案件的權限。'"
      >
        <template #action>
          <RouterLink class="assistant-view__back-link" to="/app/valuation/dashboard">回到估價作業</RouterLink>
        </template>
      </EmptyState>
      <template v-else>
        <div class="assistant-context" data-testid="assistant-context" role="status">
          <span class="assistant-context__dot" aria-hidden="true" />
          <span>{{ session ? '案件模式' : '知識模式' }}｜{{ assistantContextText }}</span>
          <span v-if="session" class="assistant-context__step">目前進度：{{ assistantStepLabel(session.currentStep) }}</span>
        </div>

        <section class="assistant-mode-guide" data-testid="assistant-mode-guide" aria-label="智能助理使用方式">
          <article :data-active="session ? 'true' : 'false'">
            <strong>案件模式</strong>
            <span>針對目前案件詢問缺件、進度、來源與下一步；可直接返回案件繼續作業。</span>
          </article>
          <article :data-active="generalKnowledgeMode ? 'true' : 'false'">
            <strong>知識模式</strong>
            <span>查詢法規、條文、查估流程與知識文件；回答會附上可核對來源。</span>
          </article>
        </section>

        <div v-if="generalKnowledgeMode" class="assistant-history" data-testid="assistant-history">
          <label for="assistant-history-select">對話紀錄</label>
          <select
            id="assistant-history-select"
            :value="knowledgeConversationId"
            :disabled="loading || sending"
            @change="selectKnowledgeConversation"
          >
            <option
              v-for="item in knowledgeConversations"
              :key="item.conversation_id"
              :value="item.conversation_id"
            >
              {{ item.title }}
            </option>
          </select>
          <button
            type="button"
            :disabled="loading || sending || !canAskGeneralQuestion"
            @click="createNewKnowledgeConversation"
          >
            新增對話
          </button>
        </div>

        <div v-if="error" class="assistant-view__inline-error" role="alert">{{ error }}</div>

        <div class="assistant-conversation" aria-live="polite">
          <div v-if="!messages.length" class="assistant-conversation__empty">
            <strong>請輸入問題</strong>
            <p>{{ emptyConversationDescription }}</p>
            <div class="assistant-conversation__suggestions" aria-label="常用問題">
              <button
                v-for="(suggestion, index) in suggestedQuestions"
                :key="suggestion"
                type="button"
                :data-testid="`assistant-suggestion-${index}`"
                :disabled="!canAskQuestion || sending || loading"
                @click="sendQuestion(suggestion)"
              >
                {{ suggestion }}
              </button>
            </div>
          </div>
          <div v-for="message in messages" :key="message.id" class="assistant-message" :class="`assistant-message--${message.role}`">
            <div v-if="message.role === 'user'" class="assistant-message__user">{{ message.content }}</div>
            <AnswerMessage v-else-if="message.answer" :answer="message.answer" />
          </div>
        </div>

        <form class="assistant-composer" @submit.prevent="submitQuestion">
          <label for="assistant-question">提問內容</label>
          <textarea
            id="assistant-question"
            v-model="question"
            data-testid="assistant-question"
            rows="4"
            maxlength="2000"
            :disabled="!canAskQuestion || loading || sending"
            :aria-invalid="questionValidationMessage ? 'true' : undefined"
            :aria-describedby="questionValidationMessage ? 'assistant-question-validation' : undefined"
            :placeholder="generalKnowledgeMode
              ? '例如：請查詢土地估價相關條文與適用依據。'
              : '例如：請說明目前這筆案件還缺少哪些資料？'"
          />
          <p
            v-if="!canAskQuestion"
            class="assistant-composer__permission"
            data-testid="assistant-permission-required"
            role="status"
          >
            {{ generalKnowledgeMode
              ? '目前帳號沒有查詢法規與知識文件的權限。'
              : '目前帳號沒有查看案件資料與來源文件的權限。' }}
          </p>
          <p
            v-if="questionValidationMessage"
            id="assistant-question-validation"
            class="assistant-composer__validation"
            data-testid="assistant-question-validation"
            role="alert"
          >
            {{ questionValidationMessage }}
          </p>
          <div class="assistant-composer__footer">
            <span>{{ question.length }} / 2000</span>
            <button
              class="assistant-composer__submit"
              type="submit"
              data-testid="assistant-submit"
              :disabled="!canAskQuestion || loading || sending || question.trim().length < ASSISTANT_QUESTION_MIN_LENGTH"
              @click.prevent="submitQuestion"
            >
              {{ sending ? '送出中…' : '送出問題' }}
            </button>
          </div>
        </form>

        <section
          v-if="canRunWorkflow"
          class="assistant-workflow"
          data-testid="assistant-workflow-actions"
          aria-labelledby="assistant-workflow-title"
        >
          <div class="assistant-workflow__heading">
            <div>
              <span class="assistant-workflow__eyebrow">估價作業</span>
              <h3 id="assistant-workflow-title">案件快捷操作</h3>
            </div>
            <p>下列按鈕會直接對目前案件執行作業。系統只使用已確認資料，尚未確認的辨識結果不會自動套用。</p>
          </div>
          <div class="assistant-workflow__actions">
            <button
              type="button"
              data-testid="assistant-workflow-action-calculation"
              :disabled="workflowSending || loading || sending"
              @click="runWorkflowAction('calculation')"
            >
              {{ workflowSending ? '執行中…' : workflowActionLabels.calculation }}
            </button>
            <button
              type="button"
              data-testid="assistant-workflow-action-validation"
              :disabled="workflowSending || loading || sending"
              @click="runWorkflowAction('validation')"
            >
              {{ workflowActionLabels.validation }}
            </button>
            <button
              type="button"
              data-testid="assistant-workflow-action-report"
              :disabled="workflowSending || loading || sending"
              @click="runWorkflowAction('report')"
            >
              {{ workflowActionLabels.report }}
            </button>
          </div>

          <section v-if="workflowResponse" class="assistant-workflow__result" data-testid="assistant-workflow-result" aria-live="polite">
            <h4>處理結果</h4>
            <p>目前進度：{{ assistantStepLabel(workflowResponse.progress.current_step) }}</p>
            <p>
              進度：{{ workflowResponse.progress.completed_items }} / {{ workflowResponse.progress.total_items }}；
              已確認資料 {{ workflowResponse.progress.confirmed_candidate_count }} 筆；
              待確認資料 {{ workflowResponse.progress.pending_candidate_count }} 筆。
            </p>
            <ul v-if="workflowResponse.tools.length" class="assistant-workflow__tools">
              <li v-for="tool in workflowResponse.tools" :key="`${tool.tool_name}-${tool.status}`">
                <strong>{{ workflowToolLabel(tool.tool_name) }}</strong>：{{ workflowStatusLabel(tool.status) }}
                <span v-if="workflowToolSummary(tool)">（{{ workflowToolSummary(tool) }}）</span>
              </li>
            </ul>
          </section>
        </section>
      </template>
    </GlassCard>

    <p class="assistant-disclaimer">AI 建議僅供輔助，最終由專業人員判斷。</p>

    <AssistantDrawer
      :open="drawerOpen"
      :answer="latestAnswer"
      :loading="loading"
      :sending="sending"
      :error="error"
      :can-ask="canAskQuestion"
      @close="closeDrawer"
      @submit="submitDrawerQuestion"
    />
  </div>
</template>

<style scoped>
.assistant-view {
  display: grid;
  gap: 4px;
  padding: 0 28px 34px;
}

.assistant-frame {
  display: grid;
  gap: 20px;
  padding: 24px;
}

.assistant-frame :deep(.lg-card__title) {
  margin-bottom: 3px;
  font-size: 20px;
}

.assistant-frame :deep(.lg-card__meta) {
  margin-bottom: 0;
}

.assistant-view__drawer-button,
.assistant-composer__submit {
  min-height: 44px;
  padding: 9px 15px;
  border: 1px solid var(--app-accent);
  border-radius: 9px;
  color: #fff;
  background: var(--app-accent);
  cursor: pointer;
  font-size: 13px;
  font-weight: 800;
}

.assistant-view__case-link {
  display: inline-flex;
  min-height: 44px;
  align-items: center;
  padding: 9px 14px;
  border: 1px solid var(--app-line);
  border-radius: 9px;
  color: var(--app-ink-soft);
  background: var(--app-paper-strong);
  font-size: 12px;
  font-weight: 800;
  text-decoration: none;
}
.assistant-view__case-link:hover { border-color: var(--app-accent); color: var(--app-accent-deep); }

.assistant-view__drawer-button:hover,
.assistant-composer__submit:hover:not(:disabled) { background: var(--app-accent-deep); }

.assistant-view__drawer-button:disabled,
.assistant-composer__submit:disabled { cursor: not-allowed; opacity: 0.55; }

.assistant-context {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 9px;
  min-height: 44px;
  padding: 10px 13px;
  border: 1px solid #dce9e1;
  border-radius: 9px;
  color: var(--app-green);
  background: #f3faf5;
  font-size: 13px;
  font-weight: 800;
}

.assistant-context__dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--app-green);
}

.assistant-context__step {
  margin-left: auto;
  color: var(--app-ink-soft);
  font-size: 12px;
  font-weight: 600;
}

.assistant-mode-guide { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; }
.assistant-mode-guide article { display: grid; gap: 4px; padding: 12px 14px; border: 1px solid var(--app-line); border-radius: 10px; background: #fafbfd; }
.assistant-mode-guide article[data-active="true"] { border-color: #bfd0e2; background: #f4f8fc; box-shadow: inset 3px 0 0 #2e5984; }
.assistant-mode-guide strong { color: var(--app-ink); font-size: 12px; }
.assistant-mode-guide span { color: var(--app-muted); font-size: 10px; line-height: 1.55; }

.assistant-history {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) auto;
  align-items: center;
  gap: 10px;
  padding: 12px 14px;
  border: 1px solid var(--app-line);
  border-radius: 10px;
  background: var(--app-paper-strong);
}

.assistant-history label {
  color: var(--app-ink);
  font-size: 12px;
  font-weight: 800;
}

.assistant-history select,
.assistant-history button {
  min-height: 40px;
  border: 1px solid var(--app-line);
  border-radius: 8px;
  background: #fff;
  font: inherit;
}

.assistant-history select { padding: 7px 10px; color: var(--app-ink); }
.assistant-history button {
  padding: 7px 13px;
  color: var(--app-accent-deep);
  cursor: pointer;
  font-size: 12px;
  font-weight: 800;
}
.assistant-history button:disabled { cursor: not-allowed; opacity: .55; }

.assistant-view__inline-error {
  padding: 12px 14px;
  border: 1px solid #efcfca;
  border-radius: 9px;
  color: #8a3c34;
  background: #fff5f3;
  font-size: 13px;
  line-height: 1.6;
}

.assistant-conversation {
  display: grid;
  gap: 14px;
  min-height: 140px;
  max-height: 640px;
  overflow: auto;
  padding: 4px;
}

.assistant-conversation__empty {
  display: grid;
  gap: 7px;
  place-items: center;
  min-height: 150px;
  border: 1px dashed var(--app-line);
  border-radius: 10px;
  color: var(--app-ink-soft);
  background: var(--app-paper-strong);
  text-align: center;
}

.assistant-conversation__empty strong,
.assistant-conversation__empty p { margin: 0; }

.assistant-conversation__empty strong { color: var(--app-ink); }
.assistant-conversation__empty p { font-size: 13px; }
.assistant-conversation__suggestions { display: flex; flex-wrap: wrap; justify-content: center; gap: 8px; max-width: 760px; margin-top: 8px; }
.assistant-conversation__suggestions button { min-height: 38px; padding: 7px 11px; border: 1px solid #d8e1eb; border-radius: 999px; color: #2e5984; background: #f7fbff; cursor: pointer; font-size: 11px; font-weight: 800; }
.assistant-conversation__suggestions button:hover:not(:disabled) { border-color: #9eb7d0; background: #edf4fb; }
.assistant-conversation__suggestions button:disabled { cursor: not-allowed; opacity: .5; }

.assistant-message--user {
  justify-self: end;
  max-width: min(78%, 640px);
}

.assistant-message__user {
  padding: 12px 15px;
  border: 1px solid #e8d2c6;
  border-radius: 13px 13px 3px 13px;
  color: var(--app-ink);
  background: #fff6f0;
  line-height: 1.7;
  white-space: pre-wrap;
}

.assistant-message--assistant { min-width: 0; }

.assistant-composer {
  display: grid;
  gap: 8px;
  padding: 16px;
  border: 1px solid var(--app-line);
  border-radius: 10px;
  background: var(--app-paper-strong);
}

.assistant-composer label {
  color: var(--app-ink);
  font-size: 13px;
  font-weight: 800;
}

.assistant-composer textarea {
  width: 100%;
  min-height: 100px;
  padding: 11px 12px;
  border: 1px solid var(--app-line);
  border-radius: 8px;
  color: var(--app-ink);
  background: #fff;
  font: inherit;
  line-height: 1.6;
  resize: vertical;
}

.assistant-composer textarea:focus {
  border-color: var(--app-accent);
  outline: 2px solid rgba(200, 91, 67, 0.18);
  outline-offset: 1px;
}

.assistant-composer__permission {
  margin: 0;
  color: var(--app-muted);
  font-size: 12px;
  line-height: 1.5;
}

.assistant-composer__validation {
  margin: 0;
  color: #8a3c34;
  font-size: 12px;
  line-height: 1.5;
}

.assistant-workflow {
  display: grid;
  gap: 14px;
  padding: 17px;
  border: 1px solid #d8e1ee;
  border-radius: 10px;
  background: #f8fbff;
}

.assistant-workflow__heading {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
}

.assistant-workflow__heading h3,
.assistant-workflow__heading p,
.assistant-workflow__result h4,
.assistant-workflow__result p {
  margin: 0;
}

.assistant-workflow__heading h3,
.assistant-workflow__result h4 {
  color: var(--app-ink);
  font-size: 15px;
}

.assistant-workflow__heading p {
  max-width: 390px;
  color: var(--app-muted);
  font-size: 12px;
  line-height: 1.55;
  text-align: right;
}

.assistant-workflow__eyebrow {
  display: block;
  margin-bottom: 3px;
  color: var(--app-violet);
  font-size: 10px;
  font-weight: 800;
  letter-spacing: 0.14em;
}

.assistant-workflow__actions {
  display: flex;
  flex-wrap: wrap;
  gap: 9px;
}

.assistant-workflow__actions button {
  min-height: 42px;
  padding: 8px 13px;
  border: 1px solid #c5d2e2;
  border-radius: 8px;
  color: var(--app-ink);
  background: #fff;
  cursor: pointer;
  font: inherit;
  font-size: 12px;
  font-weight: 800;
}

.assistant-workflow__actions button:hover:not(:disabled),
.assistant-workflow__actions button:focus-visible {
  border-color: var(--app-accent);
  outline: 2px solid rgba(200, 91, 67, 0.18);
  outline-offset: 2px;
}

.assistant-workflow__actions button:first-child {
  border-color: var(--app-accent);
  color: #fff;
  background: var(--app-accent);
}

.assistant-workflow__actions button:first-child:hover:not(:disabled) { background: var(--app-accent-deep); }
.assistant-workflow__actions button:disabled { cursor: not-allowed; opacity: 0.55; }

.assistant-workflow__result {
  display: grid;
  gap: 7px;
  padding-top: 13px;
  border-top: 1px solid #d8e1ee;
  color: var(--app-ink-soft);
  font-size: 12px;
  line-height: 1.55;
}

.assistant-workflow__tools {
  display: grid;
  gap: 5px;
  margin: 2px 0 0;
  padding-left: 18px;
}

.assistant-workflow__tools li::marker { color: var(--app-accent); }

.assistant-composer__footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  color: var(--app-muted);
  font-size: 11px;
}

.assistant-disclaimer {
  margin: 0 4px;
  color: var(--app-muted);
  font-size: 12px;
  line-height: 1.6;
}

.assistant-view__back-link {
  color: var(--app-accent-deep);
  font-weight: 800;
  text-decoration: none;
}

.assistant-view__back-link:hover { text-decoration: underline; }

@media (max-width: 640px) {
  .assistant-view { padding: 0 16px 26px; }
  .assistant-frame { padding: 16px; }
  .assistant-context__step { width: 100%; margin-left: 0; }
  .assistant-message--user { max-width: 92%; }
  .assistant-workflow__heading { display: grid; }
  .assistant-workflow__heading p { max-width: none; text-align: left; }
  .assistant-workflow__actions button { flex: 1 1 100%; }
}
</style>
