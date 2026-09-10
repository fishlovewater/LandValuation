<script setup lang="ts">
import { computed, getCurrentInstance } from 'vue'
import GlassModal from '../glass/GlassModal.vue'

const props = withDefaults(
  defineProps<{
    open?: boolean
    title: string
    message: string
    confirmLabel?: string
    cancelLabel?: string
    confirmDisabled?: boolean
    busy?: boolean
    id?: string
  }>(),
  {
    open: false,
    confirmLabel: '確認',
    cancelLabel: '取消',
    confirmDisabled: false,
    busy: false,
    id: undefined,
  },
)

const emit = defineEmits<{
  close: []
  cancel: []
  confirm: []
}>()

const fallbackId = `confirm-dialog-${getCurrentInstance()?.uid ?? 0}`
const dialogId = computed(() => props.id || fallbackId)
const messageId = computed(() => `${dialogId.value}-message`)
</script>

<template>
  <GlassModal
    :id="dialogId"
    :open="open"
    :title="title"
    :describedby="messageId"
    role="alertdialog"
    @close="emit('close')"
  >
    <p :id="messageId" class="confirm-dialog__message">{{ message }}</p>
    <template #footer>
      <div class="confirm-dialog__actions">
        <button
          type="button"
          class="confirm-dialog__button confirm-dialog__button--cancel"
          data-cancel
          :disabled="busy"
          @click="emit('cancel')"
        >
          {{ cancelLabel }}
        </button>
        <button
          type="button"
          class="confirm-dialog__button confirm-dialog__button--confirm"
          data-confirm
          :disabled="confirmDisabled || busy"
          :aria-busy="busy ? 'true' : undefined"
          @click="emit('confirm')"
        >
          {{ busy ? '處理中…' : confirmLabel }}
        </button>
      </div>
    </template>
  </GlassModal>
</template>

<style scoped>
.confirm-dialog__message {
  margin: 0;
  color: var(--app-ink-soft);
  font-size: 15px;
  line-height: 1.7;
}

.confirm-dialog__actions {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
}

.confirm-dialog__button {
  min-width: 96px;
  min-height: 44px;
  padding: 8px 16px;
  border: 1px solid var(--app-line);
  border-radius: 8px;
  cursor: pointer;
  font-weight: 800;
}

.confirm-dialog__button--cancel {
  color: var(--app-ink-soft);
  background: var(--app-paper-strong);
}

.confirm-dialog__button--confirm {
  border-color: var(--app-accent);
  color: #fff8f2;
  background: var(--app-accent);
}

.confirm-dialog__button--confirm:hover:not(:disabled) { background: var(--app-accent-deep); }
.confirm-dialog__button:disabled { cursor: not-allowed; opacity: 0.55; }

@media (max-width: 480px) {
  .confirm-dialog__actions { flex-direction: column-reverse; }
  .confirm-dialog__button { width: 100%; }
}
</style>
