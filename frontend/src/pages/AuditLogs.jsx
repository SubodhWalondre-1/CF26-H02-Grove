import React, { useCallback, useEffect, useState } from 'react'
import Card from '../components/ui/Card'
import EmptyState from '../components/ui/EmptyState'
import Pagination from '../components/ui/Pagination'
import StateBadge from '../components/ui/StateBadge'
import { getFullTrace, listAuditEvents } from '../lib/api'
import { wsManager } from '../lib/websocket'

const EVENT_TYPES = [
  { value: '', label: 'All Event Types' },
  { value: 'TENTATIVE_HOLD', label: 'TENTATIVE_HOLD' },
  { value: 'LOCK_ACQUIRED', label: 'LOCK_ACQUIRED' },
  { value: 'CONFLICT_DETECTED', label: 'CONFLICT_DETECTED' },
  { value: 'ARBITRATION_RESULT', label: 'ARBITRATION_RESULT' },
  { value: 'COMMIT', label: 'COMMIT' },
  { value: 'ROLLBACK', label: 'ROLLBACK' },
  { value: 'CANCEL', label: 'CANCEL' },
  { value: 'COMPENSATION', label: 'COMPENSATION' },
  { value: 'TTL_WARNING', label: 'TTL_WARNING' },
  { value: 'RECOVERY_ACTION', label: 'RECOVERY_ACTION' },
]

export default function AuditLogs() {
  const [events, setEvents] = useState([])
  const [pagination, setPagination] = useState({ page: 1, page_size: 50, total: 0 })
  const [filters, setFilters] = useState({
    tx_id: '',
    event_type: '',
    from: '',
    to: '',
  })

  const [expandedTxId, setExpandedTxId] = useState(null)
  const [traceData, setTraceData] = useState(null)
  const [isLoadingTrace, setIsLoadingTrace] = useState(false)
  const [isLoading, setIsLoading] = useState(true)

  const loadAuditEvents = useCallback(async (customPage) => {
    setIsLoading(true)
    try {
      const pageToFetch = customPage || pagination.page
      const queryParams = {
        page: pageToFetch,
        page_size: pagination.page_size,
        tx_id: filters.tx_id ? filters.tx_id.trim() : undefined,
        event_type: filters.event_type || undefined,
        from: filters.from || undefined,
        to: filters.to || undefined,
      }

      Object.keys(queryParams).forEach(
        (k) => (queryParams[k] == null || queryParams[k] === '') && delete queryParams[k]
      )

      const res = await listAuditEvents(queryParams)
      const data = res.data

      setEvents(data.items || [])
      setPagination({
        page: data.page || pageToFetch,
        page_size: data.page_size || 50,
        total: data.total || 0,
      })
    } catch (err) {
      console.error('Error fetching audit events:', err)
    } finally {
      setIsLoading(false)
    }
  }, [filters, pagination.page, pagination.page_size])

  useEffect(() => {
    loadAuditEvents(1)
  }, [filters.event_type, filters.from, filters.to, loadAuditEvents])

  // Debounced TX search
  useEffect(() => {
    const timer = setTimeout(() => {
      loadAuditEvents(1)
    }, 300)
    return () => clearTimeout(timer)
  }, [filters.tx_id, loadAuditEvents])

  // WebSocket live prepend
  useEffect(() => {
    const unsub = wsManager.subscribe('AUDIT_EVENT', (msg) => {
      const auditEntry = msg.data || msg
      if (!auditEntry || !auditEntry.audit_id) return

      // Prepend if matches current filter
      if (filters.event_type && auditEntry.event_type !== filters.event_type) return
      if (filters.tx_id && !auditEntry.tx_id?.includes(filters.tx_id)) return

      setEvents((prev) => [auditEntry, ...prev])
      setPagination((prev) => ({ ...prev, total: prev.total + 1 }))
    })

    return () => unsub()
  }, [filters.event_type, filters.tx_id])

  const handleRowClick = async (row) => {
    const txId = row.tx_id
    if (!txId) return

    if (expandedTxId === txId) {
      setExpandedTxId(null)
      setTraceData(null)
      return
    }

    setExpandedTxId(txId)
    setIsLoadingTrace(true)
    try {
      const res = await getFullTrace(txId)
      setTraceData(res.data)
    } catch (err) {
      console.warn(`Could not load full trace for ${txId}:`, err)
      setTraceData(null)
    } finally {
      setIsLoadingTrace(false)
    }
  }

  const formatDate = (isoStr) => {
    if (!isoStr) return '—'
    try {
      const d = new Date(isoStr)
      return `${d.toLocaleDateString()} ${d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })}`
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
        Audit Event Trail
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
          {/* TX ID Search */}
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', minWidth: '180px' }}>
            <label
              htmlFor="audit-tx-filter"
              style={{
                fontFamily: 'var(--font-body)',
                fontSize: 'var(--text-caption)',
                fontWeight: 600,
                color: 'var(--ink-muted)',
                textTransform: 'uppercase',
              }}
            >
              TX ID:
            </label>
            <input
              id="audit-tx-filter"
              type="text"
              placeholder="e.g. TX-001..."
              value={filters.tx_id}
              onChange={(e) => setFilters((prev) => ({ ...prev, tx_id: e.target.value }))}
              style={{
                padding: '8px 12px',
                borderRadius: 'var(--radius-input)',
                border: '1px solid var(--line)',
                backgroundColor: 'var(--surface)',
                fontFamily: 'var(--font-body)',
                fontSize: 'var(--text-body)',
                color: 'var(--ink)',
                width: '140px',
              }}
            />
          </div>

          {/* Event Type Select */}
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <label
              htmlFor="audit-event-type-filter"
              style={{
                fontFamily: 'var(--font-body)',
                fontSize: 'var(--text-caption)',
                fontWeight: 600,
                color: 'var(--ink-muted)',
                textTransform: 'uppercase',
              }}
            >
              Event:
            </label>
            <select
              id="audit-event-type-filter"
              value={filters.event_type}
              onChange={(e) => setFilters((prev) => ({ ...prev, event_type: e.target.value }))}
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
              {EVENT_TYPES.map((opt) => (
                <option key={opt.value} value={opt.value}>
                  {opt.label}
                </option>
              ))}
            </select>
          </div>

          {/* Date Range: From */}
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <label
              htmlFor="audit-from-filter"
              style={{
                fontFamily: 'var(--font-body)',
                fontSize: 'var(--text-caption)',
                fontWeight: 600,
                color: 'var(--ink-muted)',
                textTransform: 'uppercase',
              }}
            >
              From:
            </label>
            <input
              id="audit-from-filter"
              type="date"
              value={filters.from}
              onChange={(e) => setFilters((prev) => ({ ...prev, from: e.target.value }))}
              style={{
                padding: '8px 10px',
                borderRadius: 'var(--radius-input)',
                border: '1px solid var(--line)',
                backgroundColor: 'var(--surface)',
                fontFamily: 'var(--font-body)',
                fontSize: 'var(--text-caption)',
                color: 'var(--ink)',
              }}
            />
          </div>

          {/* Date Range: To */}
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <label
              htmlFor="audit-to-filter"
              style={{
                fontFamily: 'var(--font-body)',
                fontSize: 'var(--text-caption)',
                fontWeight: 600,
                color: 'var(--ink-muted)',
                textTransform: 'uppercase',
              }}
            >
              To:
            </label>
            <input
              id="audit-to-filter"
              type="date"
              value={filters.to}
              onChange={(e) => setFilters((prev) => ({ ...prev, to: e.target.value }))}
              style={{
                padding: '8px 10px',
                borderRadius: 'var(--radius-input)',
                border: '1px solid var(--line)',
                backgroundColor: 'var(--surface)',
                fontFamily: 'var(--font-body)',
                fontSize: 'var(--text-caption)',
                color: 'var(--ink)',
              }}
            />
          </div>
        </div>
      </Card>

      {/* Dense Audit Table */}
      <div
        style={{
          width: '100%',
          overflowX: 'auto',
          borderRadius: 'var(--radius-card)',
          border: '1px solid var(--line)',
          backgroundColor: 'var(--surface)',
        }}
      >
        <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left' }}>
          <thead>
            <tr style={{ backgroundColor: 'var(--surface-recessed)', borderBottom: '1px solid var(--line)' }}>
              <th style={{ padding: '8px 12px', fontSize: 'var(--text-caption)', color: 'var(--ink-muted)' }}>AUDIT ID</th>
              <th style={{ padding: '8px 12px', fontSize: 'var(--text-caption)', color: 'var(--ink-muted)' }}>TX ID</th>
              <th style={{ padding: '8px 12px', fontSize: 'var(--text-caption)', color: 'var(--ink-muted)' }}>EVENT</th>
              <th style={{ padding: '8px 12px', fontSize: 'var(--text-caption)', color: 'var(--ink-muted)' }}>CONFLICT</th>
              <th style={{ padding: '8px 12px', fontSize: 'var(--text-caption)', color: 'var(--ink-muted)' }}>SCORE</th>
              <th style={{ padding: '8px 12px', fontSize: 'var(--text-caption)', color: 'var(--ink-muted)' }}>DECISION</th>
              <th style={{ padding: '8px 12px', fontSize: 'var(--text-caption)', color: 'var(--ink-muted)' }}>TIMESTAMP</th>
            </tr>
          </thead>
          <tbody>
            {events.length === 0 ? (
              <tr>
                <td colSpan={7} style={{ padding: 0 }}>
                  <EmptyState message="No audit records match the current criteria." />
                </td>
              </tr>
            ) : (
              events.map((row, idx) => {
                const isEven = idx % 2 === 0
                const isExpanded = expandedTxId === row.tx_id

                return (
                  <React.Fragment key={row.audit_id || idx}>
                    <tr
                      onClick={() => handleRowClick(row)}
                      style={{
                        backgroundColor: isExpanded
                          ? 'var(--pulse-blue-soft)'
                          : isEven
                          ? 'var(--surface)'
                          : 'var(--surface-recessed)',
                        borderBottom: '1px solid var(--line)',
                        cursor: 'pointer',
                        transition: 'background-color 150ms ease',
                      }}
                    >
                      <td style={{ padding: '8px 12px', fontFamily: 'var(--font-mono)', fontSize: '0.8125rem' }}>
                        {row.audit_id}
                      </td>
                      <td style={{ padding: '8px 12px', fontFamily: 'var(--font-mono)', fontSize: '0.8125rem', fontWeight: 600 }}>
                        {row.tx_id || '—'}
                      </td>
                      <td style={{ padding: '8px 12px', fontFamily: 'var(--font-mono)', fontSize: '0.8125rem', color: 'var(--pulse-blue)' }}>
                        {row.event_type || '—'}
                      </td>
                      <td style={{ padding: '8px 12px', fontFamily: 'var(--font-mono)', fontSize: '0.8125rem' }}>
                        {row.conflict_id || '—'}
                      </td>
                      <td style={{ padding: '8px 12px', fontFamily: 'var(--font-mono)', fontSize: '0.8125rem' }}>
                        {row.effective_score != null ? row.effective_score.toFixed(1) : '—'}
                      </td>
                      <td style={{ padding: '8px 12px', fontSize: '0.8125rem', fontWeight: 500 }}>
                        {row.decision || '—'}
                      </td>
                      <td style={{ padding: '8px 12px', fontFamily: 'var(--font-mono)', fontSize: '0.75rem', color: 'var(--ink-muted)' }}>
                        {formatDate(row.timestamp)}
                      </td>
                    </tr>

                    {/* Inline Trace Expansion Drawer */}
                    {isExpanded && (
                      <tr style={{ backgroundColor: 'var(--surface-recessed)', borderBottom: '2px solid var(--pulse-blue)' }}>
                        <td colSpan={7} style={{ padding: '16px 20px' }}>
                          <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                            <div style={{ fontWeight: 600, fontFamily: 'var(--font-mono)', color: 'var(--pulse-blue)' }}>
                              Chronological Full Trace for {row.tx_id}:
                            </div>

                            {isLoadingTrace ? (
                              <div style={{ color: 'var(--ink-muted)' }}>Loading complete trace...</div>
                            ) : traceData && traceData.trace ? (
                              <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
                                {traceData.trace.map((item, tIdx) => (
                                  <div
                                    key={tIdx}
                                    style={{
                                      display: 'flex',
                                      alignItems: 'center',
                                      justifyContent: 'space-between',
                                      padding: '6px 12px',
                                      backgroundColor: 'var(--surface)',
                                      borderRadius: 'var(--radius-input)',
                                      border: '1px solid var(--line)',
                                    }}
                                  >
                                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                                      <StateBadge status={item.decision || item.event_type || 'ACTIVE'} />
                                      <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.8125rem' }}>
                                        {item.event_type} {item.decision ? `(${item.decision})` : ''}
                                      </span>
                                    </div>
                                    <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.75rem', color: 'var(--ink-muted)' }}>
                                      {formatDate(item.timestamp)}
                                    </span>
                                  </div>
                                ))}
                              </div>
                            ) : (
                              <div style={{ color: 'var(--ink-muted)' }}>No additional trace history available.</div>
                            )}
                          </div>
                        </td>
                      </tr>
                    )}
                  </React.Fragment>
                )
              })
            )}
          </tbody>
        </table>
      </div>

      {/* Pagination Controls */}
      <Pagination
        page={pagination.page}
        pageSize={pagination.page_size}
        total={pagination.total}
        onPageChange={(p) => {
          setPagination((prev) => ({ ...prev, page: p }))
          loadAuditEvents(p)
        }}
      />
    </div>
  )
}
