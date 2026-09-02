import { useEffect, useState } from 'react'
import { api } from './api'
import Login from './Login.jsx'
import Home from './Home.jsx'

// The top of the app. Its only job: figure out if someone is logged in, then
// show either the Login screen or the Wardrobe.
export default function App() {
  const [user, setUser] = useState(null)   // who is logged in (null = nobody)
  const [loading, setLoading] = useState(true)

  // When the app first loads, ask the backend "who am I?". If the cookie is
  // valid we get the user; if not, /users/me returns 401 and we stay logged out.
  useEffect(() => {
    api
      .me()
      .then(setUser)
      .catch(() => setUser(null))
      .finally(() => setLoading(false))
  }, [])

  if (loading) return <div className="center muted">Loading…</div>
  if (!user) return <Login onLoggedIn={setUser} />
  return <Home user={user} onLogout={() => setUser(null)} />
}
