<script setup lang="ts">
import {
  PhArrowRight as ArrowRight,
  PhWarningCircle as WarningCircle,
} from '@phosphor-icons/vue'
import type { ValuationReviewHandoffDto } from '../valuation.types'

type CorrectionItem = NonNullable<ValuationReviewHandoffDto['correction']>['items'][number]
type MissingItem = ValuationReviewHandoffDto['missing_items'][number]

const props = defineProps<{
  handoff: ValuationReviewHandoffDto | null
  supplementMissingItems: MissingItem[]
  revisionDraftReady: boolean
  revisionInitializing: boolean
}>()

const emit = defineEmits<{
  prepareRevision: []
  openRevisionFields: []
  correctionItem: [item: CorrectionItem]
  missingItem: [item: MissingItem]
}>()
</script>

<template>
  <section
    v-if="props.handoff?.correction"
    class="review-handoff review-handoff--correction"
    data-testid="valuation-correction-request"
    aria-labelledby="revision-panel-title"
  >
    <div class="review-handoff__heading">
      <div class="review-handoff__title">
        <WarningCircle :size="20" weight="duotone" aria-hidden="true" />
        <div>
          <p>補正要求</p>
          <h2 id="revision-panel-title">第 {{ props.handoff.correction.request_no }} 次補正要求</h2>
        </div>
      </div>
      <span class="review-handoff__deadline">{{ new Date(props.handoff.correction.due_at).toLocaleString('zh-TW') }} 前</span>
    </div>

    <p class="review-handoff__message">{{ props.handoff.correction.message }}</p>

    <ul class="review-handoff__items">
      <li v-for="item in props.handoff.correction.items" :key="`${item.finding_code}-${item.document_id ?? 'case'}`">
        <div>
          <strong>{{ item.issue_summary }}</strong>
          <span>要求修正：{{ item.requested_correction }}</span>
          <small v-if="item.page_number">文件頁次：第 {{ item.page_number }} 頁</small>
        </div>
        <button type="button" @click="emit('correctionItem', item)">
          <span>{{ item.document_id ? '前往文件處理' : '前往資料修正' }}</span>
          <ArrowRight :size="14" weight="bold" aria-hidden="true" />
        </button>
      </li>
    </ul>

    <div v-if="props.supplementMissingItems.length" class="review-handoff__missing">
      <strong>審查缺件</strong>
      <span v-for="item in props.supplementMissingItems" :key="item.item_code">
        {{ item.item_name }}{{ item.reason ? `：${item.reason}` : '' }}
      </span>
    </div>

    <div class="review-handoff__actions">
      <button
        v-if="!props.revisionDraftReady"
        class="review-handoff__primary"
        type="button"
        data-testid="prepare-revision-draft"
        :disabled="props.revisionInitializing"
        @click="emit('prepareRevision')"
      >
        <span>{{ props.revisionInitializing ? '建立補正版中…' : '建立補正版並帶入前一版資料' }}</span>
        <ArrowRight v-if="!props.revisionInitializing" :size="15" weight="bold" aria-hidden="true" />
      </button>
      <button
        v-else
        class="review-handoff__primary"
        type="button"
        data-testid="open-revision-fields"
        @click="emit('openRevisionFields')"
      >
        <span>補正版已建立，開始修正</span>
        <ArrowRight :size="15" weight="bold" aria-hidden="true" />
      </button>
      <small>舊送審版本保持不可變；補正會建立較新的比準地地價估計表與正式報告版本。</small>
    </div>
  </section>

  <section
    v-else-if="props.supplementMissingItems.length"
    class="review-handoff review-handoff--supplement"
    data-testid="valuation-supplement-request"
    aria-labelledby="supplement-panel-title"
  >
    <div class="review-handoff__heading">
      <div class="review-handoff__title">
        <WarningCircle :size="20" weight="duotone" aria-hidden="true" />
        <div>
          <p>補件要求</p>
          <h2 id="supplement-panel-title">審查補件要求</h2>
        </div>
      </div>
      <span class="review-handoff__count">{{ props.supplementMissingItems.length }} 項待補</span>
    </div>

    <p class="review-handoff__intro">審查端已完成完整性檢查並提出補件要求。請逐項補齊後，再依正常送審流程建立新版送審文件。</p>

    <ul class="review-handoff__items">
      <li v-for="item in props.supplementMissingItems" :key="item.item_code">
        <div>
          <strong>{{ item.item_name }}</strong>
          <span v-if="item.reason">{{ item.reason }}</span>
          <small v-if="item.due_at">期限：{{ new Date(item.due_at).toLocaleString('zh-TW') }}</small>
        </div>
        <button type="button" @click="emit('missingItem', item)">
          <span>{{ item.document_type ? '前往文件補件' : '前往資料補正' }}</span>
          <ArrowRight :size="14" weight="bold" aria-hidden="true" />
        </button>
      </li>
    </ul>
  </section>
</template>

<style scoped>
.review-handoff {
  display: grid;
  gap: 14px;
  padding: 20px;
  border: 1px solid var(--app-line);
  border-radius: 12px;
  background: #fff;
}

.review-handoff--correction {
  border-color: rgba(200, 91, 67, .26);
  background: #fff8f5;
}

.review-handoff--supplement {
  border-color: rgba(214, 166, 62, .32);
  background: #fffbf2;
}

.review-handoff__heading {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
}

.review-handoff__title {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  min-width: 0;
  color: var(--app-accent-deep);
}

.review-handoff__title > div {
  display: grid;
  gap: 4px;
}

.review-handoff__title p {
  margin: 0;
  color: var(--app-accent-deep);
  font-size: 10px;
  font-weight: 850;
  letter-spacing: .1em;
}

.review-handoff__title h2 {
  margin: 0;
  color: var(--app-ink);
  font-family: var(--app-font-display);
  font-size: 20px;
  font-weight: 650;
}

.review-handoff__deadline,
.review-handoff__count {
  flex: 0 0 auto;
  padding: 6px 9px;
  border-radius: 999px;
  font-size: 10px;
  font-weight: 900;
  white-space: nowrap;
}

.review-handoff__deadline {
  color: #a44334;
  background: #fff0ed;
}

.review-handoff__count {
  color: #8c621d;
  background: #fff1cf;
}

.review-handoff__message,
.review-handoff__intro {
  margin: 0;
  color: var(--app-ink-soft);
  font-size: 12px;
  line-height: 1.65;
}

.review-handoff__message {
  color: var(--app-ink);
  font-weight: 700;
  white-space: pre-line;
}

.review-handoff__items {
  display: grid;
  gap: 8px;
  margin: 0;
  padding: 0;
  list-style: none;
}

.review-handoff__items li {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 14px;
  padding: 11px 12px;
  border: 1px solid rgba(148, 163, 184, .22);
  border-radius: 9px;
  background: rgba(255, 255, 255, .86);
}

.review-handoff--correction .review-handoff__items li {
  border-left: 4px solid #c85b43;
}

.review-handoff__items li > div {
  display: grid;
  gap: 4px;
  min-width: 0;
}

.review-handoff__items strong {
  color: var(--app-ink);
  font-size: 12px;
}

.review-handoff__items span {
  color: var(--app-ink-soft);
  font-size: 11px;
  line-height: 1.55;
}

.review-handoff__items small {
  color: var(--app-muted);
  font-size: 10px;
}

.review-handoff__items button,
.review-handoff__primary {
  display: inline-flex;
  min-height: 38px;
  flex: 0 0 auto;
  align-items: center;
  justify-content: center;
  gap: 6px;
  padding: 7px 11px;
  border-radius: 8px;
  cursor: pointer;
  font-size: 11px;
  font-weight: 900;
}

.review-handoff__items button {
  border: 1px solid rgba(46, 89, 132, .26);
  color: #244d73;
  background: #fff;
}

.review-handoff__missing {
  display: grid;
  gap: 5px;
  padding: 11px 12px;
  border: 1px solid rgba(214, 166, 62, .28);
  border-radius: 9px;
  background: #fffaf0;
}

.review-handoff__missing strong {
  color: var(--app-ink);
  font-size: 11px;
}

.review-handoff__missing span {
  color: var(--app-ink-soft);
  font-size: 11px;
}

.review-handoff__actions {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 10px;
}

.review-handoff__actions small {
  color: var(--app-muted);
  font-size: 11px;
  line-height: 1.5;
}

.review-handoff__primary {
  border: 1px solid var(--app-accent);
  color: #fff;
  background: var(--app-accent);
}

.review-handoff__primary:disabled {
  cursor: not-allowed;
  opacity: .55;
}

@media (max-width: 760px) {
  .review-handoff {
    padding: 16px;
  }

  .review-handoff__heading,
  .review-handoff__items li,
  .review-handoff__actions {
    align-items: stretch;
    flex-direction: column;
  }

  .review-handoff__deadline,
  .review-handoff__count {
    width: fit-content;
  }

  .review-handoff__items button,
  .review-handoff__primary {
    width: 100%;
  }
}
</style>
