export interface LoginCredentials {
  username: string
  password: string
}

export type DemoLoginRole = 'APPRAISER' | 'REVIEWER' | 'INSPECTOR'

export interface TokenResponseDto {
  access_token: string
  token_type: string
  expires_in: number
}

export interface CurrentUserDto {
  user_id: string
  username: string
  email: string
  display_name: string
  roles: string[]
  permissions: string[]
}

export interface AuthUser {
  id: string
  username: string
  email: string
  displayName: string
  roles: string[]
  permissions: string[]
}

export interface AccountAccessRequestPayload {
  username: string
  email: string
  display_name: string
  requested_role: DemoLoginRole
  reason?: string | null
}

export interface AccountAccessRequestResponseDto {
  request_id: string
  status: 'PENDING' | 'APPROVED' | 'REJECTED'
  message: string
}

export type AccountAccessRequestStatus = 'PENDING' | 'APPROVED' | 'REJECTED'

export interface AccountAccessRequestAdminDto {
  request_id: string
  username: string
  email: string
  display_name: string
  requested_role: DemoLoginRole
  reason?: string | null
  status: AccountAccessRequestStatus
  decision_note?: string | null
  created_at: string
  handled_at?: string | null
  handled_by_user_id?: string | null
}

export interface AccountAccessDecisionResponseDto {
  request: AccountAccessRequestAdminDto
  account_created: boolean
  setup_email_sent: boolean
  debug_setup_token?: string | null
}

export interface PasswordResetRequestResponseDto {
  message: string
  debug_token?: string | null
}
