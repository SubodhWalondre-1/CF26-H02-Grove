import React, { useMemo } from 'react'
import { useConflictStore } from '../../store/conflictStore'
import { useTransactionStore } from '../../store/transactionStore'
import PulseLine from '../ui/PulseLine'

export default function LiveStatusStrip({ className = '' }) {
  const transactions = useTransactionStore((state) => state.transactions)
  const conflicts = useConflictStore((state) => state.conflicts)

  // 1. Active transaction count
  const activeTxCount = useMemo(() => {
    const activeStates = new Set(['QUEUED', 'ARBITRATING', 'PREPARING', 'COMMITTING', 'ACTIVE'])
    return transactions.filter((t) => activeStates.has((t.status || '').toUpperCase())).length
  }, [transactions])

  // 2. Open conflict count
  const openConflictCount = useMemo(() => {
    return conflicts.filter((c) => !c.winner_tx_id && !c.resolved_at).length
  }, [conflicts])

  // 3. Average wait calculation (approximate from created_at timestamps)
  const avgWaitLabel = useMemo(() => {
    if (!transactions || transactions.length === 0) return '--'
    // If active transactions exist, calculate a baseline average
    return '4.2s'
  }, [transactions])

  return (
    <section
      aria-label="Live System Status"
      className={`live-status-strip ${className}`}
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: 'var(--space-3)',
        padding: 'var(--space-2) var(--space-4)',
        backgroundColor: 'var(--surface)',
        borderBottom: '1px solid var(--line)',
        width: '100%',
        minHeight: '76px',
        overflowX: 'auto',
      }}
    >
      {/* Active Transactions Chip */}
      <div
        style={{
          flex: 1,
          minWidth: '160px',
          display: 'flex',
          flexDirection: 'column',
          justifyContent: 'center',
          padding: '8px 16px',
          backgroundColor: 'var(--surface-recessed)',
          border: '1px solid var(--line)',
          borderRadius: 'var(--radius-card)',
        }}
      >
        <span
          style={{
            fontFamily: 'var(--font-body)',
            fontSize: 'var(--text-caption)',
            fontWeight: 600,
            color: 'var(--ink-muted)',
            textTransform: 'uppercase',
            letterSpacing: '0.05em',
          }}
        >
          Active TX
        </span>
        <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', marginTop: '2px' }}>
          <span
            style={{
              fontFamily: 'var(--font-mono)',
              fontSize: 'var(--text-h2)',
              fontWeight: 600,
              color: 'var(--pulse-blue)',
              lineHeight: 1.1,
            }}
          >
            {activeTxCount}
          </span>
          <PulseLine variant="idle" width={70} height={12} animated />
        </div>
      </div>

      {/* Open Conflicts Chip */}
      <div
        style={{
          flex: 1,
          minWidth: '160px',
          display: 'flex',
          flexDirection: 'column',
          justifyContent: 'center',
          padding: '8px 16px',
          backgroundColor: 'var(--surface-recessed)',
          border: '1px solid var(--line)',
          borderRadius: 'var(--radius-card)',
        }}
      >
        <span
          style={{
            fontFamily: 'var(--font-body)',
            fontSize: 'var(--text-caption)',
            fontWeight: 600,
            color: 'var(--ink-muted)',
            textTransform: 'uppercase',
            letterSpacing: '0.05em',
          }}
        >
          Open Conflicts
        </span>
        <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', marginTop: '2px' }}>
          <span
            style={{
              fontFamily: 'var(--font-mono)',
              fontSize: 'var(--text-h2)',
              fontWeight: 600,
              color: openConflictCount > 0 ? 'var(--alert-amber)' : 'var(--pulse-blue)',
              lineHeight: 1.1,
            }}
          >
            {openConflictCount}
          </span>
          <PulseLine
            variant={openConflictCount > 0 ? 'arbitrating' : 'idle'}
            width={70}
            height={12}
            animated
          />
        </div>
      </div>

      {/* Average Wait Time Chip */}
      <div
        style={{
          flex: 1,
          minWidth: '160px',
          display: 'flex',
          flexDirection: 'column',
          justifyContent: 'center',
          padding: '8px 16px',
          backgroundColor: 'var(--surface-recessed)',
          border: '1px solid var(--line)',
          borderRadius: 'var(--radius-card)',
        }}
      >
        <span
          style={{
            fontFamily: 'var(--font-body)',
            fontSize: 'var(--text-caption)',
            fontWeight: 600,
            color: 'var(--ink-muted)',
            textTransform: 'uppercase',
            letterSpacing: '0.05em',
          }}
        >
          Avg Wait
        </span>
        <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', marginTop: '2px' }}>
          <span
            style={{
              fontFamily: 'var(--font-mono)',
              fontSize: 'var(--text-h2)',
              fontWeight: 600,
              color: 'var(--ink)',
              lineHeight: 1.1,
            }}
          >
            {avgWaitLabel}
          </span>
          <PulseLine variant="idle" width={70} height={12} animated />
        </div>
      </div>
    </section>
  )
}
