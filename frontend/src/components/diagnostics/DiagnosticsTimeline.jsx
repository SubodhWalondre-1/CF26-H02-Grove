// frontend/src/components/diagnostics/DiagnosticsTimeline.jsx
import React, { useEffect, useState } from 'react'
import { useDiagnosticsStore } from '../../store/diagnosticsStore'

const STATUS_BLOCK_COLORS = {
  PENDING_CONFIRM: { bg: '#FEF3E2', border: '#FCD34D', text: '#D97706', label: 'Hold' },
  CONFIRMED:       { bg: '#E0F2FE', border: '#7DD3FC', text: '#0284C7', label: 'Booked' },
  IN_PROGRESS:     { bg: '#FEF08A', border: '#FACC15', text: '#854D0E', label: 'Scanning' },
  COMPLETED:       { bg: '#F3E8FF', border: '#D8B4FE', text: '#7E22CE', label: 'Done' },
}

export default function DiagnosticsTimeline({ equipment }) {
  const availability = useDiagnosticsStore((s) => s.availability[equipment?.id])
  const fetchAvailability = useDiagnosticsStore((s) => s.fetchAvailability)

  useEffect(() => {
    if (equipment?.id) {
      fetchAvailability(equipment.id)
    }
  }, [equipment?.id, fetchAvailability])

  if (!equipment) {
    return (
      <div
        style={{
          padding: 'var(--space-4)',
          textAlign: 'center',
          fontFamily: 'var(--font-body)',
          fontSize: 'var(--text-caption)',
          color: 'var(--ink-muted)',
          backgroundColor: 'var(--surface)',
          borderRadius: 'var(--radius-card)',
          border: '1px solid var(--line)',
        }}
      >
        Select an equipment card above to inspect its live schedule timeline.
      </div>
    )
  }

  const bookings = availability?.bookings || []

  // Generate 8-hour timeline intervals starting from current hour
  const now = new Date()
  const currentHour = now.getHours()
  const hours = Array.from({ length: 8 }, (_, i) => (currentHour + i) % 24)

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
      {/* Timeline Header */}
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
            🗓️ Schedule Timeline: {equipment.equipment_code}
          </span>
          <span
            style={{
              fontFamily: 'var(--font-body)',
              fontSize: '0.75rem',
              color: 'var(--ink-muted)',
              marginLeft: '8px',
            }}
          >
            ({equipment.avg_scan_minutes} min slots)
          </span>
        </div>

        {/* Legend */}
        <div style={{ display: 'flex', gap: '10px', alignItems: 'center' }}>
          {Object.entries(STATUS_BLOCK_COLORS).map(([key, cfg]) => (
            <span
              key={key}
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: '4px',
                fontFamily: 'var(--font-mono)',
                fontSize: '0.65rem',
                color: cfg.text,
              }}
            >
              <span
                style={{
                  width: '8px',
                  height: '8px',
                  borderRadius: '2px',
                  backgroundColor: cfg.bg,
                  border: `1px solid ${cfg.border}`,
                }}
              />
              {cfg.label}
            </span>
          ))}
          <span
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: '4px',
              fontFamily: 'var(--font-mono)',
              fontSize: '0.65rem',
              color: 'var(--signal-green)',
            }}
          >
            <span
              style={{
                width: '8px',
                height: '8px',
                borderRadius: '2px',
                backgroundColor: 'var(--signal-green-soft)',
                border: '1px dashed var(--signal-green)',
              }}
            />
            Free
          </span>
        </div>
      </div>

      {/* Hour ruler bar */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(8, 1fr)',
          gap: '4px',
          borderBottom: '1px solid var(--line)',
          paddingBottom: '6px',
        }}
      >
        {hours.map((h, idx) => (
          <div
            key={idx}
            style={{
              fontFamily: 'var(--font-mono)',
              fontSize: '0.72rem',
              fontWeight: idx === 0 ? 700 : 500,
              color: idx === 0 ? 'var(--pulse-blue)' : 'var(--ink-muted)',
              textAlign: 'center',
            }}
          >
            {h.toString().padStart(2, '0')}:00 {idx === 0 && '• Now'}
          </div>
        ))}
      </div>

      {/* Bookings List / Visual Blocks */}
      {bookings.length === 0 ? (
        <div
          style={{
            padding: '16px',
            textAlign: 'center',
            borderRadius: 'var(--radius-card)',
            backgroundColor: 'var(--signal-green-soft)',
            border: '1px dashed var(--signal-green)',
            fontFamily: 'var(--font-body)',
            fontSize: '0.8rem',
            color: 'var(--signal-green)',
            fontWeight: 600,
          }}
        >
          ✓ No active appointments today. Equipment is fully available for urgent or scheduled scans.
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
          {bookings.map((b) => {
            const start = new Date(b.scheduled_start)
            const end = new Date(b.scheduled_end)
            const theme = STATUS_BLOCK_COLORS[b.status] || {
              bg: 'var(--surface-recessed)',
              border: 'var(--line)',
              text: 'var(--ink)',
            }

            return (
              <div
                key={b.appointment_id}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  padding: '10px 14px',
                  borderRadius: 'var(--radius-input)',
                  backgroundColor: theme.bg,
                  border: `1.5px solid ${theme.border}`,
                  transition: 'all 0.15s ease',
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                  <span
                    style={{
                      fontFamily: 'var(--font-mono)',
                      fontSize: '0.8rem',
                      fontWeight: 700,
                      color: theme.text,
                    }}
                  >
                    {start.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })} –{' '}
                    {end.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                  </span>
                  <span
                    style={{
                      fontFamily: 'var(--font-body)',
                      fontSize: '0.75rem',
                      color: 'var(--ink-muted)',
                    }}
                  >
                    👤 {b.patient_id}
                  </span>
                  <span
                    style={{
                      fontFamily: 'var(--font-mono)',
                      fontSize: '0.7rem',
                      color: 'var(--ink-muted)',
                      backgroundColor: 'rgba(0,0,0,0.04)',
                      padding: '2px 6px',
                      borderRadius: '4px',
                    }}
                  >
                    {b.tx_id}
                  </span>
                </div>

                <span
                  style={{
                    fontFamily: 'var(--font-mono)',
                    fontSize: '0.68rem',
                    fontWeight: 700,
                    padding: '2px 8px',
                    borderRadius: 'var(--radius-pill)',
                    backgroundColor: 'rgba(255,255,255,0.7)',
                    color: theme.text,
                    border: `1px solid ${theme.border}`,
                  }}
                >
                  {b.status}
                </span>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
