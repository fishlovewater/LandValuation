export interface AuthUser {
  userId: string
  username: string
  displayName: string
  isActive: boolean
  roles: string[]
  permissions: string[]
}

export interface TokenResponse {
  accessToken: string
  tokenType: string
  expiresIn: number
}

export interface LoginRequestDto {
  username: string
  password: string
}

export interface TokenResponseDto {
  access_token: string
  token_type: string
  expires_in: number
}

export interface CurrentUserResponseDto {
  user_id: string
  username: string
  display_name: string
  is_active: boolean
  roles: string[]
  permissions: string[]
}