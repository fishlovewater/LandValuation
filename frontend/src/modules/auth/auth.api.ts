import { http } from '../../api/http'
import type {
  AccountAccessRequestPayload,
  AccountAccessRequestResponseDto,
  AuthUser,
  CurrentUserDto,
  DemoLoginRole,
  LoginCredentials,
  PasswordResetRequestResponseDto,
  TokenResponseDto,
} from './auth.types'

export function mapCurrentUser(dto: CurrentUserDto): AuthUser {
  return {
    id: dto.user_id,
    username: dto.username,
    email: dto.email,
    displayName: dto.display_name,
    roles: dto.roles,
    permissions: dto.permissions,
  }
}

export const authApi = {
  async requestAccount(payload: AccountAccessRequestPayload): Promise<AccountAccessRequestResponseDto> {
    const response = await http.post<AccountAccessRequestResponseDto>('/auth/registration-requests', payload)
    return response.data
  },

  async requestPasswordReset(account: string): Promise<PasswordResetRequestResponseDto> {
    const response = await http.post<PasswordResetRequestResponseDto>('/auth/password-reset-requests', { account })
    return response.data
  },

  async confirmPasswordReset(token: string, newPassword: string): Promise<{ message: string }> {
    const response = await http.post<{ message: string }>('/auth/password-reset-confirm', {
      token,
      new_password: newPassword,
    })
    return response.data
  },

  async login(credentials: LoginCredentials): Promise<TokenResponseDto> {
    const response = await http.post<TokenResponseDto>('/auth/login', credentials)
    return response.data
  },

  async demoLogin(role: DemoLoginRole): Promise<TokenResponseDto> {
    const response = await http.post<TokenResponseDto>('/auth/demo-login', { role })
    return response.data
  },

  async me(accessToken?: string): Promise<AuthUser> {
    const response = await http.get<CurrentUserDto>(
      '/auth/me',
      accessToken ? { headers: { Authorization: `Bearer ${accessToken}` } } : undefined,
    )
    return mapCurrentUser(response.data)
  },
}
