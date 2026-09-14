import { useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { api } from '../api'
import type { Member, MeetupSummary } from '../types'

const DEPOSIT_OPTIONS = [100, 300, 500, 1000, 2000]

function defaultDateTimeLocal(): string {
  const d = new Date(Date.now() + 60 * 60 * 1000)
  d.setSeconds(0, 0)
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`
}

export function MeetupCreate() {
  const { groupId } = useParams()
  const navigate = useNavigate()

  const [members, setMembers] = useState<Member[]>([])
  const [selected, setSelected] = useState<Set<number>>(new Set())
  const [deposit, setDeposit] = useState(DEPOSIT_OPTIONS[1])
  const [place, setPlace] = useState('')
  const [scheduledAt, setScheduledAt] = useState(defaultDateTimeLocal())
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    api.get<Member[]>(`/api/groups/${groupId}/members`).then(setMembers).catch((err) => setError(String(err)))
  }, [groupId])

  function toggle(id: number) {
    setSelected((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  async function submit() {
    if (selected.size === 0) {
      setError('少なくとも1人選んでください。')
      return
    }
    if (!place.trim()) {
      setError('集合場所を入力してください。')
      return
    }
    setBusy(true)
    setError(null)
    try {
      const meetup = await api.post<MeetupSummary>(`/api/groups/${groupId}/meetups`, {
        member_ids: Array.from(selected),
        deposit_amount: deposit,
        place_name: place.trim(),
        scheduled_at: new Date(scheduledAt).toISOString(),
      })
      navigate(`/meetups/${meetup.id}`)
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
      setBusy(false)
    }
  }

  return (
    <>
      <header className="app-header">
        <h1 style={{ margin: 0 }}>待ち合わせを作成</h1>
      </header>
      <main>
        {error && <p className="error-text">{error}</p>}

        <label className="field-label">一緒に待ち合わせる友達</label>
        <div className="chip-list">
          {members.map((m) => (
            <div
              key={m.id}
              className={`chip ${selected.has(m.id) ? 'selected' : ''}`}
              onClick={() => toggle(m.id)}
            >
              {m.display_name || '(名前未設定)'}
            </div>
          ))}
          {members.length === 0 && <p className="muted">グループにまだ他のメンバーがいません。</p>}
        </div>

        <label className="field-label">1人あたりのデポジット</label>
        <div className="chip-list">
          {DEPOSIT_OPTIONS.map((amount) => (
            <div
              key={amount}
              className={`chip ${deposit === amount ? 'selected' : ''}`}
              onClick={() => setDeposit(amount)}
            >
              ¥{amount}
            </div>
          ))}
        </div>

        <label className="field-label">集合場所</label>
        <input value={place} onChange={(e) => setPlace(e.target.value)} placeholder="例: 渋谷駅ハチ公口" />

        <label className="field-label">集合時刻</label>
        <input type="datetime-local" value={scheduledAt} onChange={(e) => setScheduledAt(e.target.value)} />

        <button className="btn-primary" onClick={submit} disabled={busy}>
          確定してデポジットを請求する
        </button>
      </main>
    </>
  )
}
