import { useCallback, useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { api, ApiError } from '../api'
import { LocationMap } from '../components/LocationMap'
import type { DoubtTarget, LocationEntry, Me, MeetupDetail as MeetupDetailT, SettlementRow } from '../types'

const STATUS_LABEL: Record<string, string> = {
  draft: '準備中',
  collecting_deposit: 'デポジット確保中',
  doubt_phase: 'ダウト予想中',
  active: '進行中',
  settling: '精算中',
  completed: '完了',
  cancelled: 'キャンセル',
}

const LATE_MINUTE_OPTIONS = [5, 10, 15, 20, 30, 60]

const POLL_INTERVAL_MS = 15000

export function MeetupDetail() {
  const { meetupId } = useParams()
  const [meetup, setMeetup] = useState<MeetupDetailT | null>(null)
  const [me, setMe] = useState<Me | null>(null)
  const [locations, setLocations] = useState<LocationEntry[]>([])
  const [doubts, setDoubts] = useState<DoubtTarget[] | null>(null)
  const [settlement, setSettlement] = useState<SettlementRow[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const refresh = useCallback(async () => {
    if (!meetupId) return
    try {
      const detail = await api.get<MeetupDetailT>(`/api/meetups/${meetupId}`)
      setMeetup(detail)
      const locs = await api.get<LocationEntry[]>(`/api/meetups/${meetupId}/locations`)
      setLocations(locs)

      if (detail.status === 'doubt_phase') {
        setDoubts(await api.get<DoubtTarget[]>(`/api/meetups/${meetupId}/doubts`))
      }
      if (detail.status === 'completed') {
        setSettlement(await api.get<SettlementRow[]>(`/api/meetups/${meetupId}/settlement`))
      }
    } catch (err) {
      if (err instanceof ApiError && err.status === 400) return // phase not open yet etc.
      setError(err instanceof Error ? err.message : String(err))
    }
  }, [meetupId])

  useEffect(() => {
    api.get<Me>('/api/me').then(setMe).catch(() => {})
    refresh()
    const timer = setInterval(refresh, POLL_INTERVAL_MS)
    return () => clearInterval(timer)
  }, [refresh])

  async function arrive() {
    setBusy(true)
    try {
      await api.post(`/api/meetups/${meetupId}/arrive`)
      await refresh()
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setBusy(false)
    }
  }

  async function declareLate(minutes: number) {
    setBusy(true)
    try {
      await api.post(`/api/meetups/${meetupId}/declare-late`, { minutes })
      await refresh()
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setBusy(false)
    }
  }

  async function shareLocation() {
    if (!navigator.geolocation) {
      setError('この端末は位置情報に対応していません。')
      return
    }
    setBusy(true)
    navigator.geolocation.getCurrentPosition(
      async (pos) => {
        try {
          await api.post(`/api/meetups/${meetupId}/location`, {
            latitude: pos.coords.latitude,
            longitude: pos.coords.longitude,
          })
          await refresh()
        } catch (err) {
          setError(err instanceof Error ? err.message : String(err))
        } finally {
          setBusy(false)
        }
      },
      (err) => {
        setError(`位置情報の取得に失敗しました: ${err.message}`)
        setBusy(false)
      },
    )
  }

  async function vote(targetId: number, predictedLate: boolean) {
    setBusy(true)
    try {
      await api.post(`/api/meetups/${meetupId}/doubts`, { target_id: targetId, predicted_late: predictedLate })
      setDoubts(await api.get<DoubtTarget[]>(`/api/meetups/${meetupId}/doubts`))
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setBusy(false)
    }
  }

  if (error && !meetup) {
    return (
      <main>
        <p className="error-text">{error}</p>
      </main>
    )
  }
  if (!meetup) {
    return (
      <main>
        <p className="muted">読み込み中…</p>
      </main>
    )
  }

  const myRow = me ? meetup.participants.find((p) => p.user_id === me.id) : undefined

  return (
    <>
      <header className="app-header">
        <h1 style={{ margin: 0 }}>{meetup.place_name}</h1>
      </header>
      <main>
        {error && <p className="error-text">{error}</p>}

        <div className="card">
          <p className="muted">{new Date(meetup.scheduled_at).toLocaleString('ja-JP')}</p>
          <span className="badge badge-muted">{STATUS_LABEL[meetup.status] ?? meetup.status}</span>
        </div>

        {myRow && !myRow.arrived && (meetup.status === 'active' || meetup.status === 'collecting_deposit' || meetup.status === 'doubt_phase') && (
          <button className="btn-primary" onClick={arrive} disabled={busy}>
            到着しました
          </button>
        )}

        {myRow?.is_late && !myRow.arrived && !myRow.declared_minutes && (
          <div className="card">
            <h3>何分以内に到着できますか？</h3>
            <div className="chip-list">
              {LATE_MINUTE_OPTIONS.map((m) => (
                <div key={m} className="chip" onClick={() => declareLate(m)}>
                  {m}分以内
                </div>
              ))}
            </div>
          </div>
        )}

        {myRow?.declared_minutes && !myRow.arrived && (
          <div className="card">
            <p>
              <span className="badge badge-warn">遅刻中</span> {myRow.declared_minutes}分以内に到着すると申告済み
            </p>
            {myRow.declared_deadline_at && (
              <p className="muted">締切: {new Date(myRow.declared_deadline_at).toLocaleTimeString('ja-JP')}</p>
            )}
          </div>
        )}

        <div className="spacer" />
        <h2>メンバー</h2>
        {meetup.participants.map((p) => (
          <div className="card" key={p.user_id}>
            <div style={{ display: 'flex', justifyContent: 'space-between' }}>
              <span>{p.display_name}</span>
              {p.arrived && <span className="badge badge-ok">到着済み</span>}
              {!p.arrived && p.is_late && <span className="badge badge-warn">遅刻中</span>}
              {!p.arrived && !p.is_late && <span className="badge badge-muted">未到着</span>}
            </div>
            {meetup.status === 'completed' && p.payout_amount !== null && (
              <p className="muted">払戻: ¥{p.payout_amount}</p>
            )}
          </div>
        ))}

        <div className="spacer" />
        <h2>現在地</h2>
        <button className="btn-secondary" onClick={shareLocation} disabled={busy}>
          現在地を共有する
        </button>
        <div className="spacer" />
        <LocationMap locations={locations} />

        {doubts && doubts.length > 0 && (
          <>
            <div className="spacer" />
            <h2>ダウト予想</h2>
            <p className="muted">この予想は他のメンバーには一切わかりません。</p>
            {doubts.map((d) => (
              <div className="card" key={d.target_id}>
                <p>{d.display_name} さんは遅刻すると思いますか？</p>
                <div className="btn-row">
                  <button
                    className={d.my_prediction === true ? 'btn-primary' : 'btn-secondary'}
                    onClick={() => vote(d.target_id, true)}
                    disabled={busy}
                  >
                    遅刻すると思う
                  </button>
                  <button
                    className={d.my_prediction === false ? 'btn-primary' : 'btn-secondary'}
                    onClick={() => vote(d.target_id, false)}
                    disabled={busy}
                  >
                    時間通りだと思う
                  </button>
                </div>
              </div>
            ))}
          </>
        )}

        {settlement && (
          <>
            <div className="spacer" />
            <h2>精算結果</h2>
            {settlement.map((row) => (
              <div className="card" key={row.user_id}>
                <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                  <span>{row.display_name}</span>
                  <span className={row.net >= 0 ? 'badge badge-ok' : 'badge badge-warn'}>
                    {row.net >= 0 ? `+¥${row.net}` : `-¥${Math.abs(row.net)}`}
                  </span>
                </div>
              </div>
            ))}
          </>
        )}
      </main>
    </>
  )
}
