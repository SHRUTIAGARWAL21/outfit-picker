import { useEffect, useRef, useState } from 'react'
import { api, uploadToCloudinary } from './api'
import StatusBadge from './StatusBadge.jsx'

// The category "rails" of the closet, in the order they appear.
const SECTIONS = [
  { key: 'top', label: 'Tops' },
  { key: 'outerwear', label: 'Outerwear' },
  { key: 'dress', label: 'Dresses' },
  { key: 'bottom', label: 'Bottoms' },
  { key: 'footwear', label: 'Shoes' },
  { key: 'accessory', label: 'Accessories' },
  { key: 'other', label: 'Other' },
]

// Upload garment photos and see them hanging in your closet, grouped by type.
export default function Wardrobe() {
  const [garments, setGarments] = useState([])
  const [uploading, setUploading] = useState(false)
  const [refreshKey, setRefreshKey] = useState(0)
  const fileRef = useRef(null)

  // Poll only while something is still being analysed, then stop.
  useEffect(() => {
    let active = true
    let timer
    async function tick() {
      let data = []
      try {
        data = await api.listGarments()
      } catch {
        // transient — retry next tick
      }
      if (!active) return
      setGarments(data)
      const stillWorking = data.some((g) => g.status === 'PENDING' || g.status === 'PROCESSING')
      if (stillWorking) timer = setTimeout(tick, 4000)
    }
    tick()
    return () => {
      active = false
      clearTimeout(timer)
    }
  }, [refreshKey])

  async function onFiles(e) {
    const files = [...e.target.files]
    if (files.length === 0) return
    setUploading(true)
    for (const file of files) {
      try {
        const sig = await api.uploadSignature()
        const publicId = await uploadToCloudinary(sig, file)
        await api.createGarment(publicId)
      } catch (err) {
        alert('Upload failed: ' + err.message)
      }
    }
    setUploading(false)
    if (fileRef.current) fileRef.current.value = ''
    setRefreshKey((k) => k + 1)
  }

  // Split garments: ones still being analysed go on a "Just added" rail;
  // ready ones are grouped by their category.
  const pending = garments.filter((g) => g.status !== 'READY')
  const byCat = {}
  for (const g of garments.filter((g) => g.status === 'READY')) {
    const cat = SECTIONS.some((s) => s.key === g.attributes?.category)
      ? g.attributes.category
      : 'other'
    ;(byCat[cat] ||= []).push(g)
  }

  return (
    <div>
      <div className="section-head">
        <h2>Your closet</h2>
        <button onClick={() => fileRef.current?.click()} disabled={uploading}>
          {uploading ? 'Uploading…' : '＋ Add clothes'}
        </button>
        <input ref={fileRef} type="file" accept="image/*" multiple hidden onChange={onFiles} />
      </div>

      {garments.length === 0 ? (
        <div className="empty">
          Your closet is empty. Click <strong>“Add clothes”</strong> and upload a few flat photos —
          they’ll be sorted onto the rails for you. 🌸
        </div>
      ) : (
        <div className="closet">
          {pending.length > 0 && (
            <ClosetRail label="Just added">
              {pending.map((g) => (
                <Hanging key={g.id} g={g} />
              ))}
            </ClosetRail>
          )}

          {SECTIONS.filter((s) => byCat[s.key]?.length).map((s) => (
            <ClosetRail key={s.key} label={s.label}>
              {byCat[s.key].map((g) => (
                <Hanging key={g.id} g={g} />
              ))}
            </ClosetRail>
          ))}
        </div>
      )}
    </div>
  )
}

// One labelled rail (a clothing rod) with items hanging from it.
function ClosetRail({ label, children }) {
  return (
    <div className="closet-section">
      <p className="rail-label">{label}</p>
      <div className="rail">
        <div className="rail-items">{children}</div>
      </div>
    </div>
  )
}

// One garment hanging on a hanger.
function Hanging({ g }) {
  const a = g.attributes || {}
  const ready = g.status === 'READY'
  return (
    <div className="hanging" title={a.description || ''}>
      <span className="hook" />
      <div className="hang-thumb" style={{ backgroundImage: `url(${g.image_url})` }} />
      {ready ? (
        <div className="hang-label">
          <strong>{a.subcategory || a.category}</strong>
          <span className="muted">{a.primary_color}</span>
        </div>
      ) : g.status === 'FAILED' ? (
        <>
          <StatusBadge status={g.status} />
          <div className="error small">{g.failure_reason}</div>
        </>
      ) : (
        <StatusBadge status={g.status} />
      )}
    </div>
  )
}
