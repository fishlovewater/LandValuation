import { http } from '../../api/http'
import type { AuthUser, CurrentUserDto, DemoLoginRole, LoginCredentials, TokenResponseDto } from './auth.types'

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
