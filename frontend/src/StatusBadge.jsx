// A small coloured pill showing a PENDING/PROCESSING/READY/FAILED status.
// Shared by the wardrobe and the avatar so they look and behave the same.
const LABELS = {
  PENDING: 'Waiting…',
  PROCESSING: 'Analysing…',
  READY: 'Ready',
  FAILED: 'Failed',
  DEAD: 'Gave up',
}

export default function StatusBadge({ status }) {
  return <span className={`badge ${status.toLowerCase()}`}>{LABELS[status] || status}</span>
}
