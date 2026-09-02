import { useEffect, useRef, useState } from 'react'
import { api, uploadToCloudinary } from './api'
import StatusBadge from './StatusBadge.jsx'

// The avatar screen: upload a full-body base photo, watch the profile get
// extracted, and correct it. There is one avatar per user.
export default function Avatar() {
  // undefined = still loading, null = no avatar yet, object = the avatar row.
  const [avatar, setAvatar] = useState(undefined)
  const [uploading, setUploading] = useState(false)
  const [refreshKey, setRefreshKey] = useState(0)
  const fileRef = useRef(null)

  // Load the avatar; keep polling only while it is still being analysed.
  useEffect(() => {
    let active = true
    let timer

    async function tick() {
      let data = null
      try {
        data = await api.getAvatar()
      } catch (e) {
        if (e.status !== 404) {
          // a real error; leave data null and stop
        }
        data = null // 404 simply means "no avatar yet"
      }
      if (!active) return
      setAvatar(data)
      if (data && (data.status === 'PENDING' || data.status === 'PROCESSING')) {
        timer = setTimeout(tick, 4000)
      }
    }

    tick()
    return () => {
      active = false
      clearTimeout(timer)
    }
  }, [refreshKey])

  async function onFile(e) {
    const file = e.target.files[0]
    if (!file) return
    setUploading(true)
    try {
      const sig = await api.avatarUploadSignature()
      const publicId = await uploadToCloudinary(sig, file)
      await api.setAvatar(publicId)
    } catch (err) {
      alert('Upload failed: ' + err.message)
    }
    setUploading(false)
    if (fileRef.current) fileRef.current.value = ''
    setRefreshKey((k) => k + 1)
  }

  if (avatar === undefined) return <div className="muted">Loading…</div>

  return (
    <div>
      <div className="section-head">
        <h2>Your avatar</h2>
        <button onClick={() => fileRef.current?.click()} disabled={uploading}>
          {uploading ? 'Uploading…' : avatar ? 'Replace photo' : '＋ Upload full-body photo'}
        </button>
        <input ref={fileRef} type="file" accept="image/*" hidden onChange={onFile} />
      </div>

      {!avatar ? (
        <div className="avatar-create">
          <div className="empty">
            Upload one clear, full-body photo with a plain background — or, if you’d rather not,
            build an avatar by answering a few questions below. 🌸
          </div>
          <GenerateForm onStarted={() => setRefreshKey((k) => k + 1)} />
        </div>
      ) : (
        <div className="avatar-view">
          <div
            className="thumb big"
            style={avatar.base_image_url ? { backgroundImage: `url(${avatar.base_image_url})` } : undefined}
          >
            {!avatar.base_image_url && <span className="muted small">Creating…</span>}
          </div>
          <div className="avatar-side">
            <StatusBadge status={avatar.status} />
            {avatar.status === 'FAILED' && (
              <div className="error small">{avatar.failure_reason}</div>
            )}
            {(avatar.status === 'PENDING' || avatar.status === 'PROCESSING') && (
              <div className="muted small">
                {avatar.base_image_url ? 'Reading your photo…' : 'Creating your avatar…'}
              </div>
            )}
            {avatar.status === 'READY' && avatar.profile && (
              <ProfileForm profile={avatar.profile} onSaved={() => setRefreshKey((k) => k + 1)} />
            )}
          </div>
        </div>
      )}
    </div>
  )
}

// The no-photo path: pick a few options and the app generates an avatar.
function GenerateForm({ onStarted }) {
  const OPTIONS = {
    body_type: ['slim', 'average', 'athletic', 'curvy', 'plus-size'],
    height: ['short', 'average', 'tall'],
    gender_presentation: ['feminine', 'masculine', 'androgynous'],
    skin_tone: ['fair', 'light', 'medium', 'tan', 'deep', 'dark'],
    hair_length: ['short', 'medium', 'long'],
    hair_texture: ['straight', 'wavy', 'curly', 'coily'],
    hair_color: ['black', 'dark brown', 'brown', 'blonde', 'red', 'grey'],
    eye_color: ['brown', 'black', 'hazel', 'green', 'blue', 'grey'],
  }
  const [sel, setSel] = useState({
    body_type: 'average',
    height: 'average',
    gender_presentation: 'feminine',
    skin_tone: 'medium',
    hair_length: 'medium',
    hair_texture: 'straight',
    hair_color: 'dark brown',
    eye_color: 'brown',
  })
  const [busy, setBusy] = useState(false)

  async function submit(e) {
    e.preventDefault()
    setBusy(true)
    try {
      await api.generateAvatar(sel)
      onStarted() // start polling; the worker generates the image
    } catch (err) {
      alert(err.message)
      setBusy(false)
    }
  }

  return (
    <form className="card generate" onSubmit={submit}>
      <h3>Build an animated avatar from a few questions</h3>
      <div className="generate-grid">
        {Object.entries(OPTIONS).map(([field, opts]) => (
          <label key={field} className="field">
            <span className="muted small">{field.replace(/_/g, ' ')}</span>
            <select value={sel[field]} onChange={(e) => setSel({ ...sel, [field]: e.target.value })}>
              {opts.map((o) => (
                <option key={o} value={o}>
                  {o}
                </option>
              ))}
            </select>
          </label>
        ))}
      </div>
      <button type="submit" disabled={busy}>
        {busy ? 'Generating…' : '✨ Generate my avatar'}
      </button>
      <p className="muted small">
        This draws a cute animated character from your answers (uses your image key). It can take up
        to a minute.
      </p>
    </form>
  )
}

// The extracted profile, shown as editable fields (PRD 4.2: view and correct).
function ProfileForm({ profile, onSaved }) {
  const FIELDS = ['body_shape', 'build', 'skin_undertone', 'hair_color', 'eye_color']
  const [values, setValues] = useState(() =>
    Object.fromEntries(FIELDS.map((f) => [f, profile[f] || ''])),
  )
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false) // show a confirmation after saving

  async function save() {
    setSaving(true)
    setSaved(false)
    try {
      await api.updateAvatarProfile(values)
      setSaved(true)
      setTimeout(() => setSaved(false), 3000) // fade the message after 3s
      onSaved()
    } catch (err) {
      alert(err.message)
    }
    setSaving(false)
  }

  return (
    <div className="profile">
      <p className="muted small">What we read from your photo — correct anything that is off:</p>
      {FIELDS.map((f) => (
        <label key={f} className="field">
          <span className="muted small">{f.replace(/_/g, ' ')}</span>
          <input
            value={values[f]}
            onChange={(e) => {
              setValues({ ...values, [f]: e.target.value })
              setSaved(false) // editing again clears the confirmation
            }}
          />
        </label>
      ))}
      <div className="save-row">
        <button onClick={save} disabled={saving}>
          {saving ? 'Saving…' : 'Save corrections'}
        </button>
        {saved && <span className="saved-note">✓ Saved</span>}
      </div>
    </div>
  )
}
