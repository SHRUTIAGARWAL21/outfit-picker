import { useEffect, useRef, useState } from 'react'
import { api, uploadToCloudinary } from './api'

// The main screen for now: upload garment photos and see their status.
export default function Wardrobe({ user, onLogout }) {
  const [garments, setGarments] = useState([])
  const [uploading, setUploading] = useState(false)
  const [refreshKey, setRefreshKey] = useState(0) // bump this to restart polling
  const fileRef = useRef(null)

  // Fetch the garments, and keep polling ONLY while something is still being
  // analysed. Once every garment is READY or FAILED, we stop asking — no more
  // pointless requests. A new upload bumps `refreshKey`, which restarts this.
  useEffect(() => {
    let active = true
    let timer

    async function tick() {
      let data = []
      try {
        data = await api.listGarments()
      } catch {
        // transient read error — try again on the next tick
      }
      if (!active) return
      setGarments(data)

      const stillWorking = data.some(
        (g) => g.status === 'PENDING' || g.status === 'PROCESSING',
      )
      if (stillWorking) timer = setTimeout(tick, 4000) // keep polling only if needed
    }

    tick()
    return () => {
      active = false
      clearTimeout(timer) // stop when the screen closes or refreshKey changes
    }
  }, [refreshKey])

  // Handle one or many chosen files: for each, get a signed slip, upload to
  // Cloudinary, then tell the backend to record it.
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
    if (fileRef.current) fileRef.current.value = '' // let the same file be re-picked
    setRefreshKey((k) => k + 1) // restart polling to watch the new PENDING photos
  }

  async function logout() {
    await api.logout()
    onLogout()
  }

  return (
    <div className="app">
      <header className="topbar">
        <strong>Outfit Picker</strong>
        <span className="muted small">{user.email}</span>
        <button className="link" onClick={logout}>
          Log out
        </button>
      </header>

      <main>
        <div className="section-head">
          <h2>Your wardrobe</h2>
          <button onClick={() => fileRef.current?.click()} disabled={uploading}>
            {uploading ? 'Uploading…' : '+ Add clothes'}
          </button>
          <input
            ref={fileRef}
            type="file"
            accept="image/*"
            multiple
            hidden
            onChange={onFiles}
          />
        </div>

        {garments.length === 0 ? (
          <div className="empty muted">
            No clothes yet. Click <strong>“Add clothes”</strong> and upload a few flat photos of
            garments.
          </div>
        ) : (
          <div className="grid">
            {garments.map((g) => (
              <GarmentCard key={g.id} g={g} />
            ))}
          </div>
        )}
      </main>
    </div>
  )
}

// One garment tile: the photo, a status badge, and (when ready) a summary.
function GarmentCard({ g }) {
  const a = g.attributes || {}
  return (
    <div className="card garment">
      <div className="thumb" style={{ backgroundImage: `url(${g.image_url})` }} />
      <div className="garment-body">
        <StatusBadge status={g.status} />
        {g.status === 'READY' && (
          <div className="attrs small">
            <strong>
              {a.primary_color} {a.subcategory || a.category}
            </strong>
            <span className="muted">{a.description}</span>
          </div>
        )}
        {g.status === 'FAILED' && <div className="error small">{g.failure_reason}</div>}
      </div>
    </div>
  )
}

function StatusBadge({ status }) {
  const label = {
    PENDING: 'Waiting…',
    PROCESSING: 'Analysing…',
    READY: 'Ready',
    FAILED: 'Failed',
  }[status] || status
  return <span className={`badge ${status.toLowerCase()}`}>{label}</span>
}
