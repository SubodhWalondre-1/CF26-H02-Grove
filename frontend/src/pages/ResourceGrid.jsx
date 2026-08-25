import React, { useEffect, useMemo, useState } from 'react'
import { Activity, AlertTriangle, CheckCircle2, Clock, Filter, Layers, RefreshCw, ShieldAlert } from 'lucide-react'
import Card from '../components/ui/Card'
import TTLRing from '../components/ui/TTLRing'
import { getResources } from '../lib/api'

const CATEGORY_MAP = {
  ot: 'Operating Theatres & Surgical Suites',
  bed_icu: 'Intensive Care Units (ICU)',
  bed_emergency: 'Emergency & Trauma Bays',
  bed_stepdown: 'Step-Down & HDU Beds',
  bed_general: 'General Inpatient Wards',
  ventilator: 'Ventilators & Critical Life Support',
  diagnostic_ct: 'CT Scan & Imaging Suites',
  diagnostic_mri: 'MRI Imaging Centers',
  diagnostic_xray: 'Emergency Digital Radiography (X-Ray)',
  ambulance: 'Emergency Medical Transport & Ambulances',
  transport_unit: 'Internal Patient Transport Units',
  surgeon: 'Lead Trauma Surgeons & Attendings',
  anesthesiologist: 'Clinical Anesthesiologists',
  nurse_specialist: 'Critical Care Nurse Specialists',
}

const STATUS_CONFIG = {
  ready: { label: 'READY', bg: '#DCFCE7', text: '#15803D', border: '#86EFAC', dot: '#16A34A' },
  available: { label: 'READY', bg: '#DCFCE7', text: '#15803D', border: '#86EFAC', dot: '#16A34A' },
  locked: { label: 'LOCKED / IN USE', bg: '#FEE2E2', text: '#B91C1C', border: '#FCA5A5', dot: '#DC2626' },
  in_use: { label: 'IN USE', bg: '#FEE2E2', text: '#B91C1C', border: '#FCA5A5', dot: '#DC2626' },
  tentative: { label: 'TENTATIVE HOLD', bg: '#FEF3C7', text: '#B45309', border: '#FCD34D', dot: '#D97706' },
  tentative_hold: { label: 'TENTATIVE HOLD', bg: '#FEF3C7', text: '#B45309', border: '#FCD34D', dot: '#D97706' },
  cleaning: { label: 'CLEANING', bg: '#DBEAFE', text: '#1D4ED8', border: '#93C5FD', dot: '#2563EB' },
  sanitized: { label: 'SANITIZED', bg: '#E0E7FF', text: '#4338CA', border: '#A5B4FC', dot: '#4F46E5' },
  maintenance: { label: 'MAINTENANCE', bg: '#F1F5F9', text: '#475569', border: '#CBD5E1', dot: '#64748B' },
}

export default function ResourceGrid() {
  const [resources, setResources] = useState([])
  const [loading, setLoading] = useState(true)
  const [filterCategory, setFilterCategory] = useState('ALL')
  const [filterStatus, setFilterStatus] = useState('ALL')

  const fetchResourceData = async () => {
    try {
      const res = await getResources()
      setResources(res.data || [])
    } catch (err) {
      console.error('Failed to fetch resource grid:', err)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchResourceData()
    const interval = setInterval(fetchResourceData, 5000)
    return () => clearInterval(interval)
  }, [])

  // Categorize resources
  const categorized = useMemo(() => {
    const groups = {}
    resources.forEach((r) => {
      const catKey = r.type || 'other'
      const catTitle = CATEGORY_MAP[catKey] || catKey.toUpperCase()
      if (!groups[catTitle]) {
        groups[catTitle] = []
      }
      groups[catTitle].push(r)
    })
    return groups
  }, [resources])

  // Count summary metrics
  const statusCounts = useMemo(() => {
    const counts = { ready: 0, locked: 0, tentative: 0, turnaround: 0, maintenance: 0 }
    resources.forEach((r) => {
      const s = (r.status || '').toLowerCase()
      if (s === 'ready' || s === 'available') counts.ready++
      else if (s === 'locked' || s === 'in_use') counts.locked++
      else if (s === 'tentative' || s === 'tentative_hold') counts.tentative++
      else if (s === 'cleaning' || s === 'sanitized') counts.turnaround++
      else counts.maintenance++
    })
    return counts
  }, [resources])

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-4)' }}>
      {/* 1. Header & Live Indicator */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '12px' }}>
        <div>
          <h2 style={{ fontSize: '1.25rem', fontWeight: 700, color: 'var(--ink)', margin: 0, display: 'flex', alignItems: 'center', gap: '8px' }}>
            <Layers size={22} color="#1E3A8A" />
            Live Hospital Resource Grid
          </h2>
          <p style={{ margin: '2px 0 0', fontSize: '0.85rem', color: 'var(--ink-muted)' }}>
            Real-time visual state coordinator across all clinical suites, beds, and diagnostic machines.
          </p>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          <button
            onClick={fetchResourceData}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '6px',
              padding: '6px 12px',
              borderRadius: '6px',
              border: '1px solid var(--line)',
              background: '#fff',
              cursor: 'pointer',
              fontSize: '0.8rem',
              fontWeight: 600,
            }}
          >
            <RefreshCw size={14} className={loading ? 'animate-spin' : ''} />
            Refresh
          </button>
        </div>
      </div>

      {/* 2. Global State Meter Strip */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(130px, 1fr))',
          gap: '10px',
        }}
      >
        <div style={{ padding: '10px 14px', borderRadius: '8px', background: '#DCFCE7', border: '1px solid #86EFAC' }}>
          <div style={{ fontSize: '0.75rem', fontWeight: 700, color: '#15803D' }}>🟢 READY / AVAILABLE</div>
          <div style={{ fontSize: '1.3rem', fontWeight: 800, color: '#166534' }}>{statusCounts.ready}</div>
        </div>
        <div style={{ padding: '10px 14px', borderRadius: '8px', background: '#FEE2E2', border: '1px solid #FCA5A5' }}>
          <div style={{ fontSize: '0.75rem', fontWeight: 700, color: '#B91C1C' }}>🔴 LOCKED / IN USE</div>
          <div style={{ fontSize: '1.3rem', fontWeight: 800, color: '#991B1B' }}>{statusCounts.locked}</div>
        </div>
        <div style={{ padding: '10px 14px', borderRadius: '8px', background: '#FEF3C7', border: '1px solid #FCD34D' }}>
          <div style={{ fontSize: '0.75rem', fontWeight: 700, color: '#B45309' }}>🟡 TENTATIVE HOLD</div>
          <div style={{ fontSize: '1.3rem', fontWeight: 800, color: '#92400E' }}>{statusCounts.tentative}</div>
        </div>
        <div style={{ padding: '10px 14px', borderRadius: '8px', background: '#DBEAFE', border: '1px solid #93C5FD' }}>
          <div style={{ fontSize: '0.75rem', fontWeight: 700, color: '#1D4ED8' }}>🔵 CLEANING / SANITIZED</div>
          <div style={{ fontSize: '1.3rem', fontWeight: 800, color: '#1E40AF' }}>{statusCounts.turnaround}</div>
        </div>
        <div style={{ padding: '10px 14px', borderRadius: '8px', background: '#F1F5F9', border: '1px solid #CBD5E1' }}>
          <div style={{ fontSize: '0.75rem', fontWeight: 700, color: '#475569' }}>⚫ MAINTENANCE</div>
          <div style={{ fontSize: '1.3rem', fontWeight: 800, color: '#334155' }}>{statusCounts.maintenance}</div>
        </div>
      </div>

      {/* 3. Categorized Resource Blocks */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-4)' }}>
        {Object.entries(categorized).map(([categoryTitle, items]) => (
          <Card key={categoryTitle} style={{ padding: 'var(--space-3)' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px', borderBottom: '1px solid var(--line)', paddingBottom: '6px' }}>
              <h3 style={{ fontSize: '0.95rem', fontWeight: 700, color: 'var(--ink)', margin: 0 }}>
                {categoryTitle}
              </h3>
              <span style={{ fontSize: '0.75rem', color: 'var(--ink-muted)', fontWeight: 600 }}>
                {items.length} units
              </span>
            </div>

            {/* Grid of Chips */}
            <div
              style={{
                display: 'grid',
                gridTemplateColumns: 'repeat(auto-fill, minmax(180px, 1fr))',
                gap: '10px',
              }}
            >
              {items.map((res) => {
                const s = (res.status || 'available').toLowerCase()
                const cfg = STATUS_CONFIG[s] || STATUS_CONFIG.ready
                const isTentative = s === 'tentative' || s === 'tentative_hold'

                return (
                  <div
                    key={res.resource_id}
                    style={{
                      display: 'flex',
                      flexDirection: 'column',
                      justifyContent: 'space-between',
                      padding: '8px 10px',
                      borderRadius: '8px',
                      backgroundColor: cfg.bg,
                      border: `1px solid ${cfg.border}`,
                      transition: 'transform 0.15s ease, box-shadow 0.15s ease',
                      minHeight: '68px',
                    }}
                  >
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                      <span style={{ fontWeight: 700, fontSize: '0.85rem', color: 'var(--ink)', fontFamily: 'var(--font-mono)' }}>
                        {res.resource_id}
                      </span>
                      <span
                        style={{
                          display: 'inline-block',
                          width: '8px',
                          height: '8px',
                          borderRadius: '50%',
                          backgroundColor: cfg.dot,
                        }}
                      />
                    </div>

                    <div style={{ fontSize: '0.75rem', color: 'var(--ink)', fontWeight: 500, margin: '2px 0 4px', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                      {res.label || res.resource_id}
                    </div>

                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: 'auto' }}>
                      <span style={{ fontSize: '0.7rem', fontWeight: 700, color: cfg.text }}>
                        {cfg.label}
                      </span>

                      {isTentative && res.hold_expires_at && (
                        <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                          <Clock size={12} color="#B45309" />
                          <span style={{ fontSize: '0.65rem', fontWeight: 700, color: '#B45309' }}>HOLD</span>
                        </div>
                      )}
                    </div>
                  </div>
                )
              })}
            </div>
          </Card>
        ))}
      </div>
    </div>
  )
}
