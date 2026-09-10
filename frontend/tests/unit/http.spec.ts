import { AxiosError, type AxiosRequestConfig, type AxiosResponse } from 'axios'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { http, setUnauthorizedHandler } from '../../src/api/http'
import { readAccessToken, writeAccessToken } from '../../src/utils/storage'

describe('central HTTP client', () => {
  beforeEach(() => {
    sessionStorage.clear()
    setUnauthorizedHandler(undefined)
  })

  it('adds the bearer token without exposing credentials to callers', async () => {
    writeAccessToken('abc123')
    let authorization: string | undefined

    await http.get('/probe', {
      adapter: async (config) => {
        authorization = config.headers?.get?.('Authorization') as string | undefined
        return { data: {}, status: 200, statusText: 'OK', headers: {}, config }
      },
    })

    expect(authorization).toBe('Bearer abc123')
  })

  it('clears the token and invokes one centralized handler on 401', async () => {
    writeAccessToken('expired')
    const onUnauthorized = vi.fn()
    setUnauthorizedHandler(onUnauthorized)

    const adapter = async (config: AxiosRequestConfig): Promise<AxiosResponse> => {
      const response = { data: {}, status: 401, statusText: 'Unauthorized', headers: {}, config } as AxiosResponse
      throw new AxiosError('Unauthorized', 'ERR_BAD_REQUEST', config as never, undefined, response)
    }

    await expect(http.get('/expired', { adapter })).rejects.toBeInstanceOf(AxiosError)
    expect(readAccessToken()).toBeNull()
    expect(onUnauthorized).toHaveBeenCalledOnce()
  })
})