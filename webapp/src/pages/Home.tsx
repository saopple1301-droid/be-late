import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api'
import type { Group, MeetupSummary } from '../types'

const STATUS_LABEL: Record<string, string> = {
  draft: '準備中',
  collecting_deposit: 'デポジット確保中',
  doubt_phase: 'ダウト予想中',
  active: '進行中',
  settling: '精算中',
  completed: '完了',
  cancelled: 'キャンセル',
}

export function Home() {
  const [groups, setGroups] = useState<Group[] | null>(null)
  const [meetups, setMeetups] = useState<MeetupSummary[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    Promise.all([api.get<Group[]>('/api/groups'), api.get<MeetupSummary[]>('/api/meetups')])
      .then(([g, m]) => {
        setGroups(g)
        setMeetups(m)
      })
      .catch((err) => setError(err instanceof Error ? err.message : String(err)))
  }, [])

  const activeMeetups = meetups?.filter((m) => m.status !== 'completed' && m.status !== 'cancelled') ?? []
  const pastMeetups = meetups?.filter((m) => m.status === 'completed') ?? []

  return (
    <>
      <header className="app-header">
        <h1 style={{ margin: 0 }}>Be Late</h1>
      </header>
      <main>
        {error && <p className="error-text">{error}</p>}

        <h2>進行中の待ち合わせ</h2>
        {activeMeetups.length === 0 && <p className="muted">進行中の待ち合わせはありません。</p>}
        {activeMeetups.map((m) => (
          <Link key={m.id} to={`/meetups/${m.id}`} className="card-link">
            <div className="card">
              <h3>{m.place_name}</h3>
              <p className="muted">{new Date(m.scheduled_at).toLocaleString('ja-JP')}</p>
              <span className="badge badge-muted">{STATUS_LABEL[m.status] ?? m.status}</span>
            </div>
          </Link>
        ))}

        <div className="spacer" />
        <h2>グループ</h2>
        {groups === null && <p className="muted">読み込み中…</p>}
        {groups?.length === 0 && <p className="muted">まだグループがありません。「グループ作成」から始めましょう。</p>}
        {groups?.map((g) => (
          <Link key={g.id} to={`/groups/${g.id}`} className="card-link">
            <div className="card">
              <h3>{g.name}</h3>
              <p className="muted">招待コード: {g.invite_code}</p>
            </div>
          </Link>
        ))}

        {pastMeetups.length > 0 && (
          <>
            <div className="spacer" />
            <h2>過去の待ち合わせ</h2>
            {pastMeetups.map((m) => (
              <Link key={m.id} to={`/meetups/${m.id}`} className="card-link">
                <div className="card">
                  <h3>{m.place_name}</h3>
                  <p className="muted">{new Date(m.scheduled_at).toLocaleString('ja-JP')}</p>
                </div>
              </Link>
            ))}
          </>
        )}
      </main>
    </>
  )
}
