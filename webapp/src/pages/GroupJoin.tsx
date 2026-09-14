import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../api'
import type { Group } from '../types'

export function GroupJoin() {
  const [code, setCode] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const navigate = useNavigate()

  async function submit() {
    setBusy(true)
    setError(null)
    try {
      const group = await api.post<Group>('/api/groups/join', { invite_code: code.trim() })
      navigate(`/groups/${group.id}`)
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
      setBusy(false)
    }
  }

  return (
    <>
      <header className="app-header">
        <h1 style={{ margin: 0 }}>グループに参加</h1>
      </header>
      <main>
        {error && <p className="error-text">{error}</p>}
        <label className="field-label">招待コード</label>
        <input value={code} onChange={(e) => setCode(e.target.value)} placeholder="友達から受け取ったコード" />
        <button className="btn-primary" onClick={submit} disabled={busy || !code.trim()}>
          参加する
        </button>
      </main>
    </>
  )
}
