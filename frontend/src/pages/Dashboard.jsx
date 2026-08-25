import React, { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import Card from '../components/ui/Card'
import StateBadge from '../components/ui/StateBadge'
import Table from '../components/ui/Table'
import TxActivityChart from '../components/charts/TxActivityChart'
import BedGrid from '../components/beds/BedGrid'
import BedActionModal from '../components/beds/BedActionModal'
import DonationBoardAlert from '../components/beds/DonationBoardAlert'
import PharmacyGrid from '../components/pharmacy/PharmacyGrid'
import DiagnosticsPanel from '../components/diagnostics/DiagnosticsPanel'
import TransferModal from '../components/transfers/TransferModal'
import TransfersInProgressWidget from '../components/transfers/TransfersInProgressWidget'
import ResourceGrid from './ResourceGrid'
import { useConflictStore } from '../store/conflictStore'
import { useTransactionStore } from '../store/transactionStore'
import { useBedStore } from '../store/stores'
import api from '../lib/api'

export default function Dashboard() {
  const navigate = useNavigate()
  const [activeTab, setActiveTab] = useState('bed_grid') // 'bed_grid' | 'overview' | 'pharmacy' | 'diagnostics'
  const [modalBed, setModalBed] = useState(null)
  const [showTransferModal, setShowTransferModal] = useState(false)
  const [duplicatesBlocked, setDuplicatesBlocked] = useState(0)
  const [overridesToday, setOverridesToday] = useState(0)

  const transactions = useTransactionStore((state) => state.transactions)
  const fetchTransactions = useTransactionStore((state) => state.fetchTransactions)

  const conflicts = useConflictStore((state) => state.conflicts)
  const fetchConflicts = useConflictStore((state) => state.fetchConflicts)

  const setBedGrid = useBedStore((state) => state.setBedGrid)

  const refreshBedGrid = async () => {
    try {
      const res = await api.get('/beds/grid')
      setBedGrid(res.data || [])
    } catch (_) {}
  }

  useEffect(() => {
    fetchTransactions({ page_size: 25 })
    fetchConflicts({ status: 'open' })
    api.get('/metrics/idempotency')
      .then((res) => setDuplicatesBlocked(res.data?.duplicates_blocked || 0))
      .catch(() => {})
    api.get('/metrics/overrides')
      .then((res) => setOverridesToday(res.data?.overrides_today || 0))
      .catch(() => {})
  }, [fetchTransactions, fetchConflicts])

  // Stat metrics computation
  const activeTxCount = transactions.filter((t) =>
    ['QUEUED', 'ARBITRATING', 'PREPARING', 'COMMITTING', 'ACTIVE'].includes(
      (t.status || '').toUpperCase()
    )
  ).length

  const openConflictCount = conflicts.filter(
    (c) => !c.winner_tx_id && !c.resolved_at
  ).length

  const committedCount = transactions.filter((t) =>
    ['COMMITTED', 'ACTIVE', 'COMPLETED', 'CLOSED'].includes((t.status || '').toUpperCase())
  ).length

  const abortedCount = transactions.filter((t) =>
    ['ABORTED', 'CANCELLED', 'ROLLINGBACK'].includes((t.status || '').toUpperCase())
  ).length

  // Date formatting helper
  const formatDate = (isoStr) => {
    if (!isoStr) return '—'
    try {
      const d = new Date(isoStr)
      return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })
    } catch {
      return isoStr
    }
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-4)' }}>
      {/* Critical Shortage Donation Alerts */}
      <DonationBoardAlert />

      {/* Header & Tabs */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          flexWrap: 'wrap',
          gap: 'var(--space-2)',
        }}
      >
        <h1
          style={{
            fontFamily: 'var(--font-display)',
            fontSize: 'var(--text-h1)',
            fontWeight: 480,
            color: 'var(--ink)',
            margin: 0,
          }}
        >
          Dashboard
        </h1>

        {/* Tab Switcher */}
        <div
          style={{
            display: 'inline-flex',
            backgroundColor: 'var(--surface-recessed)',
            border: '1px solid var(--line)',
            borderRadius: 'var(--radius-pill)',
            padding: '3px',
            gap: '4px',
          }}
        >
          <button
            type="button"
            onClick={() => setActiveTab('resource_grid')}
            style={{
              fontFamily: 'var(--font-body)',
              fontSize: 'var(--text-caption)',
              fontWeight: activeTab === 'resource_grid' ? 600 : 500,
              padding: '6px 16px',
              borderRadius: 'var(--radius-pill)',
              border: activeTab === 'resource_grid' ? '1px solid var(--pulse-blue)' : '1px solid transparent',
              backgroundColor: activeTab === 'resource_grid' ? 'var(--surface)' : 'transparent',
              color: activeTab === 'resource_grid' ? 'var(--pulse-blue)' : 'var(--ink-muted)',
              cursor: 'pointer',
              boxShadow: activeTab === 'resource_grid' ? '0 1px 4px rgba(0,0,0,0.06)' : 'none',
              transition: 'all 0.15s ease',
            }}
          >
            ⚡ Live Resource Grid
          </button>
          <button
            type="button"
            onClick={() => setActiveTab('bed_grid')}
            style={{
              fontFamily: 'var(--font-body)',
              fontSize: 'var(--text-caption)',
              fontWeight: activeTab === 'bed_grid' ? 600 : 500,
              padding: '6px 16px',
              borderRadius: 'var(--radius-pill)',
              border: activeTab === 'bed_grid' ? '1px solid var(--pulse-blue)' : '1px solid transparent',
              backgroundColor: activeTab === 'bed_grid' ? 'var(--surface)' : 'transparent',
              color: activeTab === 'bed_grid' ? 'var(--pulse-blue)' : 'var(--ink-muted)',
              cursor: 'pointer',
              boxShadow: activeTab === 'bed_grid' ? '0 1px 4px rgba(0,0,0,0.06)' : 'none',
              transition: 'all 0.15s ease',
            }}
          >
            🛏️ Hospital Bed Grid
          </button>
          <button
            type="button"
            onClick={() => setActiveTab('overview')}
            style={{
              fontFamily: 'var(--font-body)',
              fontSize: 'var(--text-caption)',
              fontWeight: activeTab === 'overview' ? 600 : 500,
              padding: '6px 16px',
              borderRadius: 'var(--radius-pill)',
              border: activeTab === 'overview' ? '1px solid var(--pulse-blue)' : '1px solid transparent',
              backgroundColor: activeTab === 'overview' ? 'var(--surface)' : 'transparent',
              color: activeTab === 'overview' ? 'var(--pulse-blue)' : 'var(--ink-muted)',
              cursor: 'pointer',
              boxShadow: activeTab === 'overview' ? '0 1px 4px rgba(0,0,0,0.06)' : 'none',
              transition: 'all 0.15s ease',
            }}
          >
            📊 Transaction Overview
          </button>
          <button
            type="button"
            onClick={() => setActiveTab('pharmacy')}
            style={{
              fontFamily: 'var(--font-body)',
              fontSize: 'var(--text-caption)',
              fontWeight: activeTab === 'pharmacy' ? 600 : 500,
              padding: '6px 16px',
              borderRadius: 'var(--radius-pill)',
              border: activeTab === 'pharmacy' ? '1px solid var(--pulse-blue)' : '1px solid transparent',
              backgroundColor: activeTab === 'pharmacy' ? 'var(--surface)' : 'transparent',
              color: activeTab === 'pharmacy' ? 'var(--pulse-blue)' : 'var(--ink-muted)',
              cursor: 'pointer',
              boxShadow: activeTab === 'pharmacy' ? '0 1px 4px rgba(0,0,0,0.06)' : 'none',
              transition: 'all 0.15s ease',
            }}
          >
            💊 Pharmacy Panel
          </button>
          <button
            type="button"
            onClick={() => setActiveTab('diagnostics')}
            style={{
              fontFamily: 'var(--font-body)',
              fontSize: 'var(--text-caption)',
              fontWeight: activeTab === 'diagnostics' ? 600 : 500,
              padding: '6px 16px',
              borderRadius: 'var(--radius-pill)',
              border: activeTab === 'diagnostics' ? '1px solid var(--pulse-blue)' : '1px solid transparent',
              backgroundColor: activeTab === 'diagnostics' ? 'var(--surface)' : 'transparent',
              color: activeTab === 'diagnostics' ? 'var(--pulse-blue)' : 'var(--ink-muted)',
              cursor: 'pointer',
              boxShadow: activeTab === 'diagnostics' ? '0 1px 4px rgba(0,0,0,0.06)' : 'none',
              transition: 'all 0.15s ease',
            }}
          >
            🔬 Diagnostics
          </button>
        </div>
      </div>

      {/* Patient Transfers In-Progress Widget */}
      <TransfersInProgressWidget onOpenTransferModal={() => setShowTransferModal(true)} />

      {activeTab === 'bed_grid' ? (
        /* Bed Grid View */
        <BedGrid
          onBedSelect={(bed) => {
            setModalBed(bed)
          }}
        />
      ) : activeTab === 'overview' ? (
        /* Overview View */
        <>
          {/* Section 1: 4-Column Stat Cards */}
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))',
              gap: 'var(--space-3)',
            }}
          >
            {/* Active TX */}
            <Card style={{ padding: 'var(--space-3)' }}>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
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
                <span
                  style={{
                    fontFamily: 'var(--font-mono)',
                    fontSize: 'var(--text-h1)',
                    fontWeight: 600,
                    color: 'var(--pulse-blue)',
                    lineHeight: 1.1,
                  }}
                >
                  {activeTxCount}
                </span>
              </div>
            </Card>

            {/* Open Conflicts */}
            <Card style={{ padding: 'var(--space-3)' }}>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
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
                <span
                  style={{
                    fontFamily: 'var(--font-mono)',
                    fontSize: 'var(--text-h1)',
                    fontWeight: 600,
                    color: openConflictCount > 0 ? 'var(--alert-amber)' : 'var(--pulse-blue)',
                    lineHeight: 1.1,
                  }}
                >
                  {openConflictCount}
                </span>
              </div>
            </Card>

            {/* Committed */}
            <Card style={{ padding: 'var(--space-3)' }}>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
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
                  Committed
                </span>
                <span
                  style={{
                    fontFamily: 'var(--font-mono)',
                    fontSize: 'var(--text-h1)',
                    fontWeight: 600,
                    color: 'var(--signal-green)',
                    lineHeight: 1.1,
                  }}
                >
                  {committedCount}
                </span>
              </div>
            </Card>

            {/* Aborted */}
            <Card style={{ padding: 'var(--space-3)' }}>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
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
                  Aborted
                </span>
                <span
                  style={{
                    fontFamily: 'var(--font-mono)',
                    fontSize: 'var(--text-h1)',
                    fontWeight: 600,
                    color: 'var(--critical-red)',
                    lineHeight: 1.1,
                  }}
                >
                  {abortedCount}
                </span>
              </div>
            </Card>

            {/* Duplicates Blocked */}
            <Card style={{ padding: 'var(--space-3)' }}>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
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
                  Duplicates Blocked
                </span>
                <span
                  style={{
                    fontFamily: 'var(--font-mono)',
                    fontSize: 'var(--text-h1)',
                    fontWeight: 600,
                    color: '#6366F1',
                    lineHeight: 1.1,
                  }}
                >
                  {duplicatesBlocked}
                </span>
              </div>
            </Card>

            {/* Overrides Today */}
            <Card style={{ padding: 'var(--space-3)' }}>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
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
                  Overrides Today
                </span>
                <span
                  style={{
                    fontFamily: 'var(--font-mono)',
                    fontSize: 'var(--text-h1)',
                    fontWeight: 600,
                    color: '#EF4444',
                    lineHeight: 1.1,
                  }}
                >
                  🚨 {overridesToday}
                </span>
              </div>
            </Card>
          </div>

          {/* Activity Chart */}
          <Card title="Transaction Activity" style={{ marginBottom: 'var(--space-3)' }}>
            <p
              style={{
                fontSize: 'var(--text-caption)',
                color: 'var(--ink-muted)',
                marginBottom: 'var(--space-2)',
                fontFamily: 'var(--font-body)',
              }}
            >
              Committed, aborted, and in-flight transactions over the last 60 events (grouped in batches of 10).
            </p>
            <TxActivityChart transactions={transactions} />
          </Card>

          {/* Recent Transactions */}
          <Card title="Recent Transactions">
            <Table
              columns={[
                { key: 'tx_id', label: 'TX ID', mono: true },
                {
                  key: 'status',
                  label: 'Status',
                  render: (row) => <StateBadge status={row.status} />,
                },
                {
                  key: 'request_type',
                  label: 'Type',
                  render: (row) => (row.request_type === 'care_bundle' ? 'Care Bundle' : 'Single Resource'),
                },
                { key: 'patient_id', label: 'Patient', mono: true },
                {
                  key: 'created_at',
                  label: 'Created',
                  mono: true,
                  render: (row) => formatDate(row.created_at),
                },
              ]}
              rows={transactions.slice(0, 10)}
              onRowClick={(row) => navigate(`/transactions/${row.tx_id}`)}
              emptyMessage="No recent transactions found."
            />
          </Card>

          {/* Open Conflicts */}
          <Card title="Open Conflicts">
            <Table
              columns={[
                { key: 'conflict_id', label: 'Conflict ID', mono: true },
                {
                  key: 'resource_contested',
                  label: 'Contested Resource',
                  mono: true,
                  render: (row) => row.resource_contested || '—',
                },
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
                  label: 'Winner',
                  mono: true,
                  render: (row) => row.winner_tx_id || 'Pending Arbitration',
                },
              ]}
              rows={conflicts.filter((c) => !c.winner_tx_id && !c.resolved_at)}
              onRowClick={() => navigate('/conflicts')}
              emptyMessage="No open conflicts. All resource requests are resolving cleanly."
            />
          </Card>
        </>
      ) : activeTab === 'pharmacy' ? (
        /* Pharmacy Panel */
        <PharmacyGrid />
      ) : activeTab === 'diagnostics' ? (
        /* Diagnostics Panel */
        <DiagnosticsPanel />
      ) : activeTab === 'resource_grid' ? (
        /* Live Resource Grid */
        <ResourceGrid />
      ) : null}

      {/* Bed Action Modal */}
      {modalBed && (
        <BedActionModal
          bed={modalBed}
          onClose={() => setModalBed(null)}
          onBedUpdated={() => {
            refreshBedGrid()
          }}
          onSelectAlternative={(altBed) => {
            setModalBed(altBed)
          }}
        />
      )}

      {/* Patient Transfer Modal */}
      {showTransferModal && (
        <TransferModal
          onClose={() => setShowTransferModal(false)}
          onTransferInitiated={() => {
            fetchTransactions()
          }}
        />
      )}
    </div>
  )
}
