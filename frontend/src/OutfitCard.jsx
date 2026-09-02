import { useState } from 'react'
import { api } from './api'

// One outfit tile, shared by the Outfits screen and the Saved gallery.
// Shows the rendered image (or a placeholder while it generates), the reason,
// the garment thumbnails, and like / dislike buttons.
//
// Props:
//   outfit         the outfit data
//   initialSignal  'like' | 'dislike' | null — the user's existing feedback
//   onChanged      optional callback(outfitId, newSignal) after a change
export default function OutfitCard({ outfit, initialSignal = null, onChanged }) {
  const [signal, setSignal] = useState(initialSignal)
  const [busy, setBusy] = useState(false)

  async function apply(next) {
    // Clicking the active button again clears it (toggle off).
    const target = signal === next ? null : next
    setBusy(true)
    try {
      if (target === 'like') await api.likeOutfit(outfit.id)
      else if (target === 'dislike') await api.dislikeOutfit(outfit.id)
      else await api.clearFeedback(outfit.id)
      setSignal(target)
      onChanged?.(outfit.id, target)
    } catch (e) {
      alert(e.message)
    }
    setBusy(false)
  }

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
        <div className="outfit-top">
          <span className="rank">#{outfit.rank}</span>
          <div className="feedback">
            <button
              className={`icon ${signal === 'like' ? 'on like' : ''}`}
              onClick={() => apply('like')}
              disabled={busy}
              title="Like"
            >
              ♥
            </button>
            <button
              className={`icon ${signal === 'dislike' ? 'on dislike' : ''}`}
              onClick={() => apply('dislike')}
              disabled={busy}
              title="Not for me"
            >
              ✕
            </button>
          </div>
        </div>
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
