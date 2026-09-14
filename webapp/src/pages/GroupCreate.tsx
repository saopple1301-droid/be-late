import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../api'
import type { Group } from '../types'

export function GroupCreate() {
  const [name, setName] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const navigate = useNavigate()

  async function submit() {
    setBusy(true)
    setError(null)
    try {
      const group = await api.post<Group>('/api/groups', { name })
      navigate(`/groups/${group.id}`)
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
      setBusy(false)
    }
  }

  return (
    <>
      <header className="app-header">
        <h1 style={{ margin: 0 }}>グループ作成</h1>
      </header>
      <main>
        {error && <p className="error-text">{error}</p>}
        <label className="field-label">グループ名</label>
        <input value={name} onChange={(e) => setName(e.target.value)} placeholder="例: サークルの友達" />
        <button className="btn-primary" onClick={submit} disabled={busy || !name.trim()}>
          作成する
        </button>
        <p className="muted" style={{ marginTop: 12 }}>
          作成後に表示される招待コードを友達に共有すると、グループに参加できます。
        </p>
      </main>
    </>
  )
}
