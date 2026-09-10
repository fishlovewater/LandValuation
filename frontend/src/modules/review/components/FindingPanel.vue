<script setup lang="ts">
import { ref, watch } from 'vue'
import EmptyState from '../../../components/common/EmptyState.vue'
import GlassField from '../../../components/glass/GlassField.vue'
import type { FindingTriageDecision, ReviewDecisionModel, ReviewFindingModel } from '../review.types'

const props = withDefaults(
  defineProps<{
    finding: ReviewFindingModel | null
    decision?: ReviewDecisionModel | null
    canDecide?: boolean
    canTriage?: boolean
    readonlyReason?: string
    saving?: boolean
  }>(),
  {
    decision: null,
    canDecide: false,
    canTriage: false,
    readonlyReason: '目前案件狀態或疑點狀態不允許再次判定。',
    saving: false,
  },
)

const emit = defineEmits<{
  save: [value: { findingId: string; decision: FindingTriageDecision; reason: string }]
}>()

const decisionCode = ref<FindingTriageDecision>('CONFIRMED_ISSUE')
const reason = ref('')
const validationMessage = ref('')

watch(
  () => props.finding?.findingId,
  () => {
    decisionCode.value = 'CONFIRMED_ISSUE'
    reason.value = props.decision?.reason ?? ''
    validationMessage.value = ''
  },
  { immediate: true },
)

watch(
  () => props.decision,
  (decision) => {
    if (decision) {
      decisionCode.value =
        decision.decisionCode === 'DISMISSED_FALSE_POSITIVE' || decision.decisionCode === 'EXPERT_REVIEW'
          ? decision.decisionCode
          : 'CONFIRMED_ISSUE'
      reason.value = decision.reason ?? ''
    }
  },
)

function display(value: string | null): string {
  return value?.trim() ? value : '—'
}

function save(): void {
  if (!props.finding || !props.canTriage || props.saving) return
  const trimmed = reason.value.trim()
  if (!trimmed) {
    validationMessage.value = '請填寫審查理由。'
    return
  }
  validationMessage.value = ''
  emit('save', { findingId: props.finding.findingId, decision: decisionCode.value, reason: trimmed })
}
</script>

<template>
  <section class="finding-panel" data-testid="finding-panel" aria-label="疑點內容">
    <EmptyState
      v-if="!finding"
      title="尚未選取疑點"
      description="從左側疑點清單選取一筆，查看報告值、系統值與 AI 說明。"
    />
    <template v-else>
      <header class="finding-panel__header">
        <div>
          <p class="finding-panel__eyebrow">疑點：{{ finding.findingCodeLabel }}</p>
          <h2>{{ finding.title }}</h2>
        </div>
        <span class="finding-panel__severity" :data-severity="finding.severityCode">
          {{ finding.severityLabel }}
        </span>
      </header>

      <p class="finding-panel__description">{{ finding.description }}</p>

      <div class="finding-panel__facts">
        <div class="finding-panel__fact">
          <span>疑點狀態</span>
          <strong>{{ finding.statusLabel }}</strong>
        </div>
        <div class="finding-panel__fact">
          <span>對照欄位</span>
          <strong>{{ finding.fieldPathLabel }}</strong>
        </div>
      </div>
      <details class="finding-panel__technical">
        <summary>查看技術細節</summary>
        <dl>
          <div><dt>疑點代碼</dt><dd>{{ finding.findingCode }}</dd></div>
          <div><dt>檢核類型</dt><dd>{{ finding.findingTypeLabel }}</dd></div>
          <div><dt>欄位路徑</dt><dd>{{ display(finding.fieldPath) }}</dd></div>
        </dl>
      </details>

      <section class="finding-panel__section" aria-labelledby="finding-values-title">
        <h3 id="finding-values-title">資料對照</h3>
        <div class="finding-panel__comparison">
          <article class="finding-panel__value-card">
            <span>報告值</span>
            <strong data-testid="report-value">{{ display(finding.reportedValue ?? finding.reportedText) }}</strong>
            <small>送審報告中的原始內容</small>
          </article>
          <article class="finding-panel__value-card finding-panel__value-card--system">
            <span>系統值</span>
            <strong data-testid="system-value">{{ display(finding.systemValue) }}</strong>
            <small>伺服器規則結果，唯讀</small>
          </article>
        </div>
        <div v-if="finding.reportedGrade || finding.systemGrade" class="finding-panel__subvalues">
          <span>報告等級：{{ display(finding.reportedGrade) }}</span>
          <span>系統等級：{{ display(finding.systemGrade) }}</span>
        </div>
      </section>

      <section class="finding-panel__section" aria-labelledby="finding-ai-title">
        <h3 id="finding-ai-title">AI 說明</h3>
        <div class="finding-panel__ai">
          <span class="finding-panel__ai-status">{{ finding.aiStatusLabel }}</span>
          <p data-testid="ai-explanation">{{ display(finding.aiReasoningSummary) }}</p>
          <small v-if="finding.aiConfidence">信心：{{ finding.aiConfidence }}</small>
        </div>
      </section>

      <section
        v-if="finding.sourceEvidence.length || finding.legalBasis.length"
        class="finding-panel__section"
        aria-labelledby="finding-references-title"
      >
        <h3 id="finding-references-title">來源與引用依據</h3>
        <div class="finding-panel__references">
          <article v-for="reference in finding.sourceEvidence" :key="reference.key" class="finding-panel__reference">
            <span>{{ reference.title }}</span>
            <strong v-if="reference.detail">{{ reference.detail }}</strong>
            <small>
              <template v-if="reference.pageNumber">第 {{ reference.pageNumber }} 頁</template>
              <template v-if="reference.documentVersion"> · 文件 v{{ reference.documentVersion }}</template>
              <template v-if="reference.verificationStatus"> · {{ reference.verificationStatus }}</template>
            </small>
          </article>
          <article v-for="reference in finding.legalBasis" :key="reference.key" class="finding-panel__reference finding-panel__reference--legal">
            <span>{{ reference.title }}</span>
            <strong v-if="reference.detail">{{ reference.detail }}</strong>
            <small v-if="reference.documentVersion">規則來源文件 v{{ reference.documentVersion }}</small>
          </article>
        </div>
      </section>

      <section class="finding-panel__section" aria-labelledby="finding-decision-title">
        <h3 id="finding-decision-title">審查結論</h3>
        <p v-if="decision" class="finding-panel__saved">
          已保存：{{ decision.decisionLabel }}<span v-if="decision.reason">，{{ decision.reason }}</span>
        </p>
        <div class="finding-panel__decision-form">
          <label class="finding-panel__select-label" for="finding-decision">選擇結論</label>
          <select id="finding-decision" v-model="decisionCode" :disabled="!canTriage || saving">
            <option value="CONFIRMED_ISSUE">確認問題</option>
            <option value="DISMISSED_FALSE_POSITIVE">排除誤報</option>
            <option value="EXPERT_REVIEW">轉交專家審查</option>
          </select>
          <GlassField
            id="finding-reason"
            v-model="reason"
            label="審查理由（必填）"
            hint="理由會原樣送交伺服器保存。"
            as="textarea"
            :rows="4"
            surface="solid"
            :disabled="!canTriage || saving"
            :invalid="Boolean(validationMessage)"
            data-testid="finding-reason"
          />
          <p v-if="validationMessage" class="finding-panel__error" role="alert">{{ validationMessage }}</p>
          <p v-if="!canTriage" class="finding-panel__readonly">{{ readonlyReason }}</p>
          <button
            type="button"
            class="finding-panel__save"
            data-testid="save-finding-decision"
            :disabled="!canTriage || saving"
            @click="save"
          >
            {{ saving ? '保存中…' : '保存審查結論' }}
          </button>
        </div>
      </section>
    </template>
  </section>
</template>

<style scoped>
.finding-panel {
  display: grid;
  gap: 18px;
  padding: 20px;
  color: var(--app-ink);
}

.finding-panel__header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}

.finding-panel__eyebrow {
  margin: 0 0 6px;
  color: var(--app-accent-deep);
  font-size: 10px;
  font-weight: 900;
  letter-spacing: 0.15em;
}

.finding-panel h2 {
  margin: 0;
  color: var(--app-ink);
  font-family: var(--app-font-display);
  font-size: 23px;
  line-height: 1.35;
}

.finding-panel__severity,
.finding-panel__ai-status {
  display: inline-flex;
  min-height: 28px;
  align-items: center;
  padding: 4px 9px;
  border-radius: var(--app-radius-pill);
  color: #8d4136;
  background: #fcecea;
  font-size: 11px;
  font-weight: 800;
  white-space: nowrap;
}

.finding-panel__description {
  margin: 0;
  color: var(--app-ink-soft);
  font-size: 14px;
  line-height: 1.7;
}

.finding-panel__facts,
.finding-panel__comparison {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
}

.finding-panel__technical { color: var(--app-muted); font-size: 11px; }
.finding-panel__technical summary { cursor: pointer; font-weight: 800; }
.finding-panel__technical dl { display: grid; gap: 5px; margin: 8px 0 0; }
.finding-panel__technical dl div { display: flex; justify-content: space-between; gap: 12px; }
.finding-panel__technical dt { font-weight: 700; }
.finding-panel__technical dd { margin: 0; color: var(--app-ink-soft); overflow-wrap: anywhere; text-align: right; }

.finding-panel__fact,
.finding-panel__value-card,
.finding-panel__ai {
  display: grid;
  gap: 5px;
  padding: 12px;
  border: 1px solid var(--app-line);
  border-radius: 8px;
  background: var(--app-paper-strong);
}

.finding-panel__fact span,
.finding-panel__value-card span,
.finding-panel__value-card small,
.finding-panel__ai small {
  color: var(--app-muted);
  font-size: 11px;
}

.finding-panel__fact strong,
.finding-panel__value-card strong {
  color: var(--app-ink);
  font-size: 14px;
  overflow-wrap: anywhere;
}

.finding-panel__value-card--system { border-color: #b9cee4; background: #f3f7fb; }
.finding-panel__section { display: grid; gap: 10px; }
.finding-panel__section h3 { margin: 0; font-size: 15px; }
.finding-panel__subvalues { display: flex; flex-wrap: wrap; gap: 8px 16px; color: var(--app-ink-soft); font-size: 12px; }
.finding-panel__ai { color: var(--app-ink-soft); }
.finding-panel__ai p { margin: 0; line-height: 1.65; }
.finding-panel__ai-status { justify-self: start; color: var(--app-green); background: #e5f2eb; }
.finding-panel__references { display: grid; gap: 8px; }
.finding-panel__reference { display: grid; gap: 4px; padding: 11px 12px; border: 1px solid #c8d8e8; border-radius: 9px; background: #f4f8fc; }
.finding-panel__reference--legal { border-color: rgba(200, 91, 67, .22); background: #fff8f4; }
.finding-panel__reference span { color: var(--app-blue); font-size: 11px; font-weight: 900; }
.finding-panel__reference--legal span { color: var(--app-accent-deep); }
.finding-panel__reference strong { color: var(--app-ink); font-size: 12px; line-height: 1.55; overflow-wrap: anywhere; }
.finding-panel__reference small { color: var(--app-muted); font-size: 10px; }
.finding-panel__saved { margin: 0; color: var(--app-green); font-size: 13px; line-height: 1.6; }

.finding-panel__decision-form { display: grid; gap: 9px; }
.finding-panel__select-label { color: var(--app-ink-soft); font-size: 12px; font-weight: 800; }
.finding-panel__decision-form select { min-height: 46px; padding: 8px 12px; border: 1px solid var(--app-line); border-radius: 8px; color: var(--app-ink); background: var(--app-paper-strong); }
.finding-panel__error { margin: 0; color: #ac3c37; font-size: 12px; }
.finding-panel__readonly { margin: 0; color: var(--app-muted); font-size: 12px; }
.finding-panel__save { min-height: 46px; border: 1px solid var(--app-accent); border-radius: 8px; color: #fff8f2; background: var(--app-accent); cursor: pointer; font-weight: 800; }
.finding-panel__save:hover:not(:disabled) { background: var(--app-accent-deep); }
.finding-panel__save:disabled { cursor: not-allowed; opacity: 0.55; }

@media (max-width: 640px) {
  .finding-panel { padding: 14px; }
  .finding-panel__facts, .finding-panel__comparison { grid-template-columns: 1fr; }
}
</style>
