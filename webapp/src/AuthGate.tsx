import { useEffect, useState, type ReactNode } from 'react'
import { ensureLoggedIn } from './auth'

export function AuthGate({ children }: { children: ReactNode }) {
  const [ready, setReady] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    ensureLoggedIn()
      .then(() => setReady(true))
      .catch((err) => setError(err instanceof Error ? err.message : String(err)))
  }, [])

  if (error) {
    return (
      <div className="center-screen">
        <h2>ログインできませんでした</h2>
        <p className="muted">{error}</p>
        <p className="muted">LINEアプリ内、またはLIFFブラウザから開いてください。</p>
      </div>
    )
  }

  if (!ready) {
    return (
      <div className="center-screen">
        <p className="muted">読み込み中…</p>
      </div>
    )
  }

  return <>{children}</>
}
