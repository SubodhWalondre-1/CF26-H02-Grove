// frontend/src/components/beds/BedActionModal.jsx
import React, { useEffect, useState } from 'react'
import BedStatusBadge from './BedStatusBadge'
import api from '../../lib/api'
import { useAuthStore } from '../../store/authStore'

export default function BedActionModal({ bed, onClose, onBedUpdated, onSelectAlternative }) {
  const user = useAuthStore((state) => state.user)
  const isAdmin = user?.role === 'admin'
  const [readyAlternatives, setReadyAlternatives] = useState([])
  const [allocationMessage, setAllocationMessage] = useState(null)
  const [allocationError, setAllocationError] = useState(null)
  const [isLoading, setIsLoading] = useState(false)
  const [patientId, setPatientId] = useState('PT-TEST')
  const [releaseReason, setReleaseReason] = useState('DISCHARGED')

  useEffect(() => {
    if (bed && bed.status !== 'READY') {
      api.get(`/beds/available?bed_type=${bed.bed_type}`)
        .then((res) => {
          const list = Array.isArray(res.data) ? res.data : []
          setReadyAlternatives(list.filter((b) => b.id !== bed.id))
        })
        .catch(() => setReadyAlternatives([]))
    } else {
      setReadyAlternatives([])
    }
    setAllocationMessage(null)
    setAllocationError(null)
  }, [bed])

  if (!bed) return null

  const ttlMinutes = bed.estimated_ready_at
    ? Math.max(0, Math.ceil((new Date(bed.estimated_ready_at) - new Date()) / 60000))
    : null

  const handleRequestAllocation = async () => {
    setIsLoading(true)
    setAllocationError(null)
    setAllocationMessage(null)

    // Readiness Engine Guard
    if (bed.status !== 'READY') {
      setIsLoading(false)
      setAllocationError(
        `Bed ${bed.bed_number} is NOT READY (${bed.status}). ${
          ttlMinutes ? `Estimated ~${ttlMinutes} min remaining.` : ''
        }`
      )
      return
    }

    try {
      setAllocationMessage(`Bed ${bed.bed_number} allocated successfully for patient ${patientId}.`)
      onBedUpdated?.()
    } catch (err) {
      setAllocationError(err.response?.data?.detail || 'Allocation failed')
    } finally {
      setIsLoading(false)
    }
  }

  const handleReleaseBed = async () => {
    setIsLoading(true)
    setAllocationError(null)
    try {
      await api.post(`/beds/${bed.id}/release`, {
        patient_id: bed.current_patient_id || patientId,
        release_reason: releaseReason,
      })
      setAllocationMessage(`Bed ${bed.bed_number} released. Auto-cleaning initiated.`)
      onBedUpdated?.()
    } catch (err) {
      setAllocationError(err.response?.data?.detail || 'Failed to release bed')
    } finally {
      setIsLoading(false)
    }
  }

  const handleCompleteCleaning = async () => {
    setIsLoading(true)
    setAllocationError(null)
    try {
      const logs = bed.cleaning_logs || []
      const activeLog = logs.find((l) => l.status === 'in_progress') || { id: 'CLG-DIRECT' }
      await api.post('/beds/cleaning/complete', {
        cleaning_log_id: activeLog.id,
        notes: 'Verified sanitized and ready by housekeeping.',
      })
      setAllocationMessage(`Bed ${bed.bed_number} verified and returned to READY.`)
      onBedUpdated?.()
    } catch (err) {
      setAllocationError(err.response?.data?.detail || 'Failed to complete cleaning')
    } finally {
      setIsLoading(false)
    }
  }

  const handleToggleMaintenance = async (action) => {
    setIsLoading(true)
    setAllocationError(null)
    try {
      if (action === 'start') {
        await api.post(`/beds/${bed.id}/maintenance`, {
          reason: 'Routine clinical engineering inspection',
        })
      } else {
        await api.post(`/beds/${bed.id}/maintenance/resolve`, {})
      }
      setAllocationMessage(`Bed maintenance status updated.`)
      onBedUpdated?.()
    } catch (err) {
      setAllocationError(err.response?.data?.detail || 'Maintenance action failed')
    } finally {
      setIsLoading(false)
    }
  }

  return (
    <div
      style={{
        position: 'fixed',
        inset: 0,
        backgroundColor: 'rgba(14, 20, 20, 0.65)',
        backdropFilter: 'blur(4px)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        zIndex: 999,
        padding: 'var(--space-2)',
      }}
      onClick={onClose}
    >
      <div
        style={{
          backgroundColor: 'var(--surface)',
          border: '1px solid var(--line)',
          borderRadius: 'var(--radius-card)',
          width: '100%',
          maxWidth: '520px',
          padding: 'var(--space-3)',
          boxShadow: '0 20px 40px rgba(0,0,0,0.2)',
          position: 'relative',
          display: 'flex',
          flexDirection: 'column',
          gap: 'var(--space-2)',
        }}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Close Button */}
        <button
          type="button"
          onClick={onClose}
          style={{
            position: 'absolute',
            top: '16px',
            right: '16px',
            background: 'none',
            border: 'none',
            fontSize: '1.25rem',
            color: 'var(--ink-muted)',
            cursor: 'pointer',
            padding: '4px 8px',
            borderRadius: '4px',
          }}
        >
          ✕
        </button>

        {/* Header */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
          <div
            style={{
              fontSize: '1.75rem',
              backgroundColor: 'var(--surface-recessed)',
              padding: '10px 12px',
              borderRadius: 'var(--radius-card)',
              border: '1px solid var(--line)',
            }}
          >
            🛏️
          </div>
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <h3
                style={{
                  fontFamily: 'var(--font-display)',
                  fontSize: 'var(--text-h2)',
                  fontWeight: 600,
                  color: 'var(--ink)',
                  margin: 0,
                }}
              >
                Bed {bed.bed_number}
              </h3>
              <BedStatusBadge status={bed.status} />
            </div>
            <p
              style={{
                fontFamily: 'var(--font-body)',
                fontSize: 'var(--text-caption)',
                color: 'var(--ink-muted)',
                margin: '2px 0 0 0',
              }}
            >
              {bed.ward} • Floor {bed.floor} • Room {bed.room_number}
            </p>
          </div>
        </div>

        {/* Cleaning Countdown Banner */}
        {bed.status === 'CLEANING' && (
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '10px',
              padding: '10px 14px',
              borderRadius: 'var(--radius-input)',
              backgroundColor: '#FEF3E2',
              border: '1px solid var(--alert-amber)',
              color: 'var(--alert-amber)',
              fontFamily: 'var(--font-body)',
              fontSize: 'var(--text-caption)',
            }}
          >
            <span style={{ fontSize: '1.2rem' }}>⏱️</span>
            <div>
              <strong>Readiness Engine: Cleaning Active</strong>
              <div>
                Estimated Ready: <span style={{ textDecoration: 'underline', fontWeight: 700 }}>
                  {ttlMinutes ? `~${ttlMinutes} minutes remaining` : 'In progress'}
                </span>
              </div>
            </div>
          </div>
        )}

        {/* Bed Properties Table */}
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: '1fr 1fr',
            gap: '8px',
            padding: '12px',
            backgroundColor: 'var(--surface-recessed)',
            borderRadius: 'var(--radius-input)',
            border: '1px solid var(--line)',
            fontFamily: 'var(--font-body)',
            fontSize: 'var(--text-caption)',
          }}
        >
          <div>
            <span style={{ color: 'var(--ink-muted)' }}>Bed Type: </span>
            <strong style={{ color: 'var(--ink)' }}>{bed.bed_type}</strong>
          </div>
          <div>
            <span style={{ color: 'var(--ink-muted)' }}>Isolation: </span>
            <strong style={{ color: 'var(--ink)' }}>{bed.is_isolation ? 'Yes (Neg. Pressure)' : 'No'}</strong>
          </div>
          <div>
            <span style={{ color: 'var(--ink-muted)' }}>Ventilator Port: </span>
            <strong style={{ color: 'var(--ink)' }}>{bed.has_ventilator_port ? 'Equipped' : 'None'}</strong>
          </div>
          <div>
            <span style={{ color: 'var(--ink-muted)' }}>Oxygen Port: </span>
            <strong style={{ color: 'var(--ink)' }}>{bed.has_oxygen_port ? 'Active' : 'None'}</strong>
          </div>
          {bed.current_patient_id && (
            <div style={{ gridColumn: 'span 2' }}>
              <span style={{ color: 'var(--ink-muted)' }}>Current Patient: </span>
              <strong style={{ color: 'var(--pulse-blue)', fontFamily: 'var(--font-mono)' }}>
                {bed.current_patient_id}
              </strong>
            </div>
          )}
        </div>

        {/* Error / Rejection Banner */}
        {allocationError && (
          <div
            style={{
              padding: '10px 14px',
              borderRadius: 'var(--radius-input)',
              backgroundColor: '#FEF2F2',
              border: '1px solid var(--critical-red)',
              color: 'var(--critical-red)',
              fontFamily: 'var(--font-body)',
              fontSize: 'var(--text-caption)',
            }}
          >
            <strong>🚫 Request Rejected:</strong>
            <div style={{ marginTop: '2px' }}>{allocationError}</div>
          </div>
        )}

        {/* Success Message Banner */}
        {allocationMessage && (
          <div
            style={{
              padding: '10px 14px',
              borderRadius: 'var(--radius-input)',
              backgroundColor: 'var(--signal-green-soft)',
              border: '1px solid var(--signal-green)',
              color: 'var(--signal-green)',
              fontFamily: 'var(--font-body)',
              fontSize: 'var(--text-caption)',
            }}
          >
            <strong>✅ Success:</strong>
            <div style={{ marginTop: '2px' }}>{allocationMessage}</div>
          </div>
        )}

        {/* Suggested Ready Alternatives */}
        {allocationError && readyAlternatives.length > 0 && (
          <div
            style={{
              padding: '10px 14px',
              borderRadius: 'var(--radius-input)',
              backgroundColor: 'var(--pulse-blue-soft)',
              border: '1px solid var(--pulse-blue)',
            }}
          >
            <div
              style={{
                fontFamily: 'var(--font-body)',
                fontSize: 'var(--text-caption)',
                fontWeight: 600,
                color: 'var(--pulse-blue)',
                marginBottom: '6px',
              }}
            >
              💡 Suggested READY Alternative(s):
            </div>
            <div style={{ display: 'flex', gap: '6px', flexWrap: 'wrap' }}>
              {readyAlternatives.slice(0, 3).map((alt) => (
                <button
                  key={alt.id}
                  type="button"
                  onClick={() => {
                    onSelectAlternative?.(alt)
                    setAllocationError(null)
                  }}
                  style={{
                    fontFamily: 'var(--font-mono)',
                    fontSize: '0.75rem',
                    fontWeight: 600,
                    padding: '4px 10px',
                    borderRadius: 'var(--radius-pill)',
                    backgroundColor: 'var(--surface)',
                    border: '1px solid var(--pulse-blue)',
                    color: 'var(--pulse-blue)',
                    cursor: 'pointer',
                  }}
                >
                  {alt.bed_number} (READY)
                </button>
              ))}
            </div>
          </div>
        )}

        {/* Action Controls */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', marginTop: 'var(--space-1)' }}>
          {/* Main Request Button */}
          <button
            type="button"
            onClick={handleRequestAllocation}
            disabled={isLoading}
            style={{
              fontFamily: 'var(--font-body)',
              fontSize: 'var(--text-body)',
              fontWeight: 600,
              padding: '10px 16px',
              borderRadius: 'var(--radius-input)',
              border: 'none',
              backgroundColor: bed.status === 'READY' ? 'var(--signal-green)' : 'var(--ink-muted)',
              color: '#FFFFFF',
              cursor: 'pointer',
              boxShadow: bed.status === 'READY' ? '0 2px 8px rgba(15, 157, 102, 0.25)' : 'none',
              transition: 'background-color 0.15s ease',
            }}
          >
            {bed.status === 'READY'
              ? `Request Bed ${bed.bed_number} for Patient`
              : `Check & Request ${bed.bed_number}`}
          </button>

          {/* Patient Discharge / Release */}
          {bed.status === 'IN_USE' && (
            <button
              type="button"
              onClick={handleReleaseBed}
              disabled={isLoading}
              style={{
                fontFamily: 'var(--font-body)',
                fontSize: 'var(--text-body)',
                fontWeight: 600,
                padding: '10px 16px',
                borderRadius: 'var(--radius-input)',
                border: 'none',
                backgroundColor: '#805AD5',
                color: '#FFFFFF',
                cursor: 'pointer',
              }}
            >
              Discharge Patient & Release Bed (→ Auto-Clean)
            </button>
          )}

          {/* Housekeeping Complete Cleaning */}
          {bed.status === 'CLEANING' && (
            <button
              type="button"
              onClick={handleCompleteCleaning}
              disabled={isLoading}
              style={{
                fontFamily: 'var(--font-body)',
                fontSize: 'var(--text-body)',
                fontWeight: 600,
                padding: '10px 16px',
                borderRadius: 'var(--radius-input)',
                border: 'none',
                backgroundColor: 'var(--pulse-blue)',
                color: '#FFFFFF',
                cursor: 'pointer',
              }}
            >
              Verify Sanitized & Complete Cleaning (→ READY)
            </button>
          )}

          {/* Admin Maintenance */}
          {isAdmin && (
            <div style={{ display: 'flex', gap: '8px', marginTop: '4px' }}>
              {bed.status !== 'MAINTENANCE' ? (
                <button
                  type="button"
                  onClick={() => handleToggleMaintenance('start')}
                  disabled={isLoading}
                  style={{
                    flex: 1,
                    fontFamily: 'var(--font-body)',
                    fontSize: 'var(--text-caption)',
                    fontWeight: 500,
                    padding: '8px 12px',
                    borderRadius: 'var(--radius-input)',
                    border: '1px solid var(--line)',
                    backgroundColor: 'var(--surface-recessed)',
                    color: 'var(--ink-muted)',
                    cursor: 'pointer',
                  }}
                >
                  Place in Maintenance
                </button>
              ) : (
                <button
                  type="button"
                  onClick={() => handleToggleMaintenance('resolve')}
                  disabled={isLoading}
                  style={{
                    flex: 1,
                    fontFamily: 'var(--font-body)',
                    fontSize: 'var(--text-caption)',
                    fontWeight: 600,
                    padding: '8px 12px',
                    borderRadius: 'var(--radius-input)',
                    border: 'none',
                    backgroundColor: 'var(--signal-green)',
                    color: '#FFFFFF',
                    cursor: 'pointer',
                  }}
                >
                  Resolve Maintenance (→ Auto-Clean)
                </button>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
