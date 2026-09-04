'use client'

import Link from 'next/link'
import { FormEvent, useState } from 'react'

export default function LoginPage() {
  const [submitted, setSubmitted] = useState(false)
  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    setSubmitted(true)
  }

  return <main className="grid-bg flex min-h-screen items-center justify-center px-5 py-12"><div className="panel w-full max-w-md p-7 sm:p-9"><Link href="/" className="inline-flex items-center gap-2 text-sm text-muted-foreground transition-colors hover:text-foreground" aria-label="Back to home"><span aria-hidden="true">←</span> Back to home</Link><Link href="/" className="mt-6 block w-fit font-semibold tracking-tight text-foreground">RepoMind</Link><div className="mt-8"><p className="font-mono text-xs uppercase tracking-widest text-blue-400">Welcome back</p><h1 className="mt-2 text-3xl font-semibold">Log in to RepoMind</h1><p className="mt-3 text-sm leading-6 text-muted-foreground">Continue exploring your codebase with grounded answers.</p></div>{submitted ? <div className="mt-7 rounded-lg border border-emerald-500/20 bg-emerald-500/10 p-4 text-sm text-emerald-300">Login is ready for connection. Your form was submitted successfully.</div> : <form onSubmit={submit} className="mt-7 space-y-4"><label className="block text-sm"><span className="mb-2 block text-muted-foreground">Email</span><input required type="email" className="w-full rounded-md border border-border bg-background px-3 py-2.5 outline-none focus:border-blue-400" placeholder="you@example.com" /></label><label className="block text-sm"><span className="mb-2 block text-muted-foreground">Password</span><input required minLength={6} type="password" className="w-full rounded-md border border-border bg-background px-3 py-2.5 outline-none focus:border-blue-400" placeholder="Your password" /></label><button type="submit" className="primary-button w-full justify-center">Log in</button></form>}<p className="mt-7 text-center text-sm text-muted-foreground">New to RepoMind? <Link href="/signup" className="text-blue-400 hover:text-blue-300">Create an account</Link></p></div></main>
}
