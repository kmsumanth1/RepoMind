export default function SignupLoading() {
  return (
    <main className="grid-bg relative flex min-h-screen items-center justify-center px-5 py-12" aria-busy="true" aria-label="Loading signup">
      <div className="panel w-full max-w-md animate-pulse p-7 sm:p-9">
        <div className="h-5 w-28 rounded bg-muted" />
        <div className="mt-10 h-3 w-24 rounded bg-muted" />
        <div className="mt-3 h-10 w-72 rounded bg-muted" />
        <div className="mt-4 h-5 w-full rounded bg-muted" />
        <div className="mt-8 space-y-4">
          <div className="h-11 rounded-md bg-muted" />
          <div className="h-11 rounded-md bg-muted" />
          <div className="h-10 rounded-md bg-muted" />
        </div>
      </div>
    </main>
  )
}
