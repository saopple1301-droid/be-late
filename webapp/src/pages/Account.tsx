import { useEffect, useState } from 'react'
import { api } from '../api'
import { logout } from '../auth'
import type { Me } from '../types'

export function Account() {
  const [me, setMe] = useState<Me | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    api
      .get<Me>('/api/me')
      .then(setMe)
      .catch((err) => setError(err instanceof Error ? err.message : String(err)))
  }, [])

  async function registerCard() {
    setBusy(true)
    setError(null)
    try {
      const { url } = await api.post<{ url: string }>('/api/card-setup')
      window.location.href = url
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
      setBusy(false)
    }
  }

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
              決済カード:{' '}
              {me.has_payment_method ? (
                <span className="badge badge-ok">登録済み</span>
              ) : (
                <span className="badge badge-warn">未登録</span>
              )}
            </p>
            <p className="muted">
              払い戻し用口座(Stripe Connect):{' '}
              {me.payout_ready ? (
                <span className="badge badge-ok">設定済み</span>
              ) : (
                <span className="badge badge-warn">未設定（自動払い戻しには必要です）</span>
              )}
            </p>
          </div>
        )}

        <button className="btn-primary" onClick={registerCard} disabled={busy}>
          {me?.has_payment_method ? 'カードを更新する' : 'デポジット用カードを登録する'}
        </button>
        <div className="spacer" />
        <button className="btn-secondary" onClick={logout}>
          ログアウト
        </button>
      </main>
    </>
  )
}
