import { useState } from 'react'
import { api } from './api'
import Wardrobe from './Wardrobe.jsx'
import Avatar from './Avatar.jsx'

// The shell shown once you are logged in: the top bar, the tabs, and whichever
// screen the active tab points to. More tabs (Outfits, Saved) come next.
const TABS = [
  { key: 'wardrobe', label: 'Wardrobe' },
  { key: 'avatar', label: 'Avatar' },
]

export default function Home({ user, onLogout }) {
  const [tab, setTab] = useState('wardrobe')

  async function logout() {
    await api.logout()
    onLogout()
  }

  return (
    <div className="app">
      <header className="topbar">
        <strong>Outfit Picker</strong>
        <nav className="tabs">
          {TABS.map((t) => (
            <button
              key={t.key}
              className={`tab ${tab === t.key ? 'active' : ''}`}
              onClick={() => setTab(t.key)}
            >
              {t.label}
            </button>
          ))}
        </nav>
        <span className="muted small">{user.email}</span>
        <button className="link" onClick={logout}>
          Log out
        </button>
      </header>

      <main>
        {tab === 'wardrobe' && <Wardrobe />}
        {tab === 'avatar' && <Avatar />}
      </main>
    </div>
  )
}
