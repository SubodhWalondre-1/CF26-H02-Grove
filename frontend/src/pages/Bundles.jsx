import React, { useCallback, useEffect, useState } from 'react'
import Card from '../components/ui/Card'
import EmptyState from '../components/ui/EmptyState'
import StateBadge from '../components/ui/StateBadge'
import TTLRing from '../components/ui/TTLRing'
import { getBundleStatus, listTransactions } from '../lib/api'
import { wsManager } from '../lib/websocket'

export default function Bundles() {
  const [bundles, setBundles] = useState([])
  const [bundleStatuses, setBundleStatuses] = useState({})
  const [isLoading, setIsLoading] = useState(true)

  const loadBundleStatus = useCallback(async (txId) => {
    try {
      const res = await getBundleStatus(txId)
      setBundleStatuses((prev) => ({
        ...prev,
        [txId]: res.data,
      }))
    } catch (err) {
      console.warn(`Could not fetch 2PC prepare status for bundle ${txId}:`, err)
    }
  }, [])

  const loadBundles = useCallback(async () => {
    setIsLoading(true)
    try {
      const res = await listTransactions({ request_type: 'care_bundle' })
      const items = res.data.items || []

      // Focus on active 2PC in-flight bundles
      const activeBundles = items.filter((t) =>
        ['PREPARING', 'COMMITTING', 'QUEUED', 'ARBITRATING'].includes((t.status || '').toUpperCase())
      )

      setBundles(activeBundles)

      // Fetch 2PC status for each bundle
      activeBundles.forEach((b) => {
        loadBundleStatus(b.tx_id)
      })
    } catch (err) {
      console.error('Error fetching care bundles:', err)
    } finally {
      setIsLoading(false)
    }
  }, [loadBundleStatus])

  useEffect(() => {
    loadBundles()

    const unsubPrepare = wsManager.subscribe('BUNDLE_PREPARE_UPDATE', (msg) => {
      if (msg.tx_id) {
        loadBundleStatus(msg.tx_id)
      }
      loadBundles()
    })

    const unsubTx = wsManager.subscribe('TRANSACTION_UPDATED', () => {
      loadBundles()
    })

    const unsubTtl = wsManager.subscribe('TTL_WARNING', (msg) => {
      if (msg.tx_id) {
        setBundles((prev) =>
          prev.map((b) =>
            b.tx_id === msg.tx_id
              ? { ...b, hold_remaining_seconds: msg.remaining_seconds }
              : b
          )
        )
      }
    })

    return () => {
      unsubPrepare()
      unsubTx()
      unsubTtl()
    }
  }, [loadBundles, loadBundleStatus])

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-4)' }}>
      {/* Header & Subtitle */}
      <div>
        <h1
          style={{
            fontFamily: 'var(--font-display)',
            fontSize: 'var(--text-h1)',
            fontWeight: 480,
            color: 'var(--ink)',
            margin: 0,
          }}
        >
          Care Bundles (Two-Phase Commit)
        </h1>
        <p
          style={{
            fontFamily: 'var(--font-body)',
            fontSize: 'var(--text-caption)',
            color: 'var(--ink-muted)',
            marginTop: '4px',
            marginBottom: 0,
          }}
        >
          Atomic multi-resource bundles require all resources to be held before committing. Any
          failure triggers a full rollback — no partial locks.
        </p>
      </div>

      {/* Bundle Grid */}
      {isLoading && bundles.length === 0 ? (
        <div style={{ color: 'var(--ink-muted)', padding: 'var(--space-3)' }}>
          Loading 2PC Care Bundles...
        </div>
      ) : bundles.length === 0 ? (
        <Card>
          <EmptyState message="No care bundles in preparation. Atomic bundle requests appear here during the 2PC prepare phase." />
        </Card>
      ) : (
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fill, minmax(340px, 1fr))',
            gap: 'var(--space-3)',
          }}
        >
          {bundles.map((tx) => {
            const status = (tx.status || '').toUpperCase()
            const bStatus = bundleStatuses[tx.tx_id]
            const isPreparing = status === 'PREPARING'

            return (
              <Card key={tx.tx_id} title={`Bundle TX: ${tx.tx_id}`}>
                <div
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    marginBottom: 'var(--space-3)',
                  }}
                >
                  <StateBadge status={status} />

                  {isPreparing && tx.hold_remaining_seconds != null && (
                    <TTLRing
                      totalSeconds={tx.hold_ttl_seconds || 30}
                      remainingSeconds={tx.hold_remaining_seconds}
                    />
                  )}
                </div>

                {/* 2PC Resource Manifest Grid */}
                <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
                  <div
                    style={{
                      fontFamily: 'var(--font-body)',
                      fontSize: 'var(--text-caption)',
                      fontWeight: 600,
                      color: 'var(--ink-muted)',
                      textTransform: 'uppercase',
                    }}
                  >
                    Tentative Resource Locks (2PC Phase 1)
                  </div>

                  {bStatus && bStatus.resources ? (
                    bStatus.resources.map((r) => (
                      <div
                        key={r.resource_id}
                        style={{
                          display: 'flex',
                          justifyContent: 'space-between',
                          alignItems: 'center',
                          padding: '8px 12px',
                          backgroundColor: r.held
                            ? 'var(--signal-green-soft)'
                            : 'var(--surface-recessed)',
                          borderRadius: 'var(--radius-input)',
                          border: '1px solid var(--line)',
                        }}
                      >
                        <span style={{ fontFamily: 'var(--font-mono)', fontWeight: 500 }}>
                          {r.resource_id}
                        </span>
                        <span
                          style={{
                            fontFamily: 'var(--font-mono)',
                            fontSize: 'var(--text-caption)',
                            fontWeight: 600,
                            color: r.held ? 'var(--signal-green)' : 'var(--alert-amber)',
                          }}
                        >
                          {r.held ? '✓ HELD' : '⏳ PENDING'}
                        </span>
                      </div>
                    ))
                  ) : (
                    <div style={{ color: 'var(--ink-muted)', fontSize: 'var(--text-caption)' }}>
                      Evaluating resource holds...
                    </div>
                  )}
                </div>

                {/* All Held Status Indicator */}
                {bStatus && bStatus.all_held && (
                  <div
                    style={{
                      marginTop: 'var(--space-2)',
                      padding: '8px 12px',
                      backgroundColor: 'var(--signal-green-soft)',
                      borderRadius: 'var(--radius-input)',
                      border: '1px solid var(--signal-green)',
                      color: 'var(--signal-green)',
                      fontFamily: 'var(--font-mono)',
                      fontSize: 'var(--text-caption)',
                      fontWeight: 600,
                      textAlign: 'center',
                    }}
                  >
                    ✓ All resources held — ready to commit
                  </div>
                )}
              </Card>
            )
          })}
        </div>
      )}
    </div>
  )
}
