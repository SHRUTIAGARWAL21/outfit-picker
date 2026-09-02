// The single place the frontend talks to the backend.
//
// Every call goes to /api/... which Vite forwards to the FastAPI server (see
// vite.config.js). `credentials: 'include'` makes the browser send the session
// cookie, so the backend knows who is logged in.

const BASE = '/api'

async function request(path, options = {}) {
  const res = await fetch(BASE + path, {
    credentials: 'include',
    headers: { 'Content-Type': 'application/json', ...(options.headers || {}) },
    ...options,
  })
  if (!res.ok) {
    // Try to read the backend's error message ({"detail": "..."}).
    let detail = res.statusText
    try {
      detail = (await res.json()).detail || detail
    } catch {
      // no JSON body — keep the status text
    }
    const err = new Error(detail)
    err.status = res.status
    throw err
  }
  if (res.status === 204) return null
  return res.json()
}

export const api = {
  // --- auth ---
  signup: (email, password) =>
    request('/auth/signup', { method: 'POST', body: JSON.stringify({ email, password }) }),
  login: (email, password) =>
    request('/auth/login', { method: 'POST', body: JSON.stringify({ email, password }) }),
  logout: () => request('/auth/logout', { method: 'POST' }),
  me: () => request('/users/me'),

  // --- wardrobe ---
  listGarments: () => request('/garments'),
  uploadSignature: () => request('/garments/upload-signature', { method: 'POST' }),
  createGarment: (public_id) =>
    request('/garments', { method: 'POST', body: JSON.stringify({ public_id }) }),
  retryGarment: (id) => request(`/garments/${id}/retry`, { method: 'POST' }),

  // --- avatar ---
  getAvatar: () => request('/avatar'), // 404 if the user has no avatar yet
  avatarUploadSignature: () => request('/avatar/upload-signature', { method: 'POST' }),
  setAvatar: (public_id) =>
    request('/avatar', { method: 'POST', body: JSON.stringify({ public_id }) }),
  updateAvatarProfile: (profile) =>
    request('/avatar', { method: 'PATCH', body: JSON.stringify({ profile }) }),

  // --- recommendations ---
  createRequest: (prompt_text) =>
    request('/requests', { method: 'POST', body: JSON.stringify({ prompt_text }) }),
  getRequest: (id) => request(`/requests/${id}`),
  renderRequest: (id) => request(`/requests/${id}/render`, { method: 'POST' }),

  // --- likes / interest ---
  likeOutfit: (id) => request(`/outfits/${id}/like`, { method: 'POST' }),
  dislikeOutfit: (id) => request(`/outfits/${id}/dislike`, { method: 'POST' }),
  clearFeedback: (id) => request(`/outfits/${id}/feedback`, { method: 'DELETE' }),
  listInterest: () => request('/interest'),

  // --- quota ---
  getQuota: () => request('/quota'),
}

// The browser uploads the file straight to Cloudinary using the signed slip the
// backend handed us. The file never passes through our server (PRD 6.1).
export async function uploadToCloudinary(sig, file) {
  const form = new FormData()
  form.append('file', file)
  form.append('api_key', sig.api_key)
  form.append('timestamp', sig.timestamp)
  form.append('folder', sig.folder)
  form.append('signature', sig.signature)

  const res = await fetch(sig.upload_url, { method: 'POST', body: form })
  if (!res.ok) throw new Error('Cloudinary upload failed')
  const data = await res.json()
  return data.public_id
}
