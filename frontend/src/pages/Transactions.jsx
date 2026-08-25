import React, { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import Card from '../components/ui/Card'
import Pagination from '../components/ui/Pagination'
import StateBadge from '../components/ui/StateBadge'
import Table from '../components/ui/Table'
import { useTransactionStore } from '../store/transactionStore'

const STATUS_OPTIONS = [
  { value: '', label: 'All Statuses' },
  { value: 'QUEUED', label: 'QUEUED' },
  { value: 'ARBITRATING', label: 'ARBITRATING' },
  { value: 'PREPARING', label: 'PREPARING' },
  { value: 'COMMITTED', label: 'COMMITTED' },
  { value: 'ACTIVE', label: 'ACTIVE' },
  { value: 'ABORTED', label: 'ABORTED' },
  { value: 'CANCELLED', label: 'CANCELLED' },
  { value: 'COMPLETED', label: 'COMPLETED' },
  { value: 'CLOSED', label: 'CLOSED' },
]

export default function Transactions() {
  const navigate = useNavigate()

  const transactions = useTransactionStore((state) => state.transactions)
  const pagination = useTransactionStore((state) => state.pagination)
  const filters = useTransactionStore((state) => state.filters)
  const fetchTransactions = useTransactionStore((state) => state.fetchTransactions)
  const setFilters = useTransactionStore((state) => state.setFilters)
  const setPage = useTransactionStore((state) => state.setPage)

  const [patientSearch, setPatientSearch] = useState(filters.patient_id || '')

  useEffect(() => {
    fetchTransactions()
  }, [fetchTransactions])

  // Debounced patient search
  useEffect(() => {
    const timer = setTimeout(() => {
      if (patientSearch !== (filters.patient_id || '')) {
        setFilters({ patient_id: patientSearch ? patientSearch.trim() : null })
      }
    }, 300)

    return () => clearTimeout(timer)
  }, [patientSearch, filters.patient_id, setFilters])

  const handleStatusChange = (e) => {
    const val = e.target.value
    setFilters({ status: val || null })
  }

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
        Transactions
      </h1>

      {/* Filter Bar */}
      <Card style={{ padding: 'var(--space-2) var(--space-3)' }}>
        <div
          style={{
            display: 'flex',
            flexWrap: 'wrap',
            alignItems: 'center',
            gap: 'var(--space-3)',
          }}
        >
          {/* Status Filter */}
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <label
              htmlFor="status-filter"
              style={{
                fontFamily: 'var(--font-body)',
                fontSize: 'var(--text-caption)',
                fontWeight: 600,
                color: 'var(--ink-muted)',
                textTransform: 'uppercase',
              }}
            >
              Status:
            </label>
            <select
              id="status-filter"
              value={filters.status || ''}
              onChange={handleStatusChange}
              style={{
                padding: '8px 12px',
                borderRadius: 'var(--radius-input)',
                border: '1px solid var(--line)',
                backgroundColor: 'var(--surface)',
                fontFamily: 'var(--font-body)',
                fontSize: 'var(--text-body)',
                color: 'var(--ink)',
                cursor: 'pointer',
              }}
            >
              {STATUS_OPTIONS.map((opt) => (
                <option key={opt.value} value={opt.value}>
                  {opt.label}
                </option>
              ))}
            </select>
          </div>

          {/* Patient ID Filter */}
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flex: 1, minWidth: '220px' }}>
            <label
              htmlFor="patient-filter"
              style={{
                fontFamily: 'var(--font-body)',
                fontSize: 'var(--text-caption)',
                fontWeight: 600,
                color: 'var(--ink-muted)',
                textTransform: 'uppercase',
              }}
            >
              Patient:
            </label>
            <input
              id="patient-filter"
              type="text"
              placeholder="Filter by Patient ID (e.g. PT-0001)..."
              value={patientSearch}
              onChange={(e) => setPatientSearch(e.target.value)}
              style={{
                flex: 1,
                padding: '8px 12px',
                borderRadius: 'var(--radius-input)',
                border: '1px solid var(--line)',
                backgroundColor: 'var(--surface)',
                fontFamily: 'var(--font-body)',
                fontSize: 'var(--text-body)',
                color: 'var(--ink)',
              }}
            />
          </div>
        </div>
      </Card>

      {/* Transactions Data Table */}
      <Table
        columns={[
          {
            key: 'tx_id',
            label: 'TX ID',
            mono: true,
            render: (row) => (
              <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                <span>{row.tx_id}</span>
                {row.emergency_override && (
                  <span
                    style={{
                      backgroundColor: 'rgba(239, 68, 68, 0.15)',
                      color: '#EF4444',
                      border: '1px solid rgba(239, 68, 68, 0.3)',
                      borderRadius: '4px',
                      padding: '1px 5px',
                      fontSize: '0.7rem',
                      fontWeight: 700,
                      letterSpacing: '0.04em',
                    }}
                  >
                    🚨 OVERRIDE
                  </span>
                )}
              </div>
            ),
          },
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
            key: 'conflict_id',
            label: 'Conflict',
            mono: true,
            render: (row) => row.conflict_id || '—',
          },
          {
            key: 'created_at',
            label: 'Created',
            mono: true,
            render: (row) => formatDate(row.created_at),
          },
        ]}
        rows={transactions}
        onRowClick={(row) => navigate(`/transactions/${row.tx_id}`)}
        emptyMessage="No matching transactions found."
      />

      {/* Pagination Controls */}
      <Pagination
        page={pagination.page}
        pageSize={pagination.page_size}
        total={pagination.total}
        onPageChange={setPage}
      />
    </div>
  )
}
