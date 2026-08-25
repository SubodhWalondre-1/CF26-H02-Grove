// frontend/src/components/beds/DonationBoardAlert.jsx
import React, { useEffect, useState } from 'react'
import api from '../../lib/api'

export default function DonationBoardAlert() {
  const [shortages, setShortages] = useState([])

  const fetchShortages = async () => {
    try {
      const res = await api.get('/beds/shortage')
      const items = Array.isArray(res.data) ? res.data : []
      setShortages(items.filter((item) => item.is_critical || item.ready_count === 0))
    } catch (_) {}
  }

  useEffect(() => {
    fetchShortages()
    const interval = setInterval(fetchShortages, 10000)
    return () => clearInterval(interval)
  }, [])

  if (shortages.length === 0) return null

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-1)', marginBottom: 'var(--space-2)' }}>
      {shortages.map((item) => (
        <div
          key={item.bed_type}
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            padding: '12px 18px',
            borderRadius: 'var(--radius-card)',
            backgroundColor: '#FEF2F2',
            border: '1.5px solid var(--critical-red)',
            boxShadow: '0 2px 8px rgba(178, 59, 59, 0.12)',
            flexWrap: 'wrap',
            gap: 'var(--space-2)',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
            <span style={{ fontSize: '1.5rem', lineHeight: 1 }}>🚨</span>
            <div>
              <div
                style={{
                  fontFamily: 'var(--font-display)',
                  fontSize: 'var(--text-h3)',
                  fontWeight: 600,
                  color: 'var(--critical-red)',
                }}
              >
                Donation Board Alert: {item.bed_type} Beds Critical
              </div>
              <div
                style={{
                  fontFamily: 'var(--font-body)',
                  fontSize: 'var(--text-caption)',
                  color: '#7F1D1D',
                  marginTop: '2px',
                }}
              >
                Only <strong style={{ textDecoration: 'underline' }}>{item.ready_count} READY</strong> beds available (Safety Threshold: {item.threshold_ready}). Urgent triage and turn-around required.
              </div>
            </div>
          </div>

          <span
            style={{
              fontFamily: 'var(--font-mono)',
              fontSize: '0.75rem',
              fontWeight: 700,
              padding: '4px 12px',
              borderRadius: 'var(--radius-pill)',
              backgroundColor: 'var(--critical-red)',
              color: '#FFFFFF',
              letterSpacing: '0.04em',
              textTransform: 'uppercase',
            }}
          >
            CRITICAL SHORTAGE
          </span>
        </div>
      ))}
    </div>
  )
}
