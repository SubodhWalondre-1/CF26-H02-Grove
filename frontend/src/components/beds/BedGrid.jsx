// frontend/src/components/beds/BedGrid.jsx
import React, { useEffect, useState } from 'react'
import BedCard from './BedCard'
import Card from '../ui/Card'
import { useBedStore } from '../../store/stores'
import api from '../../lib/api'

const STATUS_COLORS = {
  READY          : '#0F9D66',
  IN_USE         : '#B23B3B',
  CLEANING       : '#C77D22',
  TENTATIVE_HOLD : '#E67E22',
  LOCKED         : '#DC2626',
  MAINTENANCE    : '#5B6767',
  SANITIZED      : '#0B6E8F',
  FREE           : '#A0AEC0',
  POST_USE       : '#805AD5',
}

function FloorSummaryBar({ summary = {} }) {
  const total = Object.values(summary).reduce((a, b) => a + b, 0)
  if (total === 0) return null

  return (
    <div
      style={{
        display: 'flex',
        height: '8px',
        width: '100%',
        borderRadius: 'var(--radius-pill)',
        overflow: 'hidden',
        backgroundColor: 'var(--surface-recessed)',
        border: '1px solid var(--line)',
        marginBottom: 'var(--space-2)',
        gap: '1px',
      }}
    >
      {Object.entries(summary).map(([status, count]) =>
        count > 0 ? (
          <div
            key={status}
            title={`${status}: ${count}`}
            style={{
              width: `${(count / total) * 100}%`,
              backgroundColor: STATUS_COLORS[status] || '#CBD5E1',
              transition: 'width 0.3s ease',
            }}
          />
        ) : null
      )}
    </div>
  )
}

function FilterBar({ filters, setFilters }) {
  const types = ['ALL', 'ICU', 'GENERAL', 'STEP_DOWN', 'EMERGENCY']
  const statuses = ['ALL', 'READY', 'IN_USE', 'CLEANING', 'MAINTENANCE', 'TENTATIVE_HOLD']

  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        flexWrap: 'wrap',
        gap: 'var(--space-2)',
        paddingBottom: 'var(--space-2)',
        borderBottom: '1px solid var(--line)',
        marginBottom: 'var(--space-3)',
      }}
    >
      {/* Type pill selectors */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '6px', flexWrap: 'wrap' }}>
        <span
          style={{
            fontFamily: 'var(--font-body)',
            fontSize: 'var(--text-caption)',
            fontWeight: 600,
            color: 'var(--ink-muted)',
            marginRight: '4px',
            textTransform: 'uppercase',
            letterSpacing: '0.04em',
          }}
        >
          Ward:
        </span>
        {types.map((type) => {
          const isSelected = (filters.type ?? 'ALL') === type
          return (
            <button
              key={type}
              type="button"
              onClick={() => setFilters((f) => ({ ...f, type: type === 'ALL' ? null : type }))}
              style={{
                fontFamily: 'var(--font-body)',
                fontSize: '0.8rem',
                fontWeight: isSelected ? 600 : 500,
                padding: '5px 12px',
                borderRadius: 'var(--radius-pill)',
                border: isSelected ? '1px solid var(--pulse-blue)' : '1px solid var(--line)',
                backgroundColor: isSelected ? 'var(--pulse-blue)' : 'var(--surface)',
                color: isSelected ? '#FFFFFF' : 'var(--ink-muted)',
                cursor: 'pointer',
                transition: 'all 0.15s ease',
              }}
            >
              {type}
            </button>
          )
        })}
      </div>

      {/* Status dropdown */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
        <span
          style={{
            fontFamily: 'var(--font-body)',
            fontSize: 'var(--text-caption)',
            fontWeight: 600,
            color: 'var(--ink-muted)',
            textTransform: 'uppercase',
            letterSpacing: '0.04em',
          }}
        >
          Status:
        </span>
        <select
          value={filters.status || 'ALL'}
          onChange={(e) =>
            setFilters((f) => ({
              ...f,
              status: e.target.value === 'ALL' ? null : e.target.value,
            }))
          }
          style={{
            fontFamily: 'var(--font-body)',
            fontSize: '0.82rem',
            fontWeight: 500,
            padding: '6px 14px',
            borderRadius: 'var(--radius-input)',
            border: '1px solid var(--line)',
            backgroundColor: 'var(--surface)',
            color: 'var(--ink)',
            cursor: 'pointer',
            outline: 'none',
          }}
        >
          {statuses.map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
        </select>
      </div>
    </div>
  )
}

export default function BedGrid({ onBedSelect }) {
  const { bedGrid = [], setBedGrid, updateBedStatus } = useBedStore()
  const [filters, setFilters] = useState({ type: null, status: null })
  const [wsReady, setWsReady] = useState(false)

  // Initial load
  useEffect(() => {
    const loadBedGrid = async () => {
      try {
        const response = await api.get('/beds/grid')
        setBedGrid(response.data || [])
      } catch (err) {
        const token = localStorage.getItem('token')
        fetch('/api/v1/beds/grid', {
          headers: token ? { Authorization: `Bearer ${token}` } : {},
        })
          .then((r) => r.json())
          .then((data) => setBedGrid(Array.isArray(data) ? data : []))
          .catch(console.error)
      }
    }

    loadBedGrid()
  }, [setBedGrid])

  // WebSocket — live bed updates
  useEffect(() => {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const host = window.location.host || 'localhost:8000'
    const socket = new WebSocket(`${protocol}//${host}/ws/beds`)

    socket.onopen = () => setWsReady(true)
    socket.onclose = () => setWsReady(false)
    socket.onerror = () => setWsReady(false)

    socket.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data)
        if (data.event === 'BED_STATUS_CHANGED' && data.bed_id) {
          updateBedStatus(data.bed_id, data.new_status, {
            estimated_ready_at: data.estimated_ready_at,
            current_patient_id: data.current_patient_id,
          })
        }
      } catch (e) {
        console.warn('Error parsing WebSocket message:', e)
      }
    }

    return () => {
      try {
        socket.close()
      } catch (_) {}
    }
  }, [updateBedStatus])

  const safeGrid = Array.isArray(bedGrid) ? bedGrid : []
  const filteredGrid = safeGrid
    .map((floor) => ({
      ...floor,
      beds: (floor.beds || []).filter((bed) => {
        if (filters.type && bed.bed_type !== filters.type) return false
        if (filters.status && bed.status !== filters.status) return false
        return true
      }),
    }))
    .filter((floor) => floor.beds && floor.beds.length > 0)

  return (
    <Card style={{ padding: 'var(--space-3)' }}>
      {/* Title & Live Strip */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          marginBottom: 'var(--space-2)',
        }}
      >
        <div>
          <h2
            style={{
              fontFamily: 'var(--font-display)',
              fontSize: 'var(--text-h2)',
              fontWeight: 600,
              color: 'var(--ink)',
              margin: 0,
            }}
          >
            Hospital Bed Grid
          </h2>
          <p
            style={{
              fontFamily: 'var(--font-body)',
              fontSize: 'var(--text-caption)',
              color: 'var(--ink-muted)',
              margin: '2px 0 0 0',
            }}
          >
            Live floor-wise clinical bed occupancy, readiness countdowns & unit allocations
          </p>
        </div>

        {/* Live Stream indicator */}
        <span
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: '6px',
            padding: '4px 12px',
            borderRadius: 'var(--radius-pill)',
            backgroundColor: wsReady ? 'var(--signal-green-soft)' : '#FEF3E2',
            border: `1px solid ${wsReady ? '#A7F3D0' : '#FCD34D'}`,
            fontFamily: 'var(--font-mono)',
            fontSize: '0.75rem',
            fontWeight: 600,
            color: wsReady ? 'var(--signal-green)' : 'var(--alert-amber)',
          }}
        >
          <span
            style={{
              width: '7px',
              height: '7px',
              borderRadius: '50%',
              backgroundColor: wsReady ? 'var(--signal-green)' : 'var(--alert-amber)',
              display: 'inline-block',
            }}
          />
          {wsReady ? 'LIVE STREAM' : 'CONNECTING'}
        </span>
      </div>

      {/* Filter Bar */}
      <FilterBar filters={filters} setFilters={setFilters} />

      {/* Floors */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-4)' }}>
        {filteredGrid.map((floor) => (
          <div
            key={floor.floor}
            style={{
              padding: 'var(--space-2)',
              backgroundColor: 'var(--surface-recessed)',
              borderRadius: 'var(--radius-card)',
              border: '1px solid var(--line)',
            }}
          >
            {/* Floor Header */}
            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                marginBottom: 'var(--space-1)',
                flexWrap: 'wrap',
                gap: 'var(--space-1)',
              }}
            >
              <div style={{ display: 'flex', alignItems: 'baseline', gap: '8px' }}>
                <h3
                  style={{
                    fontFamily: 'var(--font-display)',
                    fontSize: 'var(--text-h3)',
                    fontWeight: 600,
                    color: 'var(--ink)',
                    margin: 0,
                  }}
                >
                  Floor {floor.floor}
                </h3>
                <span
                  style={{
                    fontFamily: 'var(--font-body)',
                    fontSize: 'var(--text-caption)',
                    color: 'var(--ink-muted)',
                  }}
                >
                  ({floor.beds.length} beds)
                </span>
              </div>

              {/* Status summary pill tags */}
              <div style={{ display: 'flex', gap: '6px', flexWrap: 'wrap' }}>
                {Object.entries(floor.summary || {}).map(([s, count]) =>
                  count > 0 ? (
                    <span
                      key={s}
                      style={{
                        fontFamily: 'var(--font-mono)',
                        fontSize: '0.7rem',
                        fontWeight: 600,
                        padding: '2px 7px',
                        borderRadius: '4px',
                        backgroundColor: 'var(--surface)',
                        border: '1px solid var(--line)',
                        color: STATUS_COLORS[s] || 'var(--ink-muted)',
                      }}
                    >
                      {s}: {count}
                    </span>
                  ) : null
                )}
              </div>
            </div>

            {/* Summary Progress Bar */}
            <FloorSummaryBar summary={floor.summary} />

            {/* Bed Cards Grid */}
            <div
              style={{
                display: 'grid',
                gridTemplateColumns: 'repeat(auto-fill, minmax(130px, 1fr))',
                gap: '10px',
                marginTop: 'var(--space-1)',
              }}
            >
              {floor.beds.map((bed) => (
                <BedCard key={bed.id} bed={bed} onClick={onBedSelect} />
              ))}
            </div>
          </div>
        ))}

        {filteredGrid.length === 0 && (
          <div
            style={{
              textAlign: 'center',
              padding: 'var(--space-6) 0',
              fontFamily: 'var(--font-body)',
              color: 'var(--ink-muted)',
              fontSize: 'var(--text-body)',
            }}
          >
            No beds match the selected filters.
          </div>
        )}
      </div>
    </Card>
  )
}
