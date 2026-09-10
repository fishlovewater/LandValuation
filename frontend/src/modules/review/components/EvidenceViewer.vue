<script setup lang="ts">
import { onBeforeUnmount, ref, watch } from 'vue'
import ErrorState from '../../../components/common/ErrorState.vue'
import LoadingSkeleton from '../../../components/common/LoadingSkeleton.vue'
import { reviewApi } from '../review.api'

const props = defineProps<{ reviewId: string; documentId?: string }>()
const url = ref<string | null>(null); const loading = ref(false); const error = ref('')

async function load() {
  if (!props.documentId) return
  loading.value = true; error.value = ''
  if (url.value) URL.revokeObjectURL(url.value)
  try { url.value = URL.createObjectURL(await reviewApi.getDocumentContent(props.reviewId, props.documentId)) }
  catch { url.value = null; error.value = '無法載入此文件預覽，請確認文件仍可存取。' }
  finally { loading.value = false }
}
watch(() => props.documentId, load, { immediate: true })
onBeforeUnmount(() => { if (url.value) URL.revokeObjectURL(url.value) })
</script>

<template>
  <section class="evidence-viewer solid-panel" aria-label="文件證據">
    <LoadingSkeleton v-if="loading" :lines="5" />
    <ErrorState v-else-if="error" :message="error" @retry="load" />
    <iframe v-else-if="url" :src="url" title="案件 PDF 證據預覽" />
    <div v-else class="viewer-empty">選擇 PDF 文件或疑點以查看證據。</div>
  </section>
</template>