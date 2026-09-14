import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { api } from '../api'
import type { Group, Member } from '../types'

export function GroupDetail() {
  const { groupId } = useParams()
  const [group, setGroup] = useState<Group | null>(null)
  const [members, setMembers] = useState<Member[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    api
      .get<Group[]>('/api/groups')
      .then((groups) => setGroup(groups.find((g) => String(g.id) === groupId) ?? null))
      .catch((err) => setError(err instanceof Error ? err.message : String(err)))
    api
      .get<Member[]>(`/api/groups/${groupId}/members`)
      .then(setMembers)
      .catch((err) => setError(err instanceof Error ? err.message : String(err)))
  }, [groupId])

  return (
    <>
      <header className="app-header">
        <h1 style={{ margin: 0 }}>{group?.name ?? 'グループ'}</h1>
      </header>
      <main>
        {error && <p className="error-text">{error}</p>}
        {group && (
          <div className="card">
            <p className="muted">招待コード</p>
            <h3>{group.invite_code}</h3>
            <p className="muted">このコードを友達に共有すると参加できます。</p>
          </div>
        )}

        <h2>メンバー</h2>
        {members?.map((m) => (
          <div className="card" key={m.id}>
            {m.display_name || '(名前未設定)'}
          </div>
        ))}

        <div className="spacer" />
        <Link to={`/groups/${groupId}/meetups/new`} className="btn btn-primary">
          待ち合わせを作成する
        </Link>
      </main>
    </>
  )
}
