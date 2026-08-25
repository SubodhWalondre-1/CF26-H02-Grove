// frontend/src/components/transfers/TransfersInProgressWidget.jsx
import React, { useEffect } from 'react'
import TransferStatusBadge from './TransferStatusBadge'
import { useTransferStore } from '../../store/transferStore'

export default function TransfersInProgressWidget({ onOpenTransferModal }) {
  const activeTransfers = useTransferStore((s) => s.activeTransfers)
  const fetchActiveTransfers = useTransferStore((s) => s.fetchActiveTransfers)
  const confirmTransport = useTransferStore((s) => s.confirmTransport)
  const commitTransfer = useTransferStore((s) => s.commitTransfer)
  const cancelTransfer = useTransferStore((s) => s.cancelTransfer)

  useEffect(() => {
    fetchActiveTransfers()
    const interval = setInterval(fetchActiveTransfers, 5000)
    return () => clearInterval(interval)
  }, [fetchActiveTransfers])

  if (activeTransfers.length === 0) {
    return (
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          padding: '12px 18px',
          borderRadius: 'var(--radius-card)',
          backgroundColor: 'var(--surface)',
          border: '1px solid var(--line)',
          marginBottom: 'var(--space-2)',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <span style={{ fontSize: '1.1rem' }}>🔀</span>
          <span style={{ fontFamily: 'var(--font-body)', fontSize: '0.8rem', color: 'var(--ink-muted)' }}>
            No active patient transfers in-flight.
          </span>
        </div>
        {onOpenTransferModal && (
          <button
            type="button"
            onClick={onOpenTransferModal}
            style={{
              fontFamily: 'var(--font-body)',
              fontSize: '0.75rem',
              fontWeight: 600,
              padding: '5px 14px',
              borderRadius: 'var(--radius-pill)',
              border: '1px solid var(--pulse-blue)',
              backgroundColor: 'var(--pulse-blue-soft)',
              color: 'var(--pulse-blue)',
              cursor: 'pointer',
            }}
          >
            + Initiate Transfer
          </button>
        )}
      </div>
    )
  }

  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        gap: '10px',
        padding: '16px 20px',
        borderRadius: 'var(--radius-card)',
        backgroundColor: '#F8FAFC',
        border: '1.5px solid #CBD5E1',
        boxShadow: '0 1px 4px rgba(0,0,0,0.04)',
        marginBottom: 'var(--space-2)',
      }}
    >
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <span style={{ fontSize: '1.2rem' }}>🔀</span>
          <span
            style={{
              fontFamily: 'var(--font-display)',
              fontSize: 'var(--text-h3)',
              fontWeight: 600,
              color: 'var(--ink)',
            }}
          >
            Patient Transfers in Progress ({activeTransfers.length})
          </span>
        </div>

        {onOpenTransferModal && (
          <button
            type="button"
            onClick={onOpenTransferModal}
            style={{
              fontFamily: 'var(--font-body)',
              fontSize: '0.72rem',
              fontWeight: 600,
              padding: '4px 12px',
              borderRadius: 'var(--radius-pill)',
              border: '1px solid var(--pulse-blue)',
              backgroundColor: 'var(--pulse-blue-soft)',
              color: 'var(--pulse-blue)',
              cursor: 'pointer',
            }}
          >
            + New Transfer
          </button>
        )}
      </div>

      {/* Transfer Cards List */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
        {activeTransfers.map((t) => {
          const now = new Date()
          const exp = new Date(t.hold_ttl_expires_at)
          const remainingSec = Math.max(0, Math.round((exp - now) / 1000))
          const totalSec = 300
          const pct = Math.min(100, Math.max(0, (remainingSec / totalSec) * 100))

          const isTransit = t.status === 'IN_TRANSIT'

          return (
            <div
              key={t.transfer_id}
              style={{
                display: 'flex',
                flexDirection: 'column',
                gap: '8px',
                padding: '12px 16px',
                borderRadius: 'var(--radius-input)',
                backgroundColor: 'var(--surface)',
                border: '1px solid var(--line)',
              }}
            >
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '6px' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '10px', flexWrap: 'wrap' }}>
                  <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.8rem', fontWeight: 700, color: 'var(--ink)' }}>
                    👤 {t.patient_id}
                  </span>
                  <span style={{ fontFamily: 'var(--font-body)', fontSize: '0.78rem', color: 'var(--ink)' }}>
                    <strong>{t.source_bed_number}</strong> ➔ <strong>{t.destination_bed_number}</strong>
                  </span>
                  {t.transport_resource_id && (
                    <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.68rem', padding: '1px 6px', borderRadius: '4px', backgroundColor: '#FEF3E2', color: '#D97706' }}>
                      🚑 Transport Escort
                    </span>
                  )}
                  {t.reason && (
                    <span style={{ fontFamily: 'var(--font-body)', fontSize: '0.7rem', color: 'var(--ink-muted)' }}>
                      ({t.reason.replace(/_/g, ' ')})
                    </span>
                  )}
                </div>

                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <TransferStatusBadge status={t.status} />

                  {/* Actions */}
                  {!isTransit && (
                    <button
                      type="button"
                      onClick={async () => {
                        try {
                          await confirmTransport(t.tx_id)
                        } catch (_) {}
                      }}
                      style={{
                        fontFamily: 'var(--font-body)',
                        fontSize: '0.7rem',
                        fontWeight: 600,
                        padding: '4px 10px',
                        borderRadius: 'var(--radius-pill)',
                        border: '1px solid var(--pulse-blue)',
                        backgroundColor: 'var(--pulse-blue)',
                        color: '#FFF',
                        cursor: 'pointer',
                      }}
                    >
                      🚀 Depart (In-Transit)
                    </button>
                  )}

                  {isTransit && (
                    <button
                      type="button"
                      onClick={async () => {
                        try {
                          await commitTransfer(t.tx_id)
                        } catch (_) {}
                      }}
                      style={{
                        fontFamily: 'var(--font-body)',
                        fontSize: '0.7rem',
                        fontWeight: 600,
                        padding: '4px 10px',
                        borderRadius: 'var(--radius-pill)',
                        border: '1px solid var(--signal-green)',
                        backgroundColor: 'var(--signal-green)',
                        color: '#FFF',
                        cursor: 'pointer',
                      }}
                    >
                      ✓ Confirm Arrival (Commit)
                    </button>
                  )}

                  <button
                    type="button"
                    onClick={async () => {
                      try {
                        await cancelTransfer(t.tx_id, 'USER_CANCEL')
                      } catch (_) {}
                    }}
                    style={{
                      fontFamily: 'var(--font-body)',
                      fontSize: '0.7rem',
                      fontWeight: 500,
                      padding: '4px 8px',
                      borderRadius: 'var(--radius-pill)',
                      border: '1px solid var(--line)',
                      backgroundColor: 'transparent',
                      color: 'var(--critical-red)',
                      cursor: 'pointer',
                    }}
                    title="Cancel transfer and return patient to source bed"
                  >
                    Abort
                  </button>
                </div>
              </div>

              {/* TTL Bar */}
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <div
                  style={{
                    flex: 1,
                    height: '4px',
                    borderRadius: '2px',
                    backgroundColor: 'rgba(0,0,0,0.06)',
                    overflow: 'hidden',
                  }}
                >
                  <div
                    style={{
                      width: `${pct}%`,
                      height: '100%',
                      borderRadius: '2px',
                      backgroundColor: remainingSec <= 30 ? 'var(--critical-red)' : 'var(--pulse-blue)',
                      transition: 'width 0.5s ease',
                    }}
                  />
                </div>
                <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.68rem', color: 'var(--ink-muted)', whiteSpace: 'nowrap' }}>
                  ⏳ TTL: {remainingSec}s
                </span>
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
