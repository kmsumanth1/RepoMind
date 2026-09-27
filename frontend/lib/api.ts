// lib/api.ts
// Typed client for the RepoMind backend. Set NEXT_PUBLIC_API_URL in .env.local
// (defaults to http://localhost:8000 for local dev against `uvicorn api.main:app`).

const API_URL = (process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000').replace(/\/$/, '')
const TOKEN_KEY = 'repomind_token'

// ---------------------------------------------------------------- types
// Mirrors backend/api/schemas.py exactly - keep in sync if the backend changes.

export interface User {
  id: string
  name: string
  email: string | null
  github_login: string | null
  avatar_url: string | null
  created_at: string
}

export interface TokenResponse {
  access_token: string
  token_type: string
  user: User
}

export interface Repo {
  id: string
  full_name: string
  url: string
  status: 'cloning' | 'parsing' | 'embedding' | 'ready' | 'failed' | string
  progress: number
  message: string
  error: string | null
  file_count: number
  chunk_count: number
  commit_sha: string | null
  indexed_at: string | null
  last_opened_at: string | null
  question_count: number
}

export interface TreeNode {
  name: string
  path: string
  type: 'dir' | 'file'
  children: TreeNode[] | null
}

export interface FileOut {
  path: string
  language: string
  start_line: number
  end_line: number
  total_lines: number
  highlight_start: number | null
  highlight_end: number | null
  content: string
}

export interface Citation {
  id: number
  file: string
  start_line: number
  end_line: number
  name: string
  kind: string
  relation: string
}

export interface QueryResponse {
  session_id: string
  message_id: number
  answer: string
  citations: Citation[]
  grounded: boolean
  refused: boolean
  llm: string
  latency_ms: number
}

export interface Message {
  id: number
  role: 'user' | 'assistant'
  content: string
  citations: Citation[] | null
  meta: Record<string, unknown> | null
  created_at: string
}

export interface SessionSummary {
  id: string
  repo_id: string
  title: string
  created_at: string
  updated_at: string
}

export interface SessionDetail extends SessionSummary {
  messages: Message[]
}

// ---------------------------------------------------------------- token storage

export function getToken(): string | null {
  if (typeof window === 'undefined') return null
  return window.localStorage.getItem(TOKEN_KEY)
}

export function setToken(token: string) {
  if (typeof window === 'undefined') return
  window.localStorage.setItem(TOKEN_KEY, token)
}

export function clearToken() {
  if (typeof window === 'undefined') return
  window.localStorage.removeItem(TOKEN_KEY)
}

// ---------------------------------------------------------------- core request

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const token = getToken()
  const headers = new Headers(options.headers)
  headers.set('Accept', 'application/json')
  if (options.body && !(options.body instanceof FormData)) {
    headers.set('Content-Type', 'application/json')
  }
  if (token) headers.set('Authorization', `Bearer ${token}`)

  const res = await fetch(`${API_URL}${path}`, { ...options, headers })

  if (res.status === 204) return undefined as T

  const isJson = res.headers.get('content-type')?.includes('application/json')
  const data = isJson ? await res.json().catch(() => null) : null

  if (!res.ok) {
    const message =
      (data && (data.detail || data.message)) ||
      `Request failed with status ${res.status}`
    throw new ApiError(res.status, typeof message === 'string' ? message : JSON.stringify(message))
  }
  return data as T
}

function get<T>(path: string) {
  return request<T>(path, { method: 'GET' })
}
function post<T>(path: string, body?: unknown) {
  return request<T>(path, { method: 'POST', body: body !== undefined ? JSON.stringify(body) : undefined })
}
function del<T>(path: string) {
  return request<T>(path, { method: 'DELETE' })
}

// ---------------------------------------------------------------- auth

export function signup(name: string, email: string, password: string) {
  return post<TokenResponse>('/auth/signup', { name, email, password })
}

export function login(email: string, password: string) {
  return post<TokenResponse>('/auth/login', { email, password })
}

export function githubAuth(code: string) {
  return post<TokenResponse>('/auth/github', { code })
}

export function getMe() {
  return get<User>('/auth/me')
}

// ---------------------------------------------------------------- repos

export function addRepo(url: string, force = false) {
  return post<Repo>('/repos', { url, force })
}

export function listRepos() {
  return get<Repo[]>('/repos')
}

export function getRepo(repoId: string) {
  return get<Repo>(`/repos/${repoId}`)
}

export function deleteRepo(repoId: string) {
  return del<void>(`/repos/${repoId}`)
}

export function getRepoTree(repoId: string) {
  return get<TreeNode[]>(`/repos/${repoId}/tree`)
}

export function getRepoFile(
  repoId: string,
  path: string,
  opts: { start?: number; end?: number; context?: number } = {},
) {
  const params = new URLSearchParams({ path })
  if (opts.start != null) params.set('start', String(opts.start))
  if (opts.end != null) params.set('end', String(opts.end))
  if (opts.context != null) params.set('context', String(opts.context))
  return get<FileOut>(`/repos/${repoId}/file?${params.toString()}`)
}

// ---------------------------------------------------------------- chat

export function queryRepo(repoId: string, question: string, sessionId?: string) {
  return post<QueryResponse>(`/repos/${repoId}/query`, {
    question,
    session_id: sessionId ?? null,
  })
}

export function listSessions(repoId: string) {
  return get<SessionSummary[]>(`/repos/${repoId}/sessions`)
}

export function getSession(sessionId: string) {
  return get<SessionDetail>(`/sessions/${sessionId}`)
}

export function deleteSession(sessionId: string) {
  return del<void>(`/sessions/${sessionId}`)
}

// ---------------------------------------------------------------- polling helper

/** Polls GET /repos/{id} until status is 'ready' or 'failed'. Returns the final Repo. */
export async function waitForRepoReady(
  repoId: string,
  onProgress?: (repo: Repo) => void,
  intervalMs = 1200,
): Promise<Repo> {
  // eslint-disable-next-line no-constant-condition
  while (true) {
    const repo = await getRepo(repoId)
    onProgress?.(repo)
    if (repo.status === 'ready' || repo.status === 'failed') return repo
    await new Promise((r) => setTimeout(r, intervalMs))
  }
}
