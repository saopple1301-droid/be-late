import { NavLink } from 'react-router-dom'

export function BottomNav() {
  return (
    <nav className="bottom-nav">
      <NavLink to="/" end className={({ isActive }) => (isActive ? 'active' : '')}>
        ホーム
      </NavLink>
      <NavLink to="/groups/new" className={({ isActive }) => (isActive ? 'active' : '')}>
        グループ作成
      </NavLink>
      <NavLink to="/groups/join" className={({ isActive }) => (isActive ? 'active' : '')}>
        参加
      </NavLink>
      <NavLink to="/account" className={({ isActive }) => (isActive ? 'active' : '')}>
        アカウント
      </NavLink>
    </nav>
  )
}
