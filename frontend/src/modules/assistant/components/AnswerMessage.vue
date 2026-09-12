<script setup lang="ts">
import { computed, ref } from 'vue'
import CitationPanel from './CitationPanel.vue'
import type { AssistantAnswerModel } from '../assistant.types'

const props = defineProps<{
  answer: AssistantAnswerModel
}>()

const selectedCitationId = ref<string | null>(null)
const selectedCitation = computed(() => {
  if (!selectedCitationId.value) return null
  return props.answer.citations.find((citation) => citation.citationId === selectedCitationId.value) ?? null
})
const selectedCitationIndex = computed(() => {
  if (!selectedCitationId.value) return -1
  return props.answer.citations.findIndex((citation) => citation.citationId === selectedCitationId.value)
})

function citationIndex(citationId: string): number {
  return props.answer.citations.findIndex((citation) => citation.citationId === citationId)
}

function selectCitation(citationId: string): void {
  if (citationIndex(citationId) < 0) return
  selectedCitationId.value = citationId
}
</script>

<template>
  <article class="answer-message" data-testid="assistant-answer">
    <div class="answer-message__heading">
      <span class="answer-message__eyebrow">回答</span>
      <h3>智能助理回應</h3>
    </div>

    <div v-if="answer.supported && answer.text" class="answer-message__body">
      <p class="answer-message__text">{{ answer.text }}</p>
      <div
        v-if="answer.answerRoute === 'CASE' || answer.answerRoute === 'HYBRID'"
        class="answer-message__system-source"
        data-testid="assistant-case-source"
      >
        <strong>系統來源</strong>
        <span>系統中已授權的結構化資料</span>
      </div>
      <p v-for="(claim, claimIndex) in answer.claims" :key="`${claimIndex}-${claim.text}`" class="answer-message__claim">
        <span>{{ claim.text }}</span>
        <button
          v-for="citationId in claim.citationIds"
          :key="citationId"
          type="button"
          class="answer-message__citation"
          :data-testid="`assistant-citation-${citationIndex(citationId) + 1}`"
          :data-citation-id="citationId"
          :aria-label="`開啟來源 ${citationIndex(citationId) + 1}`"
          @click="selectCitation(citationId)"
        >
          來源 {{ citationIndex(citationId) + 1 }}
        </button>
      </p>
    </div>

    <p v-if="!answer.supported" class="answer-message__insufficient" data-testid="assistant-insufficient">
      目前沒有足夠的可讀適用來源，無法支持這項回答。
    </p>

    <CitationPanel
      v-if="selectedCitation && selectedCitationIndex >= 0"
      :citation="selectedCitation"
      :index="selectedCitationIndex + 1"
    />
  </article>
</template>

<style scoped>
.answer-message {
  display: grid;
  gap: 16px;
  padding: 22px;
  border: 1px solid var(--app-line);
  border-radius: var(--app-radius-sm);
  background: var(--app-paper-strong);
  color: var(--app-ink);
  box-shadow: var(--app-shadow-soft);
}

.answer-message__heading {
  display: grid;
  gap: 4px;
}

.answer-message__eyebrow {
  color: var(--app-violet);
  font-size: 10px;
  font-weight: 800;
  letter-spacing: 0.16em;
}

.answer-message h3 {
  margin: 0;
  font-size: 17px;
}

.answer-message__body {
  display: grid;
  gap: 11px;
  padding: 16px;
  border: 1px solid #e8edf4;
  border-radius: 10px;
  background: var(--app-paper-strong);
  line-height: 1.8;
}

.answer-message__body--unverified {
  border-color: #f0d8c9;
  background: #fffaf7;
}

.answer-message__claim {
  margin: 0;
  white-space: pre-wrap;
}

.answer-message__text {
  margin: 0;
  white-space: pre-wrap;
}

.answer-message__system-source {
  display: flex;
  align-items: center;
  gap: 8px;
  width: fit-content;
  padding: 6px 9px;
  border: 1px solid #dce5ee;
  border-radius: 8px;
  color: var(--app-ink-soft);
  background: #f7f9fb;
  font-size: 11px;
}

.answer-message__system-source strong { color: var(--app-ink); }

.answer-message__citation {
  display: inline-flex;
  min-height: 28px;
  margin-left: 7px;
  padding: 3px 8px;
  border: 1px solid #d9c8e9;
  border-radius: var(--app-radius-pill);
  color: var(--app-violet);
  background: #f6f1fb;
  cursor: pointer;
  font-size: 11px;
  font-weight: 800;
  vertical-align: baseline;
}

.answer-message__citation:hover,
.answer-message__citation:focus-visible {
  border-color: var(--app-violet);
  outline: 2px solid rgba(116, 104, 143, 0.22);
  outline-offset: 2px;
}

.answer-message__insufficient {
  margin: 0;
  padding: 13px 15px;
  border: 1px solid #efd8c8;
  border-radius: 10px;
  color: #7d432e;
  background: #fff5ee;
  font-size: 13px;
  line-height: 1.6;
}
</style>
