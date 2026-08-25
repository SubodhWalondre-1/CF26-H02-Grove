// frontend/src/components/pharmacy/PharmacyShortageAlert.jsx
import React from 'react'
import { usePharmacyStore } from '../../store/pharmacyStore'

export default function PharmacyShortageAlert() {
  const shortages = usePharmacyStore((s) => s.shortages)

  const criticalItems = shortages.filter(
    (s) => s.status === 'DEPLETED' || s.status === 'EXPIRED' || s.available_quantity <= 0
  )

  if (criticalItems.length === 0) return null

  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'flex-start',
        gap: '12px',
        padding: '14px 18px',
        borderRadius: 'var(--radius-card)',
        border: '1.5px solid #FCA5A5',
        backgroundColor: '#FFF5F5',
        marginBottom: 'var(--space-2)',
      }}
    >
      <span style={{ fontSize: '1.3rem', lineHeight: 1, flexShrink: 0 }}>🚨</span>
      <div style={{ display: 'flex', flexDirection: 'column', gap: '4px', flex: 1 }}>
        <span
          style={{
            fontFamily: 'var(--font-body)',
            fontSize: 'var(--text-caption)',
            fontWeight: 700,
            color: 'var(--critical-red)',
            textTransform: 'uppercase',
            letterSpacing: '0.05em',
          }}
        >
          Critical Pharmacy Shortage — {criticalItems.length} batch{criticalItems.length > 1 ? 'es' : ''} affected
        </span>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px', marginTop: '4px' }}>
          {criticalItems.map((item) => (
            <span
              key={item.resource_id}
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: '4px',
                padding: '3px 10px',
                borderRadius: 'var(--radius-pill)',
                backgroundColor: 'rgba(178,59,59,0.08)',
                border: '1px solid #FECACA',
                fontFamily: 'var(--font-mono)',
                fontSize: '0.7rem',
                fontWeight: 600,
                color: 'var(--critical-red)',
              }}
            >
              {item.resource_type === 'blood_unit' ? '🩸' : item.resource_type === 'oxygen_unit' ? '🫁' : '💊'}
              {item.sub_type || item.batch_id}: {item.available_quantity} left
            </span>
          ))}
        </div>
        <span
          style={{
            fontFamily: 'var(--font-body)',
            fontSize: '0.72rem',
            color: '#991B1B',
            marginTop: '2px',
          }}
        >
          Immediate restock or donation board activation recommended.
        </span>
      </div>
    </div>
  )
}
