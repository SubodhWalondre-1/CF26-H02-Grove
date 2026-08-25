import React, { useEffect, useState } from 'react'
import Card from '../components/ui/Card'
import ConflictScoreBar from '../components/ui/ConflictScoreBar'
import ConflictScoreChart from '../components/charts/ConflictScoreChart'
import Table from '../components/ui/Table'
import { getConflictScore } from '../lib/api'
import { useConflictStore } from '../store/conflictStore'
import { useEscalationStore } from '../store/escalationStore'

const FILTER_TABS = [
  { value: '', label: 'All' },
  { value: 'open', label: 'Open' },
  { value: 'resolved', label: 'Resolved' },
]

export default function Conflicts() {
  const conflicts = useConflictStore((state) => state.conflicts)
  const currentConflict = useConflictStore((state) => state.currentConflict)
  const currentScoreBreakdown = useConflictStore((state) => state.currentScoreBreakdown)
  const filters = useConflictStore((state) => state.filters)
  const fetchConflicts = useConflictStore((state) => state.fetchConflicts)
  const fetchConflict = useConflictStore((state) => state.fetchConflict)
  const setFilters = useConflictStore((state) => state.setFilters)

  const preemptionAlert = useEscalationStore((state) => state.preemptionAlert)
  const clearPreemptionAlert = useEscalationStore((state) => state.clearPreemptionAlert)

  const [selectedConflictId, setSelectedConflictId] = useState(null)
  const [breakdownMap, setBreakdownMap] = useState({})
  const [isLoadingBreakdowns, setIsLoadingBreakdowns] = useState(false)

  useEffect(() => {
    fetchConflicts()
  }, [fetchConflicts])

  const handleTabChange = (val) => {
    setFilters({ status: val || null })
  }

  const handleSelectConflict = async (row) => {
    const id = row.conflict_id
    setSelectedConflictId(id)
    setIsLoadingBreakdowns(true)

    try {
      const conflictData = await fetchConflict(id)
      const txs = conflictData.transactions || []

      // Fetch score breakdowns for each competing transaction
      const results = {}
      await Promise.all(
        txs.map(async (t) => {
          try {
            const res = await getConflictScore(id, t.tx_id)
            results[t.tx_id] = res.data
          } catch (err) {
            console.warn(`Could not load score breakdown for ${t.tx_id}:`, err)
          }
        })
      )
      setBreakdownMap(results)
    } catch (err) {
      console.error('Error fetching conflict details:', err)
    } finally {
      setIsLoadingBreakdowns(false)
    }
  }

  const currentTab = filters.status || ''

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-4)' }}>
      {/* Page Title */}
      <h1
        style={{
          fontFamily: 'var(--font-display)',
          fontSize: 'var(--text-h1)',
          fontWeight: 480,
          color: 'var(--ink)',
          margin: 0,
        }}
      >
        Resource Conflicts & Escalations
      </h1>

      {/* Preemption Toast / Alert Banner */}
      {preemptionAlert && (
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            padding: '14px 20px',
            borderRadius: 'var(--radius-card)',
            backgroundColor: '#FEF2F2',
            border: '1.5px solid #FECACA',
            color: 'var(--critical-red)',
            fontFamily: 'var(--font-body)',
            boxShadow: '0 4px 6px -1px rgba(0, 0, 0, 0.05)',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <span style={{ fontSize: '1.4rem' }}>⚡</span>
            <div>
              <strong style={{ fontSize: '0.88rem' }}>Preemption Notice:</strong>{' '}
              <span style={{ fontSize: '0.82rem' }}>{preemptionAlert.message}</span>
              {preemptionAlert.suggested_alternative && (
                <div style={{ marginTop: '4px', fontSize: '0.78rem', color: '#B91C1C' }}>
                  💡 <strong>Suggested Alternative:</strong> {preemptionAlert.suggested_alternative.label} (
                  {preemptionAlert.suggested_alternative.type}) — READY
                </div>
              )}
            </div>
          </div>
          <button
            type="button"
            onClick={clearPreemptionAlert}
            style={{
              background: 'none',
              border: 'none',
              fontSize: '1.1rem',
              color: 'var(--critical-red)',
              cursor: 'pointer',
            }}
          >
            ✕
          </button>
        </div>
      )}

      {/* Filter Tabs */}
      <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
        {FILTER_TABS.map((tab) => {
          const isActive = currentTab === tab.value
          return (
            <button
              key={tab.value}
              type="button"
              onClick={() => handleTabChange(tab.value)}
              style={{
                padding: '8px 16px',
                borderRadius: 'var(--radius-input)',
                border: '1px solid var(--line)',
                backgroundColor: isActive ? 'var(--pulse-blue-soft)' : 'var(--surface)',
                color: isActive ? 'var(--pulse-blue)' : 'var(--ink)',
                fontFamily: 'var(--font-body)',
                fontWeight: isActive ? 600 : 500,
                fontSize: 'var(--text-body)',
                cursor: 'pointer',
                transition: 'all 0.15s ease',
              }}
            >
              {tab.label}
            </button>
          )
        })}
      </div>

      {/* Conflicts Table */}
      <Table
        columns={[
          { key: 'conflict_id', label: 'Conflict ID', mono: true },
          { key: 'resource_contested', label: 'Resource', mono: true },
          {
            key: 'transactions',
            label: 'Competing TX',
            mono: true,
            render: (row) =>
              row.transactions && row.transactions.length > 0
                ? row.transactions.map((t) => t.tx_id).join(' vs ')
                : '—',
          },
          {
            key: 'winner_tx_id',
            label: 'Winner TX',
            mono: true,
            render: (row) =>
              row.winner_tx_id ? (
                <span style={{ color: 'var(--signal-green)', fontWeight: 600 }}>
                  {row.winner_tx_id}
                </span>
              ) : (
                <span style={{ color: 'var(--alert-amber)' }}>Pending Arbitration</span>
              ),
          },
          {
            key: 'resolution',
            label: 'Resolution',
            render: (row) => {
              const isEsc = row.resolution_level === 'escalation' || row.resolution === 'escalation'
              return (
                <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                  {isEsc && (
                    <span
                      style={{
                        padding: '2px 8px',
                        borderRadius: 'var(--radius-pill)',
                        backgroundColor: '#FEF3C7',
                        border: '1px solid #FCD34D',
                        color: '#B45309',
                        fontFamily: 'var(--font-mono)',
                        fontSize: '0.7rem',
                        fontWeight: 700,
                      }}
                    >
                      ⚡ ESCALATED
                    </span>
                  )}
                  <span>
                    {row.resolution === 'transaction_level'
                      ? 'Transaction Level (Formula)'
                      : row.resolution || (isEsc ? 'Forced Preemption' : '—')}
                  </span>
                </div>
              )
            },
          },
        ]}
        rows={conflicts}
        onRowClick={handleSelectConflict}
        emptyMessage="No open conflicts. All resource requests are resolving cleanly."
      />

      {/* Detail Panel */}
      {selectedConflictId && currentConflict && (
        <Card title={`Arbitration Details: ${currentConflict.conflict_id}`}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-3)' }}>
            {/* Arbiter Decision Callout */}
            <div
              style={{
                backgroundColor: 'var(--surface)',
                border: '1px solid var(--line)',
                borderRadius: 'var(--radius-input)',
                padding: '12px 16px',
                fontFamily: 'var(--font-body)',
                fontSize: 'var(--text-body)',
              }}
            >
              {currentConflict.winner_tx_id ? (
                <p style={{ margin: 0 }}>
                  Winner:{' '}
                  <span
                    style={{
                      fontFamily: 'var(--font-mono)',
                      color: 'var(--signal-green)',
                      fontWeight: 600,
                    }}
                  >
                    {currentConflict.winner_tx_id}
                  </span>{' '}
                  was prioritized based on higher clinical effective score. Competing transaction
                  holds were rolled back.
                </p>
              ) : (
                <p style={{ margin: 0, color: 'var(--alert-amber)' }}>
                  Arbitration in progress: evaluating clinical acuity scores and wait times...
                </p>
              )}
            </div>

            {/* Score Breakdowns for Competing Transactions */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-2)' }}>
              <div
                style={{
                  fontFamily: 'var(--font-body)',
                  fontSize: 'var(--text-caption)',
                  fontWeight: 600,
                  color: 'var(--ink-muted)',
                  textTransform: 'uppercase',
                }}
              >
                Competing Acuity Score Comparison
              </div>

              {isLoadingBreakdowns ? (
                <div style={{ color: 'var(--ink-muted)' }}>Calculating score breakdowns...</div>
              ) : (
                <>
                  <div
                    style={{
                      display: 'grid',
                      gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))',
                      gap: 'var(--space-2)',
                    }}
                  >
                    {(currentConflict.transactions || []).map((t) => {
                      const breakdown = breakdownMap[t.tx_id]
                      if (!breakdown) return null

                      return (
                        <ConflictScoreBar
                          key={t.tx_id}
                          txId={t.tx_id}
                          baseAcuity={breakdown.base_acuity}
                          waitContribution={breakdown.wait_contribution}
                          resourceCriticality={breakdown.resource_criticality}
                          effectiveScore={breakdown.effective_score}
                        />
                      )
                    })}
                  </div>

                  {/* Score comparison chart — Phase 6 addition */}
                  {currentConflict?.transactions?.length > 1 && (
                    <div style={{ marginTop: 'var(--space-3)' }}>
                      <p
                        style={{
                          fontSize: 'var(--text-caption)',
                          color: 'var(--ink-muted)',
                          fontFamily: 'var(--font-body)',
                          marginBottom: 'var(--space-1)',
                        }}
                      >
                        Effective Score comparison — winner highlighted in green.
                      </p>
                      <ConflictScoreChart
                        transactions={currentConflict.transactions.map((tx) => {
                          const sb = breakdownMap[tx.tx_id] || currentScoreBreakdown
                          return {
                            tx_id: tx.tx_id,
                            base_acuity: sb?.base_acuity || (tx.effective_score ? tx.effective_score * 0.6 : 6.0),
                            wait_contribution: sb?.wait_contribution || (tx.effective_score ? tx.effective_score * 0.4 : 2.0),
                            effective_score: tx.effective_score || sb?.effective_score || 0,
                          }
                        })}
                        winnerId={currentConflict.winner_tx_id}
                      />
                    </div>
                  )}
                </>
              )}
            </div>
          </div>
        </Card>
      )}
    </div>
  )
}
