import { http } from '../../api/http'
import type {
  AuthUser,
  CurrentUserResponseDto,
  LoginRequestDto,
  TokenResponse,
  TokenResponseDto,
} from './auth.types'

function mapToken(dto: TokenResponseDto): TokenResponse {
  return { accessToken: dto.access_token, tokenType: dto.token_type, expiresIn: dto.expires_in }
}

function mapUser(dto: CurrentUserResponseDto): AuthUser {
  return {
    userId: dto.user_id,
    username: dto.username,
    displayName: dto.display_name,
    isActive: dto.is_active,
    roles: dto.roles,
    permissions: dto.permissions,
  }
}

export const authApi = {
  async login(username: string, password: string): Promise<TokenResponse> {
    const payload: LoginRequestDto = { username, password }
    const { data } = await http.post<TokenResponseDto>('/api/v1/auth/login', payload)
    return mapToken(data)
  },
  async me(): Promise<AuthUser> {
    const { data } = await http.get<CurrentUserResponseDto>('/api/v1/auth/me')
    return mapUser(data)
  },
}