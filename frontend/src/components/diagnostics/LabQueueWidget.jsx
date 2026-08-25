// frontend/src/components/diagnostics/LabQueueWidget.jsx
import React, { useEffect } from 'react'
import { useLabStore } from '../../store/labStore'

const SAMPLE_STATUS_COLORS = {
  SAMPLE_COLLECTED: { text: '#D97706', bg: '#FFFBEB', border: '#FDE68A', label: 'Queued' },
  IN_TRANSIT:       { text: '#0284C7', bg: '#E0F2FE', border: '#7DD3FC', label: 'In Transit' },
  PROCESSING:       { text: '#854D0E', bg: '#FEF08A', border: '#FACC15', label: 'Processing' },
  RESULT_READY:     { text: '#15803D', bg: '#DCFCE7', border: '#86EFAC', label: 'Result Ready' },
}

export default function LabQueueWidget() {
  const stations = useLabStore((s) => s.stations)
  const samples = useLabStore((s) => s.samples)
  const fetchLabQueue = useLabStore((s) => s.fetchLabQueue)

  useEffect(() => {
    fetchLabQueue()
    const interval = setInterval(fetchLabQueue, 8000)
    return () => clearInterval(interval)
  }, [fetchLabQueue])

  const primaryStation = stations[0] || {
    lab_station_code: 'LAB-STATION-1',
    current_load: 0,
    max_concurrent: 6,
    status: 'READY',
  }

  const loadPct = primaryStation.max_concurrent > 0
    ? Math.round((primaryStation.current_load / primaryStation.max_concurrent) * 100)
    : 0

  let loadColor = 'var(--signal-green)'
  if (loadPct >= 85) loadColor = 'var(--critical-red)'
  else if (loadPct >= 50) loadColor = 'var(--alert-amber)'

  const statSamples = samples.filter((s) => s.priority === 'STAT')
  const routineSamples = samples.filter((s) => s.priority === 'ROUTINE')

  return (
    <div
      style={{
        padding: '18px 22px',
        borderRadius: 'var(--radius-card)',
        backgroundColor: 'var(--surface)',
        border: '1px solid var(--line)',
        display: 'flex',
        flexDirection: 'column',
        gap: '14px',
      }}
    >
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div>
          <span
            style={{
              fontFamily: 'var(--font-display)',
              fontSize: 'var(--text-h3)',
              fontWeight: 600,
              color: 'var(--ink)',
            }}
          >
            🧪 Clinical Lab Queue
          </span>
          <span
            style={{
              fontFamily: 'var(--font-body)',
              fontSize: '0.72rem',
              color: 'var(--ink-muted)',
              marginLeft: '8px',
            }}
          >
            {primaryStation.lab_station_code}
          </span>
        </div>

        <span
          style={{
            fontFamily: 'var(--font-mono)',
            fontSize: '0.7rem',
            fontWeight: 700,
            padding: '2px 8px',
            borderRadius: 'var(--radius-pill)',
            backgroundColor: primaryStation.status === 'READY' ? 'var(--signal-green-soft)' : '#FEE2E2',
            color: primaryStation.status === 'READY' ? 'var(--signal-green)' : 'var(--critical-red)',
            border: `1px solid ${primaryStation.status === 'READY' ? '#A7F3D0' : '#FECACA'}`,
          }}
        >
          {primaryStation.status}
        </span>
      </div>

      {/* Capacity Load Bar */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
          <span style={{ fontFamily: 'var(--font-body)', fontSize: '0.75rem', color: 'var(--ink-muted)' }}>
            Throughput Capacity
          </span>
          <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.9rem', fontWeight: 700, color: loadColor }}>
            {primaryStation.current_load} / {primaryStation.max_concurrent} active ({loadPct}%)
          </span>
        </div>
        <div
          style={{
            width: '100%',
            height: '8px',
            borderRadius: '4px',
            backgroundColor: 'rgba(0,0,0,0.06)',
            overflow: 'hidden',
          }}
        >
          <div
            style={{
              width: `${Math.min(100, loadPct)}%`,
              height: '100%',
              borderRadius: '4px',
              backgroundColor: loadColor,
              transition: 'width 0.3s ease',
            }}
          />
        </div>
      </div>

      {/* Queue Breakdown Pills */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '8px' }}>
        <div
          style={{
            padding: '10px 12px',
            borderRadius: 'var(--radius-input)',
            backgroundColor: statSamples.length > 0 ? '#FEF2F2' : 'var(--surface-recessed)',
            border: `1px solid ${statSamples.length > 0 ? '#FECACA' : 'var(--line)'}`,
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
          }}
        >
          <span style={{ fontFamily: 'var(--font-body)', fontSize: '0.72rem', fontWeight: 600, color: 'var(--critical-red)' }}>
            🚨 STAT Urgent
          </span>
          <span style={{ fontFamily: 'var(--font-mono)', fontSize: '1rem', fontWeight: 700, color: 'var(--critical-red)' }}>
            {statSamples.length}
          </span>
        </div>

        <div
          style={{
            padding: '10px 12px',
            borderRadius: 'var(--radius-input)',
            backgroundColor: 'var(--surface-recessed)',
            border: '1px solid var(--line)',
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
          }}
        >
          <span style={{ fontFamily: 'var(--font-body)', fontSize: '0.72rem', fontWeight: 500, color: 'var(--ink-muted)' }}>
            📋 Routine
          </span>
          <span style={{ fontFamily: 'var(--font-mono)', fontSize: '1rem', fontWeight: 700, color: 'var(--pulse-blue)' }}>
            {routineSamples.length}
          </span>
        </div>
      </div>

      {/* Recent / In-flight Samples */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
        <span style={{ fontFamily: 'var(--font-body)', fontSize: '0.72rem', fontWeight: 600, color: 'var(--ink-muted)', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
          Active Samples ({samples.length})
        </span>

        {samples.length === 0 ? (
          <span style={{ fontFamily: 'var(--font-body)', fontSize: '0.75rem', color: 'var(--ink-muted)', fontStyle: 'italic' }}>
            No samples currently queued or processing.
          </span>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '6px', maxHeight: '180px', overflowY: 'auto' }}>
            {samples.slice(0, 5).map((sm) => {
              const cfg = SAMPLE_STATUS_COLORS[sm.status] || {
                text: 'var(--ink)',
                bg: 'var(--surface-recessed)',
                border: 'var(--line)',
                label: sm.status,
              }
              const isStat = sm.priority === 'STAT'

              return (
                <div
                  key={sm.id}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    padding: '6px 10px',
                    borderRadius: '6px',
                    backgroundColor: cfg.bg,
                    border: `1px solid ${cfg.border}`,
                  }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                    {isStat && (
                      <span style={{ fontSize: '0.7rem', color: 'var(--critical-red)', fontWeight: 700 }}>
                        [STAT]
                      </span>
                    )}
                    <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.75rem', fontWeight: 600, color: 'var(--ink)' }}>
                      {sm.test_type}
                    </span>
                    <span style={{ fontFamily: 'var(--font-body)', fontSize: '0.7rem', color: 'var(--ink-muted)' }}>
                      ({sm.patient_id})
                    </span>
                  </div>

                  <span
                    style={{
                      fontFamily: 'var(--font-mono)',
                      fontSize: '0.65rem',
                      fontWeight: 600,
                      color: cfg.text,
                    }}
                  >
                    {cfg.label}
                  </span>
                </div>
              )
            })}
          </div>
        )}
      </div>
    </div>
  )
}
