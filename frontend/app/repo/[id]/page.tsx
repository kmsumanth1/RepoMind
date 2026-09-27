'use client'

import { useEffect, useRef, useState } from 'react'
import { useParams, useRouter } from 'next/navigation'
import {
  ArrowUp, Check, ChevronDown, ChevronRight, CircleAlert, CircleDot, Code2,
  FileCode2, Folder, GitBranch, Hash, Loader2, Menu, MessageSquare,
  PanelLeftClose, PanelLeftOpen, Send, Sparkles, X,
} from 'lucide-react'
import { useAuth } from '@/lib/auth-context'
import * as api from '@/lib/api'
import type { Citation, FileOut, Message, Repo, TreeNode } from '@/lib/api'

function RepoMark({ small = false }: { small?: boolean }) {
  return (
    <div className={`flex items-center gap-2 ${small ? 'text-sm' : ''}`}>
      <div className="repo-mark">
        <span />
      </div>
      <span className="font-semibold tracking-tight">RepoMind</span>
    </div>
  )
}

function FileTree({ nodes, onFile }: { nodes: TreeNode[]; onFile: (path: string) => void }) {
  const [open, setOpen] = useState<Record<string, boolean>>({})
  const render = (items: TreeNode[], depth = 0): React.ReactNode =>
    items.map((item) => {
      const isOpen = open[item.path] ?? depth < 1
      return (
        <div key={item.path}>
          <button
            onClick={() =>
              item.type === 'dir' ? setOpen((o) => ({ ...o, [item.path]: !isOpen })) : onFile(item.path)
            }
            className="tree-row"
            style={{ paddingLeft: `${12 + depth * 16}px` }}
          >
            {item.type === 'dir' ? (
              isOpen ? (
                <ChevronDown size={13} className="text-muted-foreground" />
              ) : (
                <ChevronRight size={13} className="text-muted-foreground" />
              )
            ) : (
              <span className="w-[13px]" />
            )}
            {item.type === 'dir' ? (
              <Folder size={14} className="text-blue-400" />
            ) : (
              <FileCode2 size={14} className="text-muted-foreground" />
            )}
            <span className="truncate">{item.name}</span>
          </button>
          {item.type === 'dir' && isOpen && item.children && render(item.children, depth + 1)}
        </div>
      )
    })
  return <div className="space-y-0.5">{render(nodes)}</div>
}

function SourceDrawer({
  repoId,
  path,
  highlight,
  onClose,
}: {
  repoId: string
  path: string
  highlight?: { start: number; end: number }
  onClose: () => void
}) {
  const [file, setFile] = useState<FileOut | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    setFile(null)
    setError(null)
    api
      .getRepoFile(repoId, path, highlight ? { start: highlight.start, end: highlight.end } : {})
      .then(setFile)
      .catch(() => setError('Could not load this file.'))
  }, [repoId, path, highlight])

  const lines = file?.content.split('\n') ?? []

  return (
    <div className="fixed inset-0 z-50 flex justify-end bg-black/50" onClick={onClose}>
      <aside className="source-drawer" onClick={(e) => e.stopPropagation()}>
        <header className="flex items-center justify-between border-b border-border px-5 py-4">
          <div>
            <p className="font-mono text-xs text-blue-400">{path}</p>
            <p className="mt-1 text-xs text-muted-foreground">
              {file ? `${file.language} · lines ${file.start_line}-${file.end_line} of ${file.total_lines}` : '…'}
            </p>
          </div>
          <button className="icon-button" onClick={onClose} aria-label="Close source viewer">
            <X size={17} />
          </button>
        </header>
        <div className="flex items-center gap-3 border-b border-border px-5 py-3 text-xs text-muted-foreground">
          <Code2 size={14} /> Source viewer
          {highlight && <span className="ml-auto rounded bg-blue-500/10 px-2 py-1 text-blue-300">highlighted</span>}
        </div>
        <div className="overflow-auto p-4">
          {error && <p className="text-sm text-red-400">{error}</p>}
          {!error && !file && <Loader2 size={16} className="animate-spin text-muted-foreground" />}
          {file && (
            <pre className="code-viewer">
              {lines.map((line, i) => {
                const lineNo = file.start_line + i
                const inRange =
                  file.highlight_start != null &&
                  file.highlight_end != null &&
                  lineNo >= file.highlight_start &&
                  lineNo <= file.highlight_end
                return (
                  <div key={lineNo} className={inRange ? 'code-highlight' : ''}>
                    <span className="line-number">{lineNo}</span>
                    <code>{line || ' '}</code>
                  </div>
                )
              })}
            </pre>
          )}
        </div>
      </aside>
    </div>
  )
}

function Indexing({ repo, onReady }: { repo: Repo; onReady: () => void }) {
  const [current, setCurrent] = useState(repo)
  const router = useRouter()

  useEffect(() => {
    let cancelled = false
    api
      .waitForRepoReady(repo.id, (r) => !cancelled && setCurrent(r))
      .then((r) => {
        if (cancelled) return
        if (r.status === 'ready') onReady()
      })
    return () => {
      cancelled = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [repo.id])

  const steps = ['Cloning repository', 'Parsing files', 'Building embeddings', 'Ready']
  const stepIndex = current.status === 'cloning' ? 0 : current.status === 'parsing' ? 1 : current.status === 'embedding' ? 2 : 3

  if (current.status === 'failed') {
    return (
      <main className="grid-bg flex min-h-screen items-center justify-center px-5">
        <div className="w-full max-w-lg animate-in-up">
          <div className="mb-10 flex justify-center">
            <RepoMark />
          </div>
          <div className="panel p-7 sm:p-9">
            <div className="flex items-start gap-4">
              <div className="rounded-lg bg-red-500/10 p-3 text-red-400">
                <CircleAlert size={21} />
              </div>
              <div>
                <p className="font-mono text-xs text-blue-400">{current.full_name}</p>
                <h1 className="mt-1 text-xl font-semibold">Indexing failed</h1>
                <p className="mt-1 text-sm text-muted-foreground">{current.error || current.message}</p>
              </div>
            </div>
            <button onClick={() => router.push('/dashboard')} className="secondary-button mt-7 w-full justify-center">
              Back to dashboard
            </button>
          </div>
        </div>
      </main>
    )
  }

  return (
    <main className="grid-bg flex min-h-screen items-center justify-center px-5">
      <div className="w-full max-w-lg animate-in-up">
        <div className="mb-10 flex justify-center">
          <RepoMark />
        </div>
        <div className="panel p-7 sm:p-9">
          <div className="mb-8 flex items-start gap-4">
            <div className="rounded-lg bg-blue-500/10 p-3 text-blue-400">
              <GitBranch size={21} />
            </div>
            <div>
              <p className="font-mono text-xs text-blue-400">{current.full_name}</p>
              <h1 className="mt-1 text-xl font-semibold">Indexing repository</h1>
              <p className="mt-1 text-sm text-muted-foreground">{current.message || 'This usually takes less than a minute.'}</p>
            </div>
          </div>
          <div className="mb-8 h-2 overflow-hidden rounded-full bg-secondary">
            <div
              className="h-full rounded-full bg-blue-500 transition-all duration-500"
              style={{ width: `${current.progress}%` }}
            />
          </div>
          <div className="space-y-4">
            {steps.map((step, i) => {
              const done = i < stepIndex
              const active = i === stepIndex
              return (
                <div key={step} className="flex items-center gap-3 text-sm">
                  <div className={done ? 'step-dot done' : active ? 'step-dot active' : 'step-dot'}>
                    {done ? <Check size={12} /> : active ? <span /> : null}
                  </div>
                  <span className={done || active ? 'text-foreground' : 'text-muted-foreground'}>{step}</span>
                </div>
              )
            })}
          </div>
        </div>
        <p className="mt-5 text-center font-mono text-xs text-muted-foreground">Powered by RepoMind retrieval engine</p>
      </div>
    </main>
  )
}

interface DrawerTarget {
  path: string
  highlight?: { start: number; end: number }
}

export default function RepoPage() {
  const params = useParams<{ id: string }>()
  const router = useRouter()
  const { user, loading: authLoading } = useAuth()
  const repoId = params.id

  const [repo, setRepo] = useState<Repo | null>(null)
  const [notFound, setNotFound] = useState(false)
  const [tree, setTree] = useState<TreeNode[]>([])
  const [sessions, setSessions] = useState<{ id: string; title: string }[]>([])
  const [sessionId, setSessionId] = useState<string | undefined>(undefined)

  const [sidebar, setSidebar] = useState(true)
  const [drawer, setDrawer] = useState<DrawerTarget | null>(null)
  const [input, setInput] = useState('')
  const [messages, setMessages] = useState<Message[]>([])
  const [loadingAnswer, setLoadingAnswer] = useState(false)
  const [askError, setAskError] = useState<string | null>(null)
  const scrollRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!authLoading && !user) router.replace('/login')
  }, [authLoading, user, router])

  useEffect(() => {
    if (!user || !repoId) return
    api
      .getRepo(repoId)
      .then(setRepo)
      .catch(() => setNotFound(true))
  }, [user, repoId])

  const loadWorkspace = async () => {
    const [t, s] = await Promise.all([api.getRepoTree(repoId), api.listSessions(repoId)])
    setTree(t)
    setSessions(s.map((x) => ({ id: x.id, title: x.title })))
  }

  useEffect(() => {
    if (repo?.status === 'ready' && tree.length === 0) {
      loadWorkspace().catch(() => {})
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [repo?.status])

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' })
  }, [messages, loadingAnswer])

  const ask = async () => {
    if (!input.trim() || loadingAnswer) return
    const question = input.trim()
    setInput('')
    setAskError(null)
    setLoadingAnswer(true)
    setMessages((m) => [...m, { id: Date.now(), role: 'user', content: question, citations: null, meta: null, created_at: new Date().toISOString() }])
    try {
      const res = await api.queryRepo(repoId, question, sessionId)
      setSessionId(res.session_id)
      setMessages((m) => [
        ...m,
        {
          id: res.message_id,
          role: 'assistant',
          content: res.answer,
          citations: res.citations,
          meta: { refused: res.refused, grounded: res.grounded },
          created_at: new Date().toISOString(),
        },
      ])
    } catch {
      setAskError('Something went wrong answering that question. Please try again.')
    } finally {
      setLoadingAnswer(false)
    }
  }

  const openCitation = (c: Citation) => {
    setDrawer({ path: c.file, highlight: { start: c.start_line, end: c.end_line } })
  }

  if (authLoading || !user) {
    return (
      <main className="grid-bg flex min-h-screen items-center justify-center">
        <Loader2 className="animate-spin text-muted-foreground" size={22} />
      </main>
    )
  }

  if (notFound) {
    return (
      <main className="grid-bg flex min-h-screen items-center justify-center px-5 text-center">
        <div>
          <p className="text-lg font-medium">Repository not found</p>
          <button onClick={() => router.push('/dashboard')} className="secondary-button mt-4">
            Back to dashboard
          </button>
        </div>
      </main>
    )
  }

  if (!repo) {
    return (
      <main className="grid-bg flex min-h-screen items-center justify-center">
        <Loader2 className="animate-spin text-muted-foreground" size={22} />
      </main>
    )
  }

  if (repo.status !== 'ready') {
    return <Indexing repo={repo} onReady={() => setRepo((r) => (r ? { ...r, status: 'ready' } : r))} />
  }

  return (
    <main className="flex h-screen overflow-hidden bg-background">
      <aside className={`${sidebar ? 'w-[276px]' : 'w-0'} sidebar shrink-0 overflow-hidden transition-all duration-300`}>
        <div className="flex h-full w-[276px] flex-col">
          <header className="flex items-center justify-between border-b border-border px-5 py-4">
            <button onClick={() => router.push('/dashboard')} className="hover:text-blue-400">
              <RepoMark small />
            </button>
            <button onClick={() => setSidebar(false)} className="icon-button" aria-label="Collapse sidebar">
              <PanelLeftClose size={16} />
            </button>
          </header>
          <div className="border-b border-border px-5 py-4">
            <div className="flex items-center gap-2">
              <div className="rounded bg-muted p-1.5">
                <GitBranch size={15} />
              </div>
              <div className="min-w-0">
                <p className="truncate text-sm font-medium">{repo.full_name}</p>
                <p className="font-mono text-[10px] text-emerald-400">indexed · {repo.file_count} files</p>
              </div>
            </div>
          </div>
          <div className="flex-1 overflow-y-auto px-3 py-5">
            <p className="section-label px-2">Files</p>
            <div className="mt-3">
              <FileTree nodes={tree} onFile={(path) => setDrawer({ path })} />
            </div>
            {sessions.length > 0 && (
              <>
                <p className="section-label mt-8 px-2">Recent questions</p>
                <div className="mt-3 space-y-1">
                  {sessions.slice(0, 8).map((s) => (
                    <button
                      key={s.id}
                      onClick={async () => {
                        setSessionId(s.id)
                        try {
                          const detail = await api.getSession(s.id)
                          setMessages(detail.messages)
                        } catch {
                          // keep current thread if the load fails
                        }
                      }}
                      className="question-link"
                    >
                      <MessageSquare size={13} /> {s.title}
                    </button>
                  ))}
                </div>
              </>
            )}
          </div>
          <footer className="border-t border-border p-4">
            <button
              onClick={() => router.push('/dashboard')}
              className="flex w-full items-center gap-2 rounded-md px-2 py-2 text-xs text-muted-foreground transition hover:bg-muted hover:text-foreground"
            >
              <X size={14} /> Index another repository
            </button>
          </footer>
        </div>
      </aside>

      <section className="flex min-w-0 flex-1 flex-col">
        <header className="flex h-[57px] shrink-0 items-center justify-between border-b border-border px-4 sm:px-6">
          <div className="flex items-center gap-3">
            {!sidebar && (
              <button onClick={() => setSidebar(true)} className="icon-button" aria-label="Open sidebar">
                <PanelLeftOpen size={17} />
              </button>
            )}
            <div className="flex items-center gap-2 text-sm">
              <span className="font-mono text-muted-foreground">{repo.full_name.split('/')[1]}</span>
              <ChevronRight size={13} className="text-muted-foreground" />
              <span className="text-muted-foreground">Ask RepoMind</span>
            </div>
          </div>
          <span className="hidden items-center gap-1.5 rounded-full bg-emerald-500/10 px-2.5 py-1 font-mono text-[10px] text-emerald-400 sm:flex">
            <CircleDot size={10} /> ready
          </span>
        </header>

        <div className="flex-1 overflow-y-auto" ref={scrollRef}>
          <div className="mx-auto max-w-3xl px-4 py-8 sm:px-8 sm:py-12">
            <div className="mb-10">
              <p className="font-mono text-xs text-blue-400">REPOSITORY Q&amp;A</p>
              <h1 className="mt-2 text-2xl font-semibold tracking-tight sm:text-3xl">What would you like to understand?</h1>
              <p className="mt-2 text-sm text-muted-foreground">
                Answers are generated from <span className="font-mono text-foreground">{repo.full_name}</span> and cited to source.
              </p>
            </div>

            {messages.length === 0 && (
              <p className="text-sm text-muted-foreground">Ask anything about this codebase to get started.</p>
            )}

            <div className="space-y-8">
              {messages
                .reduce<{ q?: Message; pairs: [Message, Message | null][] }>(
                  (acc, m) => {
                    if (m.role === 'user') {
                      acc.pairs.push([m, null])
                    } else if (acc.pairs.length) {
                      acc.pairs[acc.pairs.length - 1][1] = m
                    }
                    return acc
                  },
                  { pairs: [] },
                )
                .pairs.map(([q, a], i) => (
                  <div key={q.id} className="animate-in-up">
                    <div className="mb-3 flex items-start gap-3">
                      <div className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-blue-500/10 text-blue-400">
                        <Hash size={13} />
                      </div>
                      <p className="text-sm font-medium leading-6">{q.content}</p>
                    </div>
                    {a && a.meta?.refused ? (
                      <div className="empty-answer">
                        <CircleAlert size={18} className="text-amber-400" />
                        <div>
                          <p className="font-medium text-amber-200">No relevant code found</p>
                          <p className="mt-1 text-sm leading-6 text-muted-foreground">{a.content}</p>
                        </div>
                      </div>
                    ) : a ? (
                      <div className="answer-card">
                        <div className="whitespace-pre-line text-sm leading-7 text-foreground/90">
                          {a.content.split('`').map((part, j) =>
                            j % 2 ? (
                              <code key={j} className="rounded bg-muted px-1.5 py-0.5 font-mono text-xs text-blue-300">
                                {part}
                              </code>
                            ) : (
                              part
                            ),
                          )}
                        </div>
                        {a.citations && a.citations.length > 0 && (
                          <div className="mt-7 border-t border-border pt-4">
                            <p className="section-label mb-3">Sources</p>
                            <div className="flex flex-wrap gap-2">
                              {a.citations.map((c) => (
                                <button key={c.id} onClick={() => openCitation(c)} className="source-chip">
                                  <FileCode2 size={13} />
                                  {c.file}:{c.start_line}-{c.end_line}
                                  <ArrowUp size={12} className="rotate-45 opacity-50" />
                                </button>
                              ))}
                            </div>
                          </div>
                        )}
                      </div>
                    ) : i === messages.length - 1 ? null : null}
                  </div>
                ))}

              {loadingAnswer && (
                <div className="flex items-center gap-3 text-sm text-muted-foreground">
                  <div className="flex h-6 w-6 items-center justify-center rounded-full bg-blue-500/10 text-blue-400">
                    <Sparkles size={13} className="animate-pulse" />
                  </div>
                  <span className="animate-pulse">Searching codebase...</span>
                </div>
              )}
              {askError && <p className="text-sm text-red-400">{askError}</p>}
            </div>
          </div>
        </div>

        <div className="mx-auto w-full max-w-3xl px-4 pb-5 sm:px-8">
          <div className="composer">
            <textarea
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
                  e.preventDefault()
                  ask()
                }
              }}
              placeholder="Ask anything about this codebase..."
              rows={2}
            />
            <div className="flex items-center justify-between">
              <span className="font-mono text-[10px] text-muted-foreground">shift + enter for new line</span>
              <button onClick={ask} disabled={!input.trim() || loadingAnswer} className="send-button" aria-label="Send question">
                <Send size={15} />
              </button>
            </div>
          </div>
          <p className="mt-2 text-center font-mono text-[10px] text-muted-foreground/60">
            RepoMind can make mistakes. Verify important details in the source.
          </p>
        </div>
      </section>

      {drawer && (
        <SourceDrawer repoId={repoId} path={drawer.path} highlight={drawer.highlight} onClose={() => setDrawer(null)} />
      )}
    </main>
  )
}
