import { useEffect, useRef, useState } from 'react'
import { api, API_BASE } from './api'
import OutfitCard from './OutfitCard.jsx'

// The heart of the app: type what you need, get ranked outfits, then watch the
// rendered images stream in one by one.
const OCCASIONS = ['casual', 'office', 'party', 'wedding', 'gym', 'formal']

export default function Outfits() {
  const [prompt, setPrompt] = useState('')
  const [occasion, setOccasion] = useState(null)
  const [phase, setPhase] = useState('idle') // idle | thinking | ready | failed
  const [request, setRequest] = useState(null) // the request + its outfits
  const [error, setError] = useState('')
  const [quota, setQuota] = useState(null)
  const [hasAvatar, setHasAvatar] = useState(true) // assume yes until we know
  const esRef = useRef(null) // the live image stream (EventSource)

  // Show how many renders are left today.
  useEffect(() => {
    api.getQuota().then(setQuota).catch(() => {})
  }, [request])

  // Images only generate if the user has a READY avatar. Check once so we can
  // warn them, instead of showing "Generating…" forever for nothing.
  useEffect(() => {
    api
      .getAvatar()
      .then((a) => setHasAvatar(a?.status === 'READY'))
      .catch(() => setHasAvatar(false)) // 404 = no avatar
  }, [])

  // Close the live stream if the screen unmounts.
  useEffect(() => () => esRef.current?.close(), [])

  async function ask(e) {
    e.preventDefault()
    // Need either typed text or a chosen occasion.
    const text = prompt.trim() || (occasion ? `an outfit for a ${occasion} occasion` : '')
    if (!text) {
      setError('Type a request or pick an occasion.')
      return
    }
    setError('')
    setRequest(null)
    esRef.current?.close()
    setPhase('thinking')
    try {
      const created = await api.createRequest(text, occasion) // POST /requests -> id, instantly
      pollUntilReady(created.id)
    } catch (err) {
      setError(err.message) // e.g. "wardrobe too small"
      setPhase('idle')
    }
  }

  // Ask the backend repeatedly until the ranking is done (status READY).
  function pollUntilReady(id) {
    let tries = 0
    const tick = async () => {
      try {
        const r = await api.getRequest(id)
        if (r.status === 'READY') {
          setRequest(r)
          setPhase('ready')
          startImageStream(id) // now watch for the pictures
          return
        }
        if (r.status === 'FAILED') {
          setPhase('failed')
          return
        }
      } catch {
        // transient — try again
      }
      if (++tries < 40) setTimeout(tick, 1500)
      else setPhase('failed')
    }
    tick()
  }

  // Open the Server-Sent Events stream. The server PUSHES one message per outfit
  // as its image finishes, so pictures appear the instant they are ready.
  function startImageStream(id) {
    // withCredentials so the session cookie is sent when the API is a separate origin.
    const es = new EventSource(`${API_BASE}/requests/${id}/stream`, { withCredentials: true })
    esRef.current = es

    es.onmessage = (ev) => {
      const d = JSON.parse(ev.data)
      // Patch just the one outfit this message is about.
      setRequest((prev) =>
        prev
          ? {
              ...prev,
              outfits: prev.outfits.map((o) =>
                o.id === d.outfit_id
                  ? { ...o, render_status: d.render_status, render_url: d.render_url }
                  : o,
              ),
            }
          : prev,
      )
    }
    const close = () => es.close()
    es.addEventListener('done', close)
    es.addEventListener('timeout', close)
    es.onerror = close
  }

  return (
    <div>
      <div className="section-head">
        <h2>Ask for an outfit</h2>
        {quota && (
          <span className="muted small" style={{ marginLeft: 'auto' }}>
            {quota.remaining}/{quota.limit} image renders left today
          </span>
        )}
      </div>

      <div className="occasions">
        {OCCASIONS.map((o) => (
          <button
            key={o}
            type="button"
            className={`chip ${occasion === o ? 'on' : ''}`}
            onClick={() => setOccasion(occasion === o ? null : o)}
          >
            {o}
          </button>
        ))}
      </div>

      <form className="ask" onSubmit={ask}>
        <input
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
          placeholder={
            occasion
              ? `Add detail (optional) — e.g. warm weather, ${occasion}`
              : 'e.g. something smart but comfortable for a warm day at the office'
          }
        />
        <button type="submit" disabled={phase === 'thinking'}>
          {phase === 'thinking' ? 'Thinking…' : 'Ask'}
        </button>
      </form>

      {!hasAvatar && (
        <div className="notice">
          You have no avatar yet, so outfits show as text only. Add a full-body photo on the{' '}
          <strong>Avatar</strong> tab to get rendered images.
        </div>
      )}

      {error && <div className="error">{error}</div>}
      {phase === 'thinking' && <div className="muted">Choosing outfits from your wardrobe…</div>}
      {phase === 'failed' && (
        <div className="error">Could not build outfits. Please try again.</div>
      )}

      {request && (
        <div className="outfits">
          {request.outfits.map((o) => (
            <OutfitCard key={o.id} outfit={o} hasAvatar={hasAvatar} />
          ))}
        </div>
      )}
    </div>
  )
}
