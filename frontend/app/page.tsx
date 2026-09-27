'use client'

import { useState } from 'react'
import { useRouter } from 'next/navigation'
import { ArrowUp, BookOpen, Code2, GitBranch, Loader2, MessageSquare, Search, Zap } from 'lucide-react'
import { useAuth } from '@/lib/auth-context'
import * as api from '@/lib/api'

const DEMO_REPOS: Record<string, string> = {
  FastAPI: 'https://github.com/tiangolo/fastapi',
  Requests: 'https://github.com/psf/requests',
  Flask: 'https://github.com/pallets/flask',
}

function RepoMark() {
  return (
    <div className="flex items-center gap-2">
      <div className="repo-mark">
        <span />
      </div>
      <span className="font-semibold tracking-tight">RepoMind</span>
    </div>
  )
}

export default function Page() {
  const router = useRouter()
  const { user, loading } = useAuth()
  const [url, setUrl] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const indexRepo = async (repoUrl: string) => {
    if (!repoUrl.trim() || submitting) return
    if (!user) {
      router.push('/login')
      return
    }
    setError(null)
    setSubmitting(true)
    try {
      const repo = await api.addRepo(repoUrl.trim())
      router.push(`/repo/${repo.id}`)
    } catch (err) {
      setError(err instanceof api.ApiError ? err.message : 'Could not index that repository.')
      setSubmitting(false)
    }
  }

  return (
    <main className="grid-bg min-h-screen">
      <header className="mx-auto flex max-w-6xl items-center justify-between px-6 py-6">
        <RepoMark />
        <div className="flex items-center gap-2 sm:gap-3">
          {loading ? (
            <Loader2 size={16} className="animate-spin text-muted-foreground" />
          ) : user ? (
            <button type="button" onClick={() => router.push('/dashboard')} className="primary-button px-4 py-2">
              Dashboard
            </button>
          ) : (
            <>
              <button type="button" onClick={() => router.push('/login')} className="secondary-button">
                Log in
              </button>
              <button type="button" onClick={() => router.push('/signup')} className="primary-button px-4 py-2">
                Sign up
              </button>
            </>
          )}
        </div>
      </header>

      <section className="mx-auto flex max-w-3xl flex-col items-center px-6 pb-24 pt-24 text-center sm:pt-32">
        <div className="mb-7 flex items-center gap-2 rounded-full border border-blue-500/20 bg-blue-500/5 px-3 py-1.5 font-mono text-xs text-blue-300">
          <Zap size={13} /> grounded code intelligence
        </div>
        <h1 className="text-balance text-5xl font-semibold tracking-[-0.045em] sm:text-7xl">
          Understand any
          <br />
          <span className="text-blue-400">codebase</span>, instantly.
        </h1>
        <p className="mt-7 max-w-xl text-pretty text-base leading-7 text-muted-foreground sm:text-lg">
          Ask questions in plain English. Get clear answers grounded in your repository, with every claim linked back
          to the exact lines of code.
        </p>

        <div className="mt-10 flex w-full flex-col gap-2 rounded-xl border border-border bg-card p-2 shadow-2xl shadow-blue-950/10 sm:flex-row">
          <div className="flex min-w-0 flex-1 items-center gap-3 px-3">
            <GitBranch size={18} className="shrink-0 text-muted-foreground" />
            <input
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && indexRepo(url)}
              placeholder="Paste a GitHub repository URL"
              className="min-w-0 flex-1 bg-transparent py-3 text-sm outline-none placeholder:text-muted-foreground/60"
            />
          </div>
          <button onClick={() => indexRepo(url)} disabled={submitting} className="primary-button disabled:opacity-60">
            {submitting ? <Loader2 size={16} className="animate-spin" /> : <Search size={16} />}
            Index Repository <ArrowUp size={14} className="rotate-45" />
          </button>
        </div>
        {error && <p className="mt-3 text-sm text-red-400">{error}</p>}

        <div className="mt-5 flex flex-wrap justify-center gap-2">
          <span className="mr-1 py-2 text-xs text-muted-foreground">Try a demo:</span>
          {Object.entries(DEMO_REPOS).map(([label, repoUrl]) => (
            <button key={label} onClick={() => indexRepo(repoUrl)} className="chip-button">
              <GitBranch size={13} /> {label}
            </button>
          ))}
        </div>

        <div className="mt-24 grid w-full grid-cols-1 gap-3 text-left sm:grid-cols-3">
          <div className="feature-card">
            <MessageSquare size={18} className="text-blue-400" />
            <p className="mt-5 font-medium">Ask naturally</p>
            <p className="mt-2 text-sm leading-6 text-muted-foreground">No query language. Just ask what you need to know.</p>
          </div>
          <div className="feature-card">
            <BookOpen size={18} className="text-blue-400" />
            <p className="mt-5 font-medium">Trust the answer</p>
            <p className="mt-2 text-sm leading-6 text-muted-foreground">Every response includes the source files and line ranges.</p>
          </div>
          <div className="feature-card">
            <Code2 size={18} className="text-blue-400" />
            <p className="mt-5 font-medium">Go deeper</p>
            <p className="mt-2 text-sm leading-6 text-muted-foreground">Jump directly into highlighted code when context matters.</p>
          </div>
        </div>
      </section>
    </main>
  )
}
