'use client'

import { useEffect, useState, FormEvent } from 'react'
import { useRouter } from 'next/navigation'
import { GitBranch, Plus, Trash2, MessageSquare, Loader2 } from 'lucide-react'
import { useAuth } from '@/lib/auth-context'
import * as api from '@/lib/api'
import type { Repo } from '@/lib/api'

function statusLabel(repo: Repo) {
  if (repo.status === 'ready') return { text: 'ready', className: 'bg-emerald-500/10 text-emerald-400' }
  if (repo.status === 'failed') return { text: 'failed', className: 'bg-red-500/10 text-red-400' }
  return { text: repo.status, className: 'bg-blue-500/10 text-blue-400' }
}

export default function DashboardPage() {
  const router = useRouter()
  const { user, loading, logout } = useAuth()
  const [repos, setRepos] = useState<Repo[]>([])
  const [reposLoading, setReposLoading] = useState(true)
  const [url, setUrl] = useState('')
  const [adding, setAdding] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!loading && !user) router.replace('/login')
  }, [loading, user, router])

  useEffect(() => {
    if (!user) return
    api
      .listRepos()
      .then(setRepos)
      .catch(() => setError('Could not load your repositories.'))
      .finally(() => setReposLoading(false))
  }, [user])

  const submitRepo = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    if (!url.trim() || adding) return
    setError(null)
    setAdding(true)
    try {
      const repo = await api.addRepo(url.trim())
      router.push(`/repo/${repo.id}`)
    } catch (err) {
      setError(err instanceof api.ApiError ? err.message : 'Could not index that repository.')
      setAdding(false)
    }
  }

  const removeRepo = async (id: string) => {
    const prev = repos
    setRepos((r) => r.filter((x) => x.id !== id))
    try {
      await api.deleteRepo(id)
    } catch {
      setRepos(prev)
    }
  }

  if (loading || !user) {
    return (
      <main className="grid-bg flex min-h-screen items-center justify-center">
        <Loader2 className="animate-spin text-muted-foreground" size={22} />
      </main>
    )
  }

  return (
    <main className="grid-bg min-h-screen">
      <header className="mx-auto flex max-w-4xl items-center justify-between px-6 py-6">
        <div className="flex items-center gap-2">
          <div className="repo-mark">
            <span />
          </div>
          <span className="font-semibold tracking-tight">RepoMind</span>
        </div>
        <div className="flex items-center gap-3 text-sm text-muted-foreground">
          <span>{user.name}</span>
          <button onClick={logout} className="secondary-button">
            Log out
          </button>
        </div>
      </header>

      <section className="mx-auto max-w-4xl px-6 pb-24">
        <h1 className="text-2xl font-semibold tracking-tight">Your repositories</h1>
        <p className="mt-1 text-sm text-muted-foreground">Add a GitHub repo to start asking it questions.</p>

        <form onSubmit={submitRepo} className="mt-6 flex flex-col gap-2 rounded-xl border border-border bg-card p-2 sm:flex-row">
          <div className="flex min-w-0 flex-1 items-center gap-3 px-3">
            <GitBranch size={18} className="shrink-0 text-muted-foreground" />
            <input
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              placeholder="https://github.com/owner/repo"
              className="min-w-0 flex-1 bg-transparent py-3 text-sm outline-none placeholder:text-muted-foreground/60"
            />
          </div>
          <button type="submit" disabled={adding || !url.trim()} className="primary-button disabled:opacity-60">
            {adding ? <Loader2 size={16} className="animate-spin" /> : <Plus size={16} />}
            {adding ? 'Adding…' : 'Add repository'}
          </button>
        </form>
        {error && <p className="mt-3 text-sm text-red-400">{error}</p>}

        <div className="mt-8 space-y-2">
          {reposLoading && <p className="text-sm text-muted-foreground">Loading…</p>}
          {!reposLoading && repos.length === 0 && (
            <p className="text-sm text-muted-foreground">No repositories yet. Add one above to get started.</p>
          )}
          {repos.map((repo) => {
            const s = statusLabel(repo)
            return (
              <div
                key={repo.id}
                onClick={() => router.push(`/repo/${repo.id}`)}
                className="feature-card flex cursor-pointer items-center justify-between gap-4"
              >
                <div className="flex min-w-0 items-center gap-3">
                  <div className="rounded bg-muted p-2">
                    <GitBranch size={16} />
                  </div>
                  <div className="min-w-0">
                    <p className="truncate text-sm font-medium">{repo.full_name}</p>
                    <p className="mt-0.5 flex items-center gap-2 text-xs text-muted-foreground">
                      <span className={`rounded-full px-2 py-0.5 font-mono text-[10px] ${s.className}`}>{s.text}</span>
                      {repo.status === 'ready' && <span>{repo.file_count} files</span>}
                      {repo.question_count > 0 && (
                        <span className="flex items-center gap-1">
                          <MessageSquare size={11} /> {repo.question_count}
                        </span>
                      )}
                    </p>
                  </div>
                </div>
                <button
                  onClick={(e) => {
                    e.stopPropagation()
                    removeRepo(repo.id)
                  }}
                  className="icon-button shrink-0"
                  aria-label={`Remove ${repo.full_name}`}
                >
                  <Trash2 size={15} />
                </button>
              </div>
            )
          })}
        </div>
      </section>
    </main>
  )
}
