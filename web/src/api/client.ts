export const API_BASE: string = import.meta.env.VITE_API_BASE ?? '/api/v1'

export class ApiError extends Error {
  readonly status: number

  constructor(status: number, message: string) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

export async function getJson<T>(path: string, signal?: AbortSignal): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    signal,
    headers: { Accept: 'application/json' },
  })
  if (!response.ok) {
    throw new ApiError(response.status, `GET ${path} failed with ${response.status}`)
  }
  return (await response.json()) as T
}
