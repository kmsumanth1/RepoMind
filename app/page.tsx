'use client'

import { useMemo, useState } from 'react'
import {
  ArrowUp, BookOpen, Check, ChevronDown, ChevronRight, CircleAlert, CircleDot,
  Code2, Copy, FileCode2, Folder, GitBranch, Hash, Menu, MessageSquare,
  PanelLeftClose, PanelLeftOpen, Search, Send, Sparkles, X, Zap,
} from 'lucide-react'

const files = [
  { name: 'app', kind: 'folder', open: true, children: [
    { name: 'main.py', kind: 'file', language: 'python' },
    { name: 'config.py', kind: 'file', language: 'python' },
  ]},
  { name: 'fastapi', kind: 'folder', open: true, children: [
    { name: 'routing.py', kind: 'file', language: 'python' },
    { name: 'applications.py', kind: 'file', language: 'python' },
    { name: 'middleware', kind: 'folder', open: true, children: [
      { name: 'cors.py', kind: 'file', language: 'python' },
      { name: 'gzip.py', kind: 'file', language: 'python' },
    ]},
  ]},
  { name: 'tests', kind: 'folder', children: [{ name: 'test_routing.py', kind: 'file', language: 'python' }]},
  { name: 'pyproject.toml', kind: 'file', language: 'toml' },
  { name: 'README.md', kind: 'file', language: 'markdown' },
]

const codeLines = [
  'from starlette.middleware.base import BaseHTTPMiddleware',
  'from fastapi import FastAPI, Request',
  '',
  'class CORSMiddleware(BaseHTTPMiddleware):',
  '    """Middleware that adds CORS headers to responses."""',
  '',
  '    async def dispatch(self, request: Request, call_next):',
  '        response = await call_next(request)',
  '        response.headers["Access-Control-Allow-Origin"] = "*"',
  '        response.headers["Access-Control-Allow-Methods"] = "*"',
  '        response.headers["Access-Control-Allow-Headers"] = "*"',
  '        return response',
]

const starterAnswer = {
  question: 'How does middleware work in FastAPI?',
  answer: 'FastAPI middleware is built on Starlette\'s ASGI middleware system. Middleware wraps every request and response, letting you run logic before a request reaches a path operation and after it returns.\n\nYou can add middleware with `app.add_middleware()` or the `@app.middleware("http")` decorator. Each middleware receives the request and a `call_next` function that passes control to the next layer.',
  sources: ['fastapi/applications.py:455-489', 'fastapi/middleware/cors.py:8-24'],
}

function RepoMark({ small = false }: { small?: boolean }) {
  return <div className={`flex items-center gap-2 ${small ? 'text-sm' : ''}`}><div className="repo-mark"><span /></div><span className="font-semibold tracking-tight">RepoMind</span></div>
}

function FileTree({ onFile }: { onFile: (name: string) => void }) {
  const render = (items: any[], depth = 0): React.ReactNode => items.map((item) => (
    <div key={item.name}>
      <button onClick={() => item.kind === 'file' && onFile(item.name)} className="tree-row" style={{ paddingLeft: `${12 + depth * 16}px` }}>
        {item.kind === 'folder' ? <ChevronDown size={13} className="text-muted-foreground" /> : <span className="w-[13px]" />}
        {item.kind === 'folder' ? <Folder size={14} className="text-blue-400" /> : <FileCode2 size={14} className="text-muted-foreground" />}
        <span className="truncate">{item.name}</span>
      </button>
      {item.kind === 'folder' && item.open && render(item.children, depth + 1)}
    </div>
  ))
  return <div className="space-y-0.5">{render(files)}</div>
}

function SourceDrawer({ file, onClose }: { file: string; onClose: () => void }) {
  return <div className="fixed inset-0 z-50 flex justify-end bg-black/50" onClick={onClose}>
    <aside className="source-drawer" onClick={(e) => e.stopPropagation()}>
      <header className="flex items-center justify-between border-b border-border px-5 py-4">
        <div><p className="font-mono text-xs text-blue-400">fastapi / {file}</p><p className="mt-1 text-xs text-muted-foreground">Python · 12 relevant lines</p></div>
        <button className="icon-button" onClick={onClose} aria-label="Close source viewer"><X size={17} /></button>
      </header>
      <div className="flex items-center gap-3 border-b border-border px-5 py-3 text-xs text-muted-foreground"><Code2 size={14} /> Source viewer <span className="ml-auto rounded bg-blue-500/10 px-2 py-1 text-blue-300">highlighted</span></div>
      <div className="overflow-auto p-4"><pre className="code-viewer">{codeLines.map((line, i) => <div key={i} className={i >= 7 && i <= 10 ? 'code-highlight' : ''}><span className="line-number">{i + 1}</span><code>{line || ' '}</code></div>)}</pre></div>
    </aside>
  </div>
}

function Indexing({ onReady }: { onReady: () => void }) {
  const [progress, setProgress] = useState(48)
  useMemo(() => { const timer = setTimeout(() => setProgress(100), 800); const done = setTimeout(onReady, 1450); return () => { clearTimeout(timer); clearTimeout(done) } }, [onReady])
  const steps = ['Cloning repository', 'Parsing files', 'Building embeddings', 'Ready']
  return <main className="grid-bg flex min-h-screen items-center justify-center px-5"><div className="w-full max-w-lg animate-in-up">
    <div className="mb-10 flex justify-center"><RepoMark /></div>
    <div className="panel p-7 sm:p-9"><div className="mb-8 flex items-start gap-4"><div className="rounded-lg bg-blue-500/10 p-3 text-blue-400"><GitBranch size={21} /></div><div><p className="font-mono text-xs text-blue-400">github.com/tiangolo/fastapi</p><h1 className="mt-1 text-xl font-semibold">Indexing repository</h1><p className="mt-1 text-sm text-muted-foreground">This usually takes less than a minute.</p></div></div>
      <div className="mb-8 h-2 overflow-hidden rounded-full bg-secondary"><div className="h-full rounded-full bg-blue-500 transition-all duration-1000" style={{ width: `${progress}%` }} /></div>
      <div className="space-y-4">{steps.map((step, i) => { const done = progress === 100 || i < 2; return <div key={step} className="flex items-center gap-3 text-sm"><div className={done ? 'step-dot done' : i === 2 ? 'step-dot active' : 'step-dot'}>{done ? <Check size={12} /> : i === 2 ? <span /> : null}</div><span className={done ? 'text-foreground' : 'text-muted-foreground'}>{step}</span>{i === 1 && <span className="ml-auto font-mono text-xs text-muted-foreground">{progress === 100 ? '342 / 342' : '142 / 342'} files</span>}</div>})}</div>
    </div><p className="mt-5 text-center font-mono text-xs text-muted-foreground">Powered by RepoMind retrieval engine</p>
  </div></main>
}

function Landing({ onIndex }: { onIndex: () => void }) {
  const [url, setUrl] = useState('')
  return <main className="grid-bg min-h-screen"><header className="mx-auto flex max-w-6xl items-center justify-between px-6 py-6"><RepoMark /><span className="font-mono text-xs text-muted-foreground">v1.0 / private beta</span></header><section className="mx-auto flex max-w-3xl flex-col items-center px-6 pb-24 pt-24 text-center sm:pt-32"><div className="mb-7 flex items-center gap-2 rounded-full border border-blue-500/20 bg-blue-500/5 px-3 py-1.5 font-mono text-xs text-blue-300"><Zap size={13} /> grounded code intelligence</div><h1 className="text-balance text-5xl font-semibold tracking-[-0.045em] sm:text-7xl">Understand any<br /><span className="text-blue-400">codebase</span>, instantly.</h1><p className="mt-7 max-w-xl text-pretty text-base leading-7 text-muted-foreground sm:text-lg">Ask questions in plain English. Get clear answers grounded in your repository, with every claim linked back to the exact lines of code.</p><div className="mt-10 flex w-full flex-col gap-2 rounded-xl border border-border bg-card p-2 shadow-2xl shadow-blue-950/10 sm:flex-row"><div className="flex min-w-0 flex-1 items-center gap-3 px-3"><GitBranch size={18} className="shrink-0 text-muted-foreground" /><input value={url} onChange={(e) => setUrl(e.target.value)} onKeyDown={(e) => e.key === 'Enter' && onIndex()} placeholder="Paste a GitHub repository URL" className="min-w-0 flex-1 bg-transparent py-3 text-sm outline-none placeholder:text-muted-foreground/60" /></div><button onClick={onIndex} className="primary-button"><Search size={16} /> Index Repository <ArrowUp size={14} className="rotate-45" /></button></div><div className="mt-5 flex flex-wrap justify-center gap-2"><span className="mr-1 py-2 text-xs text-muted-foreground">Try a demo:</span>{['FastAPI', 'Requests', 'Flask'].map((repo) => <button key={repo} onClick={onIndex} className="chip-button"><GitBranch size={13} /> {repo}</button>)}</div><div className="mt-24 grid w-full grid-cols-1 gap-3 text-left sm:grid-cols-3"><div className="feature-card"><MessageSquare size={18} className="text-blue-400" /><p className="mt-5 font-medium">Ask naturally</p><p className="mt-2 text-sm leading-6 text-muted-foreground">No query language. Just ask what you need to know.</p></div><div className="feature-card"><BookOpen size={18} className="text-blue-400" /><p className="mt-5 font-medium">Trust the answer</p><p className="mt-2 text-sm leading-6 text-muted-foreground">Every response includes the source files and line ranges.</p></div><div className="feature-card"><Code2 size={18} className="text-blue-400" /><p className="mt-5 font-medium">Go deeper</p><p className="mt-2 text-sm leading-6 text-muted-foreground">Jump directly into highlighted code when context matters.</p></div></div></section></main>
}

function Workspace({ onReset }: { onReset: () => void }) {
  const [sidebar, setSidebar] = useState(true); const [drawer, setDrawer] = useState<string | null>(null); const [input, setInput] = useState(''); const [messages, setMessages] = useState<any[]>([starterAnswer]); const [loading, setLoading] = useState(false); const [noResult, setNoResult] = useState(false)
  const ask = () => { if (!input.trim() || loading) return; const question = input.trim(); setInput(''); setLoading(true); setNoResult(false); setTimeout(() => { const empty = /pricing|weather|hello/i.test(question); setNoResult(empty); setMessages((m) => [...m, { question, answer: empty ? '' : 'The repository uses a layered ASGI architecture. Requests enter through the application instance, pass through registered middleware, and are dispatched to a matching route. Dependencies are resolved before the endpoint is called, then the response travels back through the same middleware stack.', sources: ['fastapi/applications.py:455-489', 'fastapi/routing.py:716-741'] }]); setLoading(false) }, 1100) }
  return <main className="flex h-screen overflow-hidden bg-background"><aside className={`${sidebar ? 'w-[276px]' : 'w-0'} sidebar shrink-0 overflow-hidden transition-all duration-300`}><div className="flex h-full w-[276px] flex-col"><header className="flex items-center justify-between border-b border-border px-5 py-4"><button onClick={onReset} className="hover:text-blue-400"><RepoMark small /></button><button onClick={() => setSidebar(false)} className="icon-button" aria-label="Collapse sidebar"><PanelLeftClose size={16} /></button></header><div className="border-b border-border px-5 py-4"><div className="flex items-center gap-2"><div className="rounded bg-muted p-1.5"><GitBranch size={15} /></div><div className="min-w-0"><p className="truncate text-sm font-medium">tiangolo/fastapi</p><p className="font-mono text-[10px] text-emerald-400">indexed · 342 files</p></div></div></div><div className="flex-1 overflow-y-auto px-3 py-5"><p className="section-label px-2">Files</p><div className="mt-3"><FileTree onFile={(n) => setDrawer(n)} /></div><p className="section-label mt-8 px-2">Recent questions</p><div className="mt-3 space-y-1"><button className="question-link"><MessageSquare size={13} /> How does middleware work?</button><button className="question-link"><MessageSquare size={13} /> Where are routes defined?</button></div></div><footer className="border-t border-border p-4"><button onClick={onReset} className="flex w-full items-center gap-2 rounded-md px-2 py-2 text-xs text-muted-foreground transition hover:bg-muted hover:text-foreground"><X size={14} /> Index another repository</button></footer></div></aside><section className="flex min-w-0 flex-1 flex-col"><header className="flex h-[57px] shrink-0 items-center justify-between border-b border-border px-4 sm:px-6"><div className="flex items-center gap-3">{!sidebar && <button onClick={() => setSidebar(true)} className="icon-button" aria-label="Open sidebar"><PanelLeftOpen size={17} /></button>}<div className="flex items-center gap-2 text-sm"><span className="font-mono text-muted-foreground">fastapi</span><ChevronRight size={13} className="text-muted-foreground" /><span className="text-muted-foreground">Ask RepoMind</span></div></div><div className="flex items-center gap-2"><span className="hidden items-center gap-1.5 rounded-full bg-emerald-500/10 px-2.5 py-1 font-mono text-[10px] text-emerald-400 sm:flex"><CircleDot size={10} /> ready</span><button className="icon-button"><Menu size={17} /></button></div></header><div className="flex-1 overflow-y-auto"><div className="mx-auto max-w-3xl px-4 py-8 sm:px-8 sm:py-12"><div className="mb-10"><p className="font-mono text-xs text-blue-400">REPOSITORY Q&A</p><h1 className="mt-2 text-2xl font-semibold tracking-tight sm:text-3xl">What would you like to understand?</h1><p className="mt-2 text-sm text-muted-foreground">Answers are generated from <span className="font-mono text-foreground">tiangolo/fastapi</span> and cited to source.</p></div><div className="space-y-8">{messages.map((msg, i) => <div key={`${msg.question}-${i}`} className="animate-in-up"><div className="mb-3 flex items-start gap-3"><div className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-blue-500/10 text-blue-400"><Hash size={13} /></div><p className="text-sm font-medium leading-6">{msg.question}</p></div>{noResult && i === messages.length - 1 ? <div className="empty-answer"><CircleAlert size={18} className="text-amber-400" /><div><p className="font-medium text-amber-200">No relevant code found</p><p className="mt-1 text-sm leading-6 text-muted-foreground">I couldn&apos;t find anything in this repository that answers this question. Try asking about a file, function, or concept in the codebase.</p></div></div> : <div className="answer-card"><div className="whitespace-pre-line text-sm leading-7 text-foreground/90">{msg.answer.split('`').map((part: string, j: number) => j % 2 ? <code key={j} className="rounded bg-muted px-1.5 py-0.5 font-mono text-xs text-blue-300">{part}</code> : part)}</div><div className="mt-7 border-t border-border pt-4"><p className="section-label mb-3">Sources</p><div className="flex flex-wrap gap-2">{msg.sources.map((source: string) => <button key={source} onClick={() => setDrawer(source.split(':')[0].split('/').pop() || source)} className="source-chip"><FileCode2 size={13} />{source}<ArrowUp size={12} className="rotate-45 opacity-50" /></button>)}</div></div></div>}</div>)}{loading && <div className="flex items-center gap-3 text-sm text-muted-foreground"><div className="flex h-6 w-6 items-center justify-center rounded-full bg-blue-500/10 text-blue-400"><Sparkles size={13} className="animate-pulse" /></div><span className="animate-pulse">Searching codebase...</span></div>}</div></div></div><div className="mx-auto w-full max-w-3xl px-4 pb-5 sm:px-8"><div className="composer"><textarea value={input} onChange={(e) => setInput(e.target.value)} onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing && e.keyCode !== 229) { e.preventDefault(); ask() } }} placeholder="Ask anything about this codebase..." rows={2} /><div className="flex items-center justify-between"><span className="font-mono text-[10px] text-muted-foreground">shift + enter for new line</span><button onClick={ask} disabled={!input.trim() || loading} className="send-button" aria-label="Send question"><Send size={15} /></button></div></div><p className="mt-2 text-center font-mono text-[10px] text-muted-foreground/60">RepoMind can make mistakes. Verify important details in the source.</p></div></section>{drawer && <SourceDrawer file={drawer} onClose={() => setDrawer(null)} />}</main>
}

export default function Page() { const [screen, setScreen] = useState<'landing' | 'indexing' | 'workspace'>('landing'); if (screen === 'landing') return <Landing onIndex={() => setScreen('indexing')} />; if (screen === 'indexing') return <Indexing onReady={() => setScreen('workspace')} />; return <Workspace onReset={() => setScreen('landing')} /> }
