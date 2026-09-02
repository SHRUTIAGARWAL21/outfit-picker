import { useState } from 'react'
import { api } from './api'

// The login / signup screen. One form does both, toggled by `mode`.
export default function Login({ onLoggedIn }) {
  const [mode, setMode] = useState('login') // 'login' or 'signup'
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  async function submit(e) {
    e.preventDefault() // stop the browser from reloading the page
    setError('')
    setBusy(true)
    try {
      // Sign-up only creates the account; logging in is what starts the session.
      if (mode === 'signup') await api.signup(email, password)
      const user = await api.login(email, password)
      onLoggedIn(user) // hand the logged-in user up to App
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="center">
      <form className="card auth" onSubmit={submit}>
        <h1>Outfit Picker</h1>
        <p className="muted">{mode === 'login' ? 'Welcome back.' : 'Create your account.'}</p>

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

        <p className="muted small">
          {mode === 'login' ? "No account?" : 'Already have one?'}{' '}
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
  )
}
