import React from 'react'

export default function ConflictScoreBar({
  baseAcuity = 0,
  waitContribution = 0,
  resourceCriticality = 1.0,
  effectiveScore = 0,
  txId = '',
  className = '',
}) {
  const base = Number(baseAcuity) || 0
  const wait = Number(waitContribution) || 0
  const crit = Number(resourceCriticality) || 1.0
  const score = Number(effectiveScore) || ((base + wait) * crit)

  const subTotal = base + wait
  const basePct = subTotal > 0 ? (base / subTotal) * 100 : 100
  const waitPct = subTotal > 0 ? (wait / subTotal) * 100 : 0

  return (
    <div
      className={`conflict-score-bar ${className}`}
      style={{
        display: 'flex',
        flexDirection: 'column',
        gap: '6px',
        padding: '12px 14px',
        borderRadius: 'var(--radius-input)',
        backgroundColor: 'var(--surface-recessed)',
        border: '1px solid var(--line)',
      }}
    >
      {/* Header Row */}
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          fontFamily: 'var(--font-mono)',
          fontSize: 'var(--text-caption)',
        }}
      >
        <span style={{ fontWeight: 600, color: 'var(--ink)' }}>{txId}</span>
        <span style={{ fontWeight: 600, color: 'var(--pulse-blue)' }}>
          Effective Score: {score.toFixed(1)}
        </span>
      </div>

      {/* Stacked Horizontal Progress Bar */}
      <div
        style={{
          width: '100%',
          height: '8px',
          borderRadius: '4px',
          overflow: 'hidden',
          display: 'flex',
          backgroundColor: 'var(--line)',
        }}
      >
        <div
          style={{
            width: `${basePct}%`,
            height: '100%',
            backgroundColor: 'var(--pulse-blue)',
            transition: 'width 0.3s ease',
          }}
          title={`Base Acuity: ${base.toFixed(1)}`}
        />
        <div
          style={{
            width: `${waitPct}%`,
            height: '100%',
            backgroundColor: 'var(--signal-green)',
            transition: 'width 0.3s ease',
          }}
          title={`Wait Contribution: +${wait.toFixed(1)}`}
        />
      </div>

      {/* Legend Row */}
      <div
        style={{
          display: 'flex',
          flexWrap: 'wrap',
          alignItems: 'center',
          gap: '12px',
          fontFamily: 'var(--font-mono)',
          fontSize: '0.75rem',
          marginTop: '2px',
        }}
      >
        <span style={{ display: 'inline-flex', alignItems: 'center', gap: '4px', color: 'var(--pulse-blue)' }}>
          <span style={{ width: '8px', height: '8px', borderRadius: '2px', backgroundColor: 'var(--pulse-blue)' }} />
          Base Acuity {base.toFixed(1)}
        </span>

        <span style={{ display: 'inline-flex', alignItems: 'center', gap: '4px', color: 'var(--signal-green)' }}>
          <span style={{ width: '8px', height: '8px', borderRadius: '2px', backgroundColor: 'var(--signal-green)' }} />
          Wait Contribution +{wait.toFixed(1)}
        </span>

        <span style={{ display: 'inline-flex', alignItems: 'center', gap: '4px', color: 'var(--ink-muted)' }}>
          × Resource Criticality {crit.toFixed(1)}
        </span>
      </div>

      {/* Explicit Clinical Formula Calculation */}
      <div
        style={{
          fontFamily: 'var(--font-mono)',
          fontSize: '0.75rem',
          color: 'var(--ink-muted)',
          borderTop: '1px dashed var(--line)',
          paddingTop: '6px',
          marginTop: '2px',
        }}
      >
        ({base.toFixed(1)} + {wait.toFixed(1)}) × {crit.toFixed(1)} = {score.toFixed(1)}
      </div>
    </div>
  )
}
