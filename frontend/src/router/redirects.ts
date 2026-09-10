export function safeAppRedirect(value: unknown): string | null {
  if (typeof value !== 'string' || value.includes('\\')) return null
  const suffixStart = value.search(/[?#]/)
  const path = suffixStart === -1 ? value : value.slice(0, suffixStart)
  if (path !== '/app' && !path.startsWith('/app/')) return null
  if (/%(?:2e|2f|5c)/i.test(path)) return null

  let decodedPath = path
  for (let index = 0; index < 3; index += 1) {
    let nextPath: string
    try {
      nextPath = decodeURIComponent(decodedPath)
    } catch {
      return null
    }
    if (nextPath === decodedPath) break
    decodedPath = nextPath
  }

  if (
    decodedPath.includes('\\') ||
    /(?:^|\/)\.{1,2}(?:\/|$)/.test(decodedPath) ||
    /\/{2,}/.test(decodedPath)
  ) {
    return null
  }
  return value
}
