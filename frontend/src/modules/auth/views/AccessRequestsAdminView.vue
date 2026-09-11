<script setup lang="ts">
import { onMounted, ref } from 'vue'
import PageHeader from '../../../components/common/PageHeader.vue'
import EmptyState from '../../../components/common/EmptyState.vue'
import ErrorState from '../../../components/common/ErrorState.vue'
import LoadingSkeleton from '../../../components/common/LoadingSkeleton.vue'
import { formatDateZhTw } from '../../../utils/formatters'
import { authApi } from '../auth.api'
import type { AccountAccessRequestAdminDto, AccountAccessRequestStatus } from '../auth.types'

const statusFilter = ref<AccountAccessRequestStatus>('PENDING')
const rows = ref<AccountAccessRequestAdminDto[]>([])
const loading = ref(false)
const busyId = ref<string | null>(null)
const error = ref('')
const notice = ref('')
const noteById = ref<Record<string, string>>({})

async function load(): Promise<void> {
  loading.value = true
  error.value = ''
  try {
    rows.value = await authApi.listAccountRequests(statusFilter.value)
  } catch {
    error.value = '目前無法載入帳號申請，請稍後再試。'
  } finally {
    loading.value = false
  }
}

async function decide(row: AccountAccessRequestAdminDto, decision: 'APPROVED' | 'REJECTED'): Promise<void> {
  if (busyId.value) return
  busyId.value = row.request_id
  error.value = ''
  notice.value = ''
  try {
    const result = await authApi.decideAccountRequest(row.request_id, decision, noteById.value[row.request_id])
    if (decision === 'APPROVED') {
      notice.value = result.setup_email_sent
        ? `已核准 ${row.display_name}，密碼設定信已寄出。`
        : result.debug_setup_token
          ? `已核准 ${row.display_name}。開發環境設定碼：${result.debug_setup_token}`
          : `已核准 ${row.display_name}；目前未設定寄信服務，請由管理者協助密碼設定。`
    } else {
      notice.value = `已拒絕 ${row.display_name} 的帳號申請。`
    }
    await load()
  } catch {
    error.value = '帳號申請目前無法完成處理，請確認申請狀態與寄信設定後再試。'
  } finally {
    busyId.value = null
  }
}

onMounted(load)
</script>

<template>
  <section class="access-admin" data-testid="access-requests-admin">
    <PageHeader
      eyebrow="帳號管理"
      title="工作帳號申請"
      description="僅具 auth.manage 權限的管理者可核准或拒絕申請；核准後系統建立帳號並寄送一次性密碼設定連結。"
    />

    <div class="access-admin__toolbar">
      <label>
        <span>申請狀態</span>
        <select v-model="statusFilter" data-testid="access-request-status" @change="load">
          <option value="PENDING">待審核</option>
          <option value="APPROVED">已核准</option>
          <option value="REJECTED">已拒絕</option>
        </select>
      </label>
      <button type="button" :disabled="loading" @click="load">重新載入</button>
    </div>

    <p v-if="notice" class="access-admin__notice" role="status">{{ notice }}</p>
    <ErrorState v-if="error && !rows.length" :message="error" @retry="load" />
    <LoadingSkeleton v-else-if="loading && !rows.length" :rows="4" label="帳號申請載入中" />
    <EmptyState
      v-else-if="!rows.length"
      :title="statusFilter === 'PENDING' ? '目前沒有待審核申請' : '目前沒有符合狀態的申請'"
      description="新的工作帳號申請會顯示在這裡。"
    />

    <div v-else class="access-admin__list">
      <article v-for="row in rows" :key="row.request_id" class="access-admin__card">
        <header>
          <div>
            <small>{{ row.requested_role }}</small>
            <h2>{{ row.display_name }}</h2>
            <p>{{ row.username }} · {{ row.email }}</p>
          </div>
          <span :data-status="row.status">{{ row.status === 'PENDING' ? '待審核' : row.status === 'APPROVED' ? '已核准' : '已拒絕' }}</span>
        </header>
        <dl>
          <div><dt>申請時間</dt><dd>{{ formatDateZhTw(row.created_at) }}</dd></div>
          <div><dt>申請原因</dt><dd>{{ row.reason || '未填寫' }}</dd></div>
          <div v-if="row.decision_note"><dt>處理備註</dt><dd>{{ row.decision_note }}</dd></div>
        </dl>
        <div v-if="row.status === 'PENDING'" class="access-admin__decision">
          <label>管理備註<textarea v-model="noteById[row.request_id]" maxlength="2000" rows="2" /></label>
          <div>
            <button type="button" :disabled="Boolean(busyId)" @click="decide(row, 'REJECTED')">拒絕申請</button>
            <button class="is-primary" type="button" :disabled="Boolean(busyId)" @click="decide(row, 'APPROVED')">
              {{ busyId === row.request_id ? '處理中…' : '核准並建立帳號' }}
            </button>
          </div>
        </div>
      </article>
    </div>
  </section>
</template>

<style scoped>
.access-admin{padding:0 28px 36px}.access-admin__toolbar{display:flex;align-items:end;justify-content:space-between;gap:16px;margin:18px 0}.access-admin__toolbar label{display:grid;gap:6px;color:var(--app-ink-soft);font-size:12px;font-weight:800}.access-admin select,.access-admin textarea{border:1px solid var(--app-line);border-radius:8px;padding:9px 11px;color:var(--app-ink);background:#fff;font:inherit}.access-admin button{min-height:40px;padding:8px 14px;border:1px solid var(--app-line);border-radius:8px;color:var(--app-ink-soft);background:#fff;cursor:pointer;font-weight:800}.access-admin button.is-primary{border-color:var(--app-accent);color:#fff;background:var(--app-accent)}.access-admin button:disabled{cursor:not-allowed;opacity:.55}.access-admin__notice{padding:11px 13px;border-radius:8px;color:#236a4c;background:#edf8f2}.access-admin__list{display:grid;gap:12px}.access-admin__card{padding:18px;border:1px solid var(--app-line);border-radius:var(--app-radius-sm);background:var(--app-paper-strong)}.access-admin__card header{display:flex;align-items:flex-start;justify-content:space-between;gap:14px}.access-admin__card h2{margin:3px 0;color:var(--app-ink);font-size:18px}.access-admin__card p,.access-admin__card small{margin:0;color:var(--app-muted);font-size:11px}.access-admin__card header>span{padding:5px 9px;border-radius:999px;background:#edf4fb;color:#2e5984;font-size:11px;font-weight:800}.access-admin__card header>span[data-status="APPROVED"]{background:#edf8f3;color:#2f745b}.access-admin__card header>span[data-status="REJECTED"]{background:#fff0ed;color:#9a4435}.access-admin dl{display:grid;gap:8px;margin:16px 0 0}.access-admin dl div{display:grid;grid-template-columns:90px 1fr;gap:10px}.access-admin dt{color:var(--app-muted);font-size:11px}.access-admin dd{margin:0;color:var(--app-ink-soft);font-size:12px}.access-admin__decision{display:grid;gap:10px;margin-top:16px;padding-top:14px;border-top:1px solid var(--app-line)}.access-admin__decision label{display:grid;gap:6px;color:var(--app-ink-soft);font-size:11px;font-weight:800}.access-admin__decision>div{display:flex;justify-content:flex-end;gap:8px}@media(max-width:640px){.access-admin{padding-inline:14px}.access-admin__toolbar,.access-admin__card header{align-items:stretch;flex-direction:column}.access-admin dl div{grid-template-columns:1fr}.access-admin__decision>div{flex-direction:column}.access-admin__decision button{width:100%}}
</style>
