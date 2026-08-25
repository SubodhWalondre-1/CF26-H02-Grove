import React from 'react'

export default function PulseLine({
  variant = 'idle',
  width = 80,
  height = 24,
  animated = true,
  className = '',
}) {
  const isFullWidth = width === '100%' || width === 'auto'
  const svgWidth = isFullWidth ? 400 : typeof width === 'number' ? width : 80
  const svgHeight = typeof height === 'number' ? height : 24
  const midY = svgHeight / 2

  const getStrokeColor = () => {
    switch (variant.toLowerCase()) {
      case 'idle':
        return 'rgba(11, 110, 143, 0.35)'
      case 'queued':
        return 'var(--pulse-blue)'
      case 'arbitrating':
        return 'var(--pulse-blue)'
      case 'preparing':
        return 'var(--pulse-blue)'
      case 'committed':
      case 'active':
      case 'completed':
      case 'closed':
        return 'var(--signal-green)'
      case 'aborted':
      case 'cancelled':
        return 'var(--critical-red)'
      default:
        return 'var(--pulse-blue)'
    }
  }

  const getPathData = () => {
    const w = svgWidth
    const h = svgHeight
    const m = midY

    switch (variant.toLowerCase()) {
      case 'idle':
        return `M 0 ${m} Q ${w * 0.1} ${m - 2}, ${w * 0.2} ${m} T ${w * 0.4} ${m} Q ${w * 0.45} ${m - 6}, ${w * 0.48} ${m + 6} T ${w * 0.52} ${m} Q ${w * 0.7} ${m + 2}, ${w * 0.8} ${m} T ${w} ${m}`

      case 'queued':
        return `M 0 ${m + 3} L ${w * 0.5} ${m + 3} Q ${w * 0.75} ${m + 3}, ${w} ${m - 4}`

      case 'arbitrating':
        return `M 0 ${m} L ${w * 0.25} ${m} L ${w * 0.35} ${m - h * 0.35} L ${w * 0.45} ${m + h * 0.35} L ${w * 0.55} ${m - h * 0.4} L ${w * 0.65} ${m + h * 0.2} L ${w * 0.75} ${m} L ${w} ${m}`

      case 'preparing':
        return `M 0 ${m + 3} L ${w * 0.2} ${m + 3} L ${w * 0.35} ${m - 5} L ${w * 0.8} ${m - 5} L ${w * 0.9} ${m} L ${w} ${m}`

      case 'committed':
      case 'active':
      case 'completed':
      case 'closed':
        return `M 0 ${m} L ${w * 0.4} ${m} Q ${w * 0.45} ${m - 4}, ${w * 0.5} ${m + 4} T ${w * 0.55} ${m} L ${w} ${m}`

      case 'aborted':
      case 'cancelled':
        return `M 0 ${m} L ${w * 0.4} ${m} L ${w * 0.55} ${m - 4} L ${w * 0.75} ${h - 2}`

      default:
        return `M 0 ${m} L ${w} ${m}`
    }
  }

  const strokeColor = getStrokeColor()
  const pathD = getPathData()
  const isIdle = variant.toLowerCase() === 'idle'
  const isArbitrating = variant.toLowerCase() === 'arbitrating'

  return (
    <div
      className={`pulse-line-wrapper ${className}`}
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        width: isFullWidth ? '100%' : `${svgWidth}px`,
        height: `${svgHeight}px`,
        overflow: 'hidden',
      }}
    >
      <style>{`
        @keyframes pulseLineScroll {
          0% { stroke-dashoffset: 0; }
          100% { stroke-dashoffset: -200; }
        }
        @keyframes pulseSpike {
          0%, 100% { stroke-width: 1.5px; opacity: 0.85; }
          50% { stroke-width: 2.5px; opacity: 1; filter: drop-shadow(0 0 2px var(--pulse-blue)); }
        }
        .pulse-line-idle-anim {
          stroke-dasharray: 8 4;
          animation: pulseLineScroll 6s linear infinite;
        }
        .pulse-line-arbitrating-anim {
          animation: pulseSpike 0.8s ease-in-out infinite;
        }
        @media (prefers-reduced-motion: reduce) {
          .pulse-line-idle-anim,
          .pulse-line-arbitrating-anim {
            animation: none !important;
          }
        }
      `}</style>
      <svg
        width={isFullWidth ? '100%' : svgWidth}
        height={svgHeight}
        viewBox={`0 0 ${svgWidth} ${svgHeight}`}
        preserveAspectRatio={isFullWidth ? 'none' : 'xMidYMid meet'}
        style={{ display: 'block', width: isFullWidth ? '100%' : `${svgWidth}px` }}
      >
        <path
          d={pathD}
          fill="none"
          stroke={strokeColor}
          strokeWidth={isArbitrating ? 2 : 1.5}
          strokeLinecap="round"
          strokeLinejoin="round"
          className={
            animated
              ? isIdle
                ? 'pulse-line-idle-anim'
                : isArbitrating
                ? 'pulse-line-arbitrating-anim'
                : ''
              : ''
          }
        />
      </svg>
    </div>
  )
}
