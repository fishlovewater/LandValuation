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
