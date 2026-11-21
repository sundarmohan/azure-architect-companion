const sensitiveKey = /(^|[_-])(password|passwd|secret|token|api[_-]?key|access[_-]?key|private[_-]?key|connection[_-]?string|conn[_-]?string|credential|auth)($|[_-])/i

export function stripSensitive<T>(value: T): T {
  if (Array.isArray(value)) return value.map((item) => stripSensitive(item)) as T
  if (typeof value === 'object' && value !== null) {
    return Object.fromEntries(
      Object.entries(value)
        .filter(([key]) => !sensitiveKey.test(key))
        .map(([key, item]) => [key, stripSensitive(item)]),
    ) as T
  }
  return value
}

export function containsSensitiveKey(value: unknown): boolean {
  if (Array.isArray(value)) return value.some(containsSensitiveKey)
  if (typeof value !== 'object' || value === null) return false
  return Object.entries(value).some(([key, item]) => sensitiveKey.test(key) || containsSensitiveKey(item))
}
