import { BrowserRouter, Route, Routes } from 'react-router-dom'
import { AuthGate } from './AuthGate'
import { BottomNav } from './components/BottomNav'
import { Account } from './pages/Account'
import { GroupCreate } from './pages/GroupCreate'
import { GroupDetail } from './pages/GroupDetail'
import { GroupJoin } from './pages/GroupJoin'
import { Home } from './pages/Home'
import { MeetupCreate } from './pages/MeetupCreate'
import { MeetupDetail } from './pages/MeetupDetail'

function App() {
  return (
    <AuthGate>
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<Home />} />
          <Route path="/groups/new" element={<GroupCreate />} />
          <Route path="/groups/join" element={<GroupJoin />} />
          <Route path="/groups/:groupId" element={<GroupDetail />} />
          <Route path="/groups/:groupId/meetups/new" element={<MeetupCreate />} />
          <Route path="/meetups/:meetupId" element={<MeetupDetail />} />
          <Route path="/account" element={<Account />} />
        </Routes>
        <BottomNav />
      </BrowserRouter>
    </AuthGate>
  )
}

export default App
