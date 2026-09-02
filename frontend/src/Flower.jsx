// A small decorative 5-petal flower drawn as SVG (crisp at any size).
export default function Flower({ size = 46, petal = '#f7a8cb', center = '#c9a7ef' }) {
  return (
    <svg width={size} height={size} viewBox="0 0 100 100" aria-hidden="true">
      {[0, 72, 144, 216, 288].map((a) => (
        <ellipse
          key={a}
          cx="50"
          cy="27"
          rx="12"
          ry="21"
          fill={petal}
          opacity="0.9"
          transform={`rotate(${a} 50 50)`}
        />
      ))}
      <circle cx="50" cy="50" r="11" fill={center} />
    </svg>
  )
}
