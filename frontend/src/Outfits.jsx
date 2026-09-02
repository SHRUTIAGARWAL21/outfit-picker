import { useEffect, useRef, useState } from 'react'
import { api } from './api'

// The heart of the app: type what you need, get ranked outfits, then watch the
// rendered images stream in one by one.
export default function Outfits() {
  const [prompt, setPrompt] = useState('')
  const [phase, setPhase] = useState('idle') // idle | thinking | ready | failed
  const [request, setRequest] = useState(null) // the request + its outfits
  const [error, setError] = useState('')
  const [quota, setQuota] = useState(null)
  const esRef = useRef(null) // the live image stream (EventSource)

  // Show how many renders are left today.
  useEffect(() => {
    api.getQuota().then(setQuota).catch(() => {})
  }, [request])

  // Close the live stream if the screen unmounts.
  useEffect(() => () => esRef.current?.close(), [])

  async function ask(e) {
    e.preventDefault()
    setError('')
    setRequest(null)
    esRef.current?.close()
    setPhase('thinking')
    try {
      const created = await api.createRequest(prompt) // POST /requests -> id, instantly
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
    const es = new EventSource(`/api/requests/${id}/stream`)
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

      <form className="ask" onSubmit={ask}>
        <input
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
          placeholder="e.g. something smart but comfortable for a warm day at the office"
          required
        />
        <button type="submit" disabled={phase === 'thinking'}>
          {phase === 'thinking' ? 'Thinking…' : 'Ask'}
        </button>
      </form>

      {error && <div className="error">{error}</div>}
      {phase === 'thinking' && <div className="muted">Choosing outfits from your wardrobe…</div>}
      {phase === 'failed' && (
        <div className="error">Could not build outfits. Please try again.</div>
      )}

      {request && (
        <div className="outfits">
          {request.outfits.map((o) => (
            <OutfitCard key={o.id} outfit={o} />
          ))}
        </div>
      )}
    </div>
  )
}

// One outfit: the rendered image (or a placeholder while it generates), the
// reason, and the garment thumbnails it is made of.
function OutfitCard({ outfit }) {
  return (
    <div className="card outfit">
      <div className="render">
        {outfit.render_url ? (
          <img src={outfit.render_url} alt={`Outfit ${outfit.rank}`} />
        ) : (
          <div className="render-placeholder muted small">
            {outfit.render_status === 'FAILED' ? 'Image unavailable' : 'Generating image…'}
          </div>
        )}
      </div>
      <div className="outfit-body">
        <div className="rank">#{outfit.rank}</div>
        <p className="reason">{outfit.reason}</p>
        <div className="pieces">
          {outfit.garments.map((g) => (
            <div
              key={g.id}
              className="piece"
              style={{ backgroundImage: `url(${g.image_url})` }}
              title={g.attributes?.description || ''}
            />
          ))}
        </div>
      </div>
    </div>
  )
}
