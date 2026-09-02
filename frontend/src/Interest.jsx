import { useEffect, useState } from 'react'
import { api } from './api'
import OutfitCard from './OutfitCard.jsx'

// The interest section: the outfits you liked. A plain read of /interest — the
// backend never regenerates an image here, it just returns the stored ones.
export default function Interest() {
  const [outfits, setOutfits] = useState(undefined) // undefined = loading

  useEffect(() => {
    api
      .listInterest()
      .then(setOutfits)
      .catch(() => setOutfits([]))
  }, [])

  if (outfits === undefined) return <div className="muted">Loading…</div>

  return (
    <div>
      <div className="section-head">
        <h2>Saved outfits</h2>
      </div>

      {outfits.length === 0 ? (
        <div className="empty muted">
          No saved outfits yet. Like an outfit on the <strong>Outfits</strong> tab and it appears
          here.
        </div>
      ) : (
        <div className="outfits">
          {outfits.map((o) => (
            <OutfitCard
              key={o.id}
              outfit={o}
              initialSignal="like"
              // If it stops being a like (un-liked or disliked), drop it here.
              onChanged={(id, signal) => {
                if (signal !== 'like') setOutfits((prev) => prev.filter((x) => x.id !== id))
              }}
            />
          ))}
        </div>
      )}
    </div>
  )
}
