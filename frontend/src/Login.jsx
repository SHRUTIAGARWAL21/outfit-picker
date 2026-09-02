import { useState } from 'react'
import { api } from './api'
import Flower from './Flower.jsx'

// The landing page: a pretty welcome with the "diva" tagline and flowers,
// plus the login / signup form. One form does both, toggled by `mode`.
export default function Login({ onLoggedIn }) {
  const [mode, setMode] = useState('login') // 'login' or 'signup'
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  async function submit(e) {
    e.preventDefault()
    setError('')
    setBusy(true)
    try {
      if (mode === 'signup') await api.signup(email, password)
      const user = await api.login(email, password)
      onLoggedIn(user)
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="center">
      <div className="landing">
        <div className="flowers-row">
          <Flower size={34} petal="#e6b7e8" center="#f7a8cb" />
          <Flower size={52} petal="#f7a8cb" center="#c9a7ef" />
          <Flower size={34} petal="#c9a7ef" center="#f7a8cb" />
        </div>

        <div className="diva">Let me help you to be the diva</div>
        <p className="tag">Style outfits from the clothes you already own. 🌸</p>

        <form className="card auth" onSubmit={submit}>
          <h2>{mode === 'login' ? 'Welcome back, gorgeous' : 'Join the wardrobe'}</h2>
          <p className="sub">{mode === 'login' ? 'Log in to your closet.' : 'Create your account.'}</p>

          <label>Email</label>
          <input
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
            autoComplete="email"
          />

          <label>Password</label>
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
            minLength={8}
            autoComplete={mode === 'login' ? 'current-password' : 'new-password'}
          />

          {error && <div className="error">{error}</div>}

          <button type="submit" disabled={busy}>
            {busy ? 'Please wait…' : mode === 'login' ? 'Log in' : 'Sign up'}
          </button>

          <p className="muted small" style={{ marginTop: 6 }}>
            {mode === 'login' ? "New here?" : 'Already have an account?'}{' '}
            <button
              type="button"
              className="link"
              onClick={() => {
                setError('')
                setMode(mode === 'login' ? 'signup' : 'login')
              }}
            >
              {mode === 'login' ? 'Sign up' : 'Log in'}
            </button>
          </p>
        </form>
      </div>
    </div>
  )
}
