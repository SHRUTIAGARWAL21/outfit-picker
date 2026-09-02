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
          {uploading ? 'Uploading…' : avatar ? 'Replace photo' : '+ Upload full-body photo'}
        </button>
        <input ref={fileRef} type="file" accept="image/*" hidden onChange={onFile} />
      </div>

      {!avatar ? (
        <div className="empty muted">
          Upload one clear, full-body photo with a plain background. It becomes the base image we
          dress in your outfits.
        </div>
      ) : (
        <div className="avatar-view">
          <div className="thumb big" style={{ backgroundImage: `url(${avatar.base_image_url})` }} />
          <div className="avatar-side">
            <StatusBadge status={avatar.status} />
            {avatar.status === 'FAILED' && (
              <div className="error small">{avatar.failure_reason}</div>
            )}
            {(avatar.status === 'PENDING' || avatar.status === 'PROCESSING') && (
              <div className="muted small">Reading your photo…</div>
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
