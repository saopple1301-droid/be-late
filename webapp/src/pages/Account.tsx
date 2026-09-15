import { useEffect, useState } from 'react'
import { api } from '../api'
import { logout } from '../auth'
import type { Me } from '../types'

export function Account() {
  const [me, setMe] = useState<Me | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    api
      .get<Me>('/api/me')
      .then(setMe)
      .catch((err) => setError(err instanceof Error ? err.message : String(err)))
  }, [])

  return (
    <>
      <header className="app-header">
        <h1 style={{ margin: 0 }}>アカウント</h1>
      </header>
      <main>
        {error && <p className="error-text">{error}</p>}
        {me && (
          <div className="card">
            <h3>{me.display_name || '(名前未設定)'}</h3>
            <p className="muted">
              このデモ環境ではデポジット・ペナルティの決済は発生しません（すべてシミュレーションです）。
            </p>
          </div>
        )}

        <button className="btn-secondary" onClick={logout}>
          ログアウト
        </button>
      </main>
    </>
  )
}
