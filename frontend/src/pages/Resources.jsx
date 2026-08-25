import React, { useEffect } from 'react'
import Card from '../components/ui/Card'
import EmptyState from '../components/ui/EmptyState'
import { useResourceStore } from '../store/resourceStore'

const TYPE_OPTIONS = [
  { value: '', label: 'All Types' },
  { value: 'ot', label: 'Operating Theatres (OT)' },
  { value: 'surgeon', label: 'Surgeons' },
  { value: 'anesthesia', label: 'Anesthesia Teams' },
  { value: 'ventilator', label: 'ICU Ventilators' },
]

const STATUS_OPTIONS = [
  { value: '', label: 'All Statuses' },
  { value: 'available', label: 'Available' },
  { value: 'locked', label: 'Locked' },
  { value: 'tentative', label: 'Tentative (Hold)' },
]

export default function Resources() {
  const resources = useResourceStore((state) => state.resources)
  const filters = useResourceStore((state) => state.filters)
  const fetchResources = useResourceStore((state) => state.fetchResources)
  const setFilters = useResourceStore((state) => state.setFilters)

  useEffect(() => {
    fetchResources()
  }, [fetchResources])

  const handleTypeChange = (e) => {
    setFilters({ type: e.target.value || null })
  }

  const handleStatusChange = (e) => {
    setFilters({ status: e.target.value || null })
  }

  const formatExpiry = (isoStr) => {
    if (!isoStr) return ''
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
        Clinical Resources
      </h1>

      {/* Filter Controls Bar */}
      <Card style={{ padding: 'var(--space-2) var(--space-3)' }}>
        <div
          style={{
            display: 'flex',
            flexWrap: 'wrap',
            alignItems: 'center',
            gap: 'var(--space-3)',
          }}
        >
          {/* Type Filter */}
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <label
              htmlFor="resource-type-filter"
              style={{
                fontFamily: 'var(--font-body)',
                fontSize: 'var(--text-caption)',
                fontWeight: 600,
                color: 'var(--ink-muted)',
                textTransform: 'uppercase',
              }}
            >
              Type:
            </label>
            <select
              id="resource-type-filter"
              value={filters.type || ''}
              onChange={handleTypeChange}
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
              {TYPE_OPTIONS.map((opt) => (
                <option key={opt.value} value={opt.value}>
                  {opt.label}
                </option>
              ))}
            </select>
          </div>

          {/* Status Filter */}
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <label
              htmlFor="resource-status-filter"
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
              id="resource-status-filter"
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
        </div>
      </Card>

      {/* Resource Cards Grid */}
      {resources.length === 0 ? (
        <Card>
          <EmptyState message="No resources match the current filters." />
        </Card>
      ) : (
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fill, minmax(260px, 1fr))',
            gap: 'var(--space-3)',
          }}
        >
          {resources.map((resource) => {
            const status = (resource.status || 'available').toLowerCase()
            const isAvailable = status === 'available'
            const isLocked = status === 'locked'

            const statusBg = isAvailable
              ? 'var(--signal-green-soft)'
              : isLocked
              ? '#FBE9E9'
              : 'var(--pulse-blue-soft)'

            const statusColor = isAvailable
              ? 'var(--signal-green)'
              : isLocked
              ? 'var(--critical-red)'
              : 'var(--pulse-blue)'

            return (
              <Card key={resource.resource_id} style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                {/* Resource Label */}
                <div
                  style={{
                    fontFamily: 'var(--font-mono)',
                    fontWeight: 600,
                    fontSize: 'var(--text-h3)',
                    color: 'var(--ink)',
                  }}
                >
                  {resource.label || resource.resource_id}
                </div>

                {/* Resource ID & Type */}
                <div style={{ color: 'var(--ink-muted)', fontSize: 'var(--text-caption)' }}>
                  {resource.resource_id} · <span style={{ textTransform: 'capitalize' }}>{resource.type}</span>
                </div>

                {/* Status Badge */}
                <div style={{ margin: '4px 0' }}>
                  <span
                    style={{
                      display: 'inline-block',
                      backgroundColor: statusBg,
                      color: statusColor,
                      padding: '2px 10px',
                      borderRadius: 'var(--radius-pill)',
                      fontSize: 'var(--text-caption)',
                      fontFamily: 'var(--font-mono)',
                      fontWeight: 600,
                      border: '1px solid var(--line)',
                      letterSpacing: '0.03em',
                    }}
                  >
                    {status.toUpperCase()}
                  </span>
                </div>

                {/* Held By Transaction */}
                {resource.held_by_tx && (
                  <div style={{ fontSize: 'var(--text-caption)', color: 'var(--ink-muted)' }}>
                    Held by{' '}
                    <span style={{ fontFamily: 'var(--font-mono)', fontWeight: 600, color: 'var(--ink)' }}>
                      {resource.held_by_tx}
                    </span>
                  </div>
                )}

                {/* Hold TTL Expiration */}
                {resource.hold_expires_at && (
                  <div
                    style={{
                      fontSize: 'var(--text-caption)',
                      color: 'var(--alert-amber)',
                      fontFamily: 'var(--font-mono)',
                    }}
                  >
                    Expires: {formatExpiry(resource.hold_expires_at)}
                  </div>
                )}

                {/* Criticality Weight */}
                <div
                  style={{
                    marginTop: 'auto',
                    paddingTop: '6px',
                    borderTop: '1px dashed var(--line)',
                    fontSize: 'var(--text-caption)',
                    color: 'var(--ink-muted)',
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'center',
                  }}
                >
                  <span>
                    Criticality:{' '}
                    <span style={{ fontFamily: 'var(--font-mono)', fontWeight: 600, color: 'var(--ink)' }}>
                      {resource.criticality}
                    </span>
                  </span>
                </div>

                {/* Turnaround & Readiness Actions */}
                <div style={{ display: 'flex', flexDirection: 'column', gap: '6px', marginTop: '8px' }}>
                  {status === 'cleaning' && (
                    <button
                      onClick={async () => {
                        try {
                          await api.post(`/resources/${resource.resource_id}/transitions/cleaning-complete`)
                          fetchResources()
                        } catch (err) {
                          alert(err.response?.data?.detail || 'Failed to complete cleaning')
                        }
                      }}
                      style={{
                        padding: '4px 8px',
                        backgroundColor: '#F59E0B',
                        color: '#FFF',
                        border: 'none',
                        borderRadius: '4px',
                        fontSize: '0.75rem',
                        fontWeight: 600,
                        cursor: 'pointer',
                      }}
                    >
                      ✓ Mark Cleaning Complete
                    </button>
                  )}

                  {status === 'sanitized' && (
                    <button
                      onClick={async () => {
                        try {
                          await api.post(`/resources/${resource.resource_id}/transitions/verify-ready`)
                          fetchResources()
                        } catch (err) {
                          alert(err.response?.data?.detail || 'Failed to verify readiness')
                        }
                      }}
                      style={{
                        padding: '4px 8px',
                        backgroundColor: 'var(--signal-green)',
                        color: '#FFF',
                        border: 'none',
                        borderRadius: '4px',
                        fontSize: '0.75rem',
                        fontWeight: 600,
                        cursor: 'pointer',
                      }}
                    >
                      🛡️ Verify & Sign Off READY
                    </button>
                  )}

                  {!isAvailable && (
                    <button
                      onClick={async () => {
                        try {
                          await api.post(`/resources/${resource.resource_id}/notify-when-ready`)
                          alert(`Subscribed for alert when ${resource.label || resource.resource_id} becomes READY!`)
                        } catch (err) {
                          alert(err.response?.data?.detail || 'Subscription failed')
                        }
                      }}
                      style={{
                        padding: '3px 8px',
                        backgroundColor: 'transparent',
                        color: 'var(--pulse-blue)',
                        border: '1px solid var(--pulse-blue)',
                        borderRadius: '4px',
                        fontSize: '0.72rem',
                        fontWeight: 600,
                        cursor: 'pointer',
                      }}
                    >
                      🔔 Notify Me When Ready
                    </button>
                  )}
                </div>
              </Card>
            )
          })}
        </div>
      )}
    </div>
  )
}
