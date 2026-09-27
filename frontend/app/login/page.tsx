'use client'

import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { FormEvent, useState } from 'react'
import { useAuth } from '@/lib/auth-context'
import { ApiError } from '@/lib/api'

export default function LoginPage() {
  const router = useRouter()
  const { login } = useAuth()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    setError(null)
    setSubmitting(true)
    try {
      await login(email, password)
      router.push('/dashboard')
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        setError('Incorrect email or password.')
      } else if (err instanceof ApiError && err.status === 429) {
        setError('Too many attempts. Please wait a moment and try again.')
      } else {
        setError(err instanceof Error ? err.message : 'Something went wrong. Please try again.')
      }
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <main className="grid-bg relative flex min-h-screen items-center justify-center px-5 py-12">
      <div className="panel w-full max-w-md p-7 sm:p-9">
        <Link
          href="/"
          className="inline-flex items-center gap-2 text-sm text-muted-foreground transition-colors hover:text-foreground"
          aria-label="Back to home"
        >
          <span aria-hidden="true">←</span> Back to home
        </Link>
        <div className="mt-6">
          <Link href="/" className="block w-fit font-semibold tracking-tight text-foreground">
            RepoMind
          </Link>
        </div>
        <div className="mt-8">
          <p className="font-mono text-xs uppercase tracking-widest text-blue-400">Welcome back</p>
          <h1 className="mt-2 text-3xl font-semibold">Log in to RepoMind</h1>
          <p className="mt-3 text-sm leading-6 text-muted-foreground">
            Continue exploring your codebase with grounded answers.
          </p>
        </div>

        {error && (
          <div className="mt-7 rounded-lg border border-red-500/20 bg-red-500/10 p-4 text-sm text-red-300">
            {error}
          </div>
        )}

        <form onSubmit={submit} className="mt-7 space-y-4">
          <label className="block text-sm">
            <span className="mb-2 block text-muted-foreground">Email</span>
            <input
              required
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="w-full rounded-md border border-border bg-background px-3 py-2.5 outline-none focus:border-blue-400"
              placeholder="you@example.com"
            />
          </label>
          <label className="block text-sm">
            <span className="mb-2 block text-muted-foreground">Password</span>
            <input
              required
              minLength={6}
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full rounded-md border border-border bg-background px-3 py-2.5 outline-none focus:border-blue-400"
              placeholder="Your password"
            />
          </label>
          <button type="submit" disabled={submitting} className="primary-button w-full justify-center disabled:opacity-60">
            {submitting ? 'Logging in…' : 'Log in'}
          </button>
        </form>

        <p className="mt-7 text-center text-sm text-muted-foreground">
          New to RepoMind?{' '}
          <Link href="/signup" className="text-blue-400 hover:text-blue-300">
            Create an account
          </Link>
        </p>
      </div>
    </main>
  )
}
