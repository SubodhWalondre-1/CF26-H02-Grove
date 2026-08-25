import React, { useEffect, useState } from 'react'

export default function TTLRing({
  totalSeconds = 30,
  remainingSeconds = 30,
  className = '',
}) {
  const [announcement, setAnnouncement] = useState('')

  const total = Math.max(1, totalSeconds || 30)
  const remaining = Math.max(0, remainingSeconds != null ? remainingSeconds : total)
  const isWarning = remaining <= 10

  const radius = 36
  const circumference = 2 * Math.PI * radius // ~226.195
  const clampedRatio = Math.min(1, Math.max(0, remaining / total))
  const strokeDashoffset = circumference * (1 - clampedRatio)

  // Accessibility screen-reader announcements at 10s and 5s thresholds
  useEffect(() => {
    const rounded = Math.round(remaining)
    if (rounded === 10) {
      setAnnouncement('Hold TTL warning: 10 seconds remaining')
    } else if (rounded === 5) {
      setAnnouncement('Hold TTL critical: 5 seconds remaining')
    }
  }, [remaining])

  const strokeColor = isWarning ? 'var(--alert-amber)' : 'var(--pulse-blue)'

  return (
    <div
      className={`ttl-ring-container ${className}`}
      style={{
        position: 'relative',
        display: 'inline-flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
      }}
    >
      <div
        aria-live="polite"
        className="sr-only"
        style={{
          position: 'absolute',
          width: '1px',
          height: '1px',
          padding: '0',
          margin: '-1px',
          overflow: 'hidden',
          clip: 'rect(0, 0, 0, 0)',
          whiteSpace: 'nowrap',
          border: '0',
        }}
      >
        {announcement}
      </div>

      <style>{`
        .ttl-ring-progress {
          transition: stroke-dashoffset 0.9s linear, stroke 0.4s ease;
        }
        @media (prefers-reduced-motion: reduce) {
          .ttl-ring-progress {
            transition: none !important;
          }
        }
      `}</style>

      <svg
        width="80"
        height="80"
        viewBox="0 0 80 80"
        style={{
          display: 'block',
          filter: isWarning ? 'drop-shadow(0 0 8px var(--alert-amber))' : 'none',
          transition: 'filter 0.3s ease',
        }}
      >
        {/* Background Track Circle */}
        <circle
          cx="40"
          cy="40"
          r={radius}
          fill="none"
          stroke="var(--line)"
          strokeWidth="6"
        />

        {/* Depleting Progress Arc */}
        <circle
          cx="40"
          cy="40"
          r={radius}
          fill="none"
          stroke={strokeColor}
          strokeWidth="6"
          strokeLinecap="round"
          strokeDasharray={circumference}
          strokeDashoffset={strokeDashoffset}
          transform="rotate(-90 40 40)"
          className="ttl-ring-progress"
        />

        {/* Center Countdown Label */}
        <text
          x="40"
          y="44"
          textAnchor="middle"
          fill="var(--ink)"
          style={{
            fontFamily: 'var(--font-mono)',
            fontSize: '1.15rem',
            fontWeight: 600,
            fontVariantNumeric: 'tabular-nums',
          }}
        >
          {Math.ceil(remaining)}s
        </text>
      </svg>
    </div>
  )
}
