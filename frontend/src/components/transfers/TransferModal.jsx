// frontend/src/components/transfers/TransferModal.jsx
import React, { useState, useEffect } from 'react'
import { useTransferStore } from '../../store/transferStore'
import { useBedStore } from '../../store/stores'

const TRANSFER_REASONS = [
  { key: 'ICU_STEPDOWN',          label: '📉 ICU Stepdown (Stabilized)' },
  { key: 'ESCALATION',            label: '🚨 Clinical Escalation (Deteriorating)' },
  { key: 'INFECTIOUS_ISOLATION',  label: '☣️ Infectious Isolation Room' },
  { key: 'DISCHARGE_PREP',        label: '🏠 Discharge Preparation Ward' },
  { key: 'WARD_REORGANIZATION',   label: '🔄 Ward Reorganization' },
]

export default function TransferModal({ initialBed, onClose, onTransferInitiated }) {
  const bedGrid = useBedStore((s) => s.bedGrid)
  const initiateTransfer = useTransferStore((s) => s.initiateTransfer)

  // Flatten all beds from bedGrid
  const allBeds = bedGrid.flatMap((f) => f.beds || [])
  const occupiedBeds = allBeds.filter((b) => b.status === 'IN_USE' && b.current_patient_id)
  const readyBeds = allBeds.filter((b) => b.status === 'READY')

  const [sourceBedId, setSourceBedId] = useState(
    initialBed?.status === 'IN_USE' ? initialBed.id : occupiedBeds[0]?.id || ''
  )
  const [destBedId, setDestBedId] = useState(readyBeds[0]?.id || '')
  const [needTransport, setNeedTransport] = useState(true)
  const [reason, setReason] = useState('ICU_STEPDOWN')
  const [transferType, setTransferType] = useState('INTRA_FACILITY')
  const [submitting, setSubmitting] = useState(false)
  const [errorMsg, setErrorMsg] = useState(null)

  const selectedSource = allBeds.find((b) => b.id === sourceBedId)
  const selectedDest = allBeds.find((b) => b.id === destBedId)

  const handleSubmit = async (e) => {
    e.preventDefault()
    if (!sourceBedId || !destBedId) {
      setErrorMsg('Please select both source and destination beds')
      return
    }

    if (!selectedSource?.current_patient_id) {
      setErrorMsg('Source bed has no assigned patient')
      return
    }

    setSubmitting(true)
    setErrorMsg(null)

    try {
      const payload = {
        patient_id: selectedSource.current_patient_id,
        source_bed_id: sourceBedId,
        destination_bed_id: destBedId,
        transport_resource_id: needTransport ? 'RES-TRANS-1' : null,
        transfer_type: transferType,
        reason,
        ttl_seconds: 300,
      }
      const res = await initiateTransfer(payload)
      onTransferInitiated?.(res)
      onClose?.()
    } catch (err) {
      const msg = err.response?.data?.detail?.message || err.response?.data?.detail || err.message
      setErrorMsg(typeof msg === 'string' ? msg : JSON.stringify(msg))
      setSubmitting(false)
    }
  }

  return (
    <div
      style={{
        position: 'fixed',
        inset: 0,
        backgroundColor: 'rgba(15, 23, 42, 0.65)',
        backdropFilter: 'blur(4px)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        zIndex: 9999,
        padding: 'var(--space-2)',
      }}
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose?.()
      }}
    >
      <div
        style={{
          width: '100%',
          maxWidth: '520px',
          backgroundColor: 'var(--surface)',
          borderRadius: 'var(--radius-card)',
          border: '1px solid var(--line)',
          boxShadow: '0 20px 25px -5px rgba(0, 0, 0, 0.2), 0 10px 10px -5px rgba(0, 0, 0, 0.04)',
          overflow: 'hidden',
          display: 'flex',
          flexDirection: 'column',
        }}
      >
        {/* Modal Header */}
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            padding: '16px 20px',
            borderBottom: '1px solid var(--line)',
            backgroundColor: 'var(--surface-recessed)',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <span style={{ fontSize: '1.3rem' }}>🔀</span>
            <div>
              <h3
                style={{
                  fontFamily: 'var(--font-display)',
                  fontSize: 'var(--text-h3)',
                  fontWeight: 600,
                  color: 'var(--ink)',
                  margin: 0,
                }}
              >
                Initiate Patient Transfer
              </h3>
              <p
                style={{
                  fontFamily: 'var(--font-body)',
                  fontSize: '0.72rem',
                  color: 'var(--ink-muted)',
                  margin: 0,
                }}
              >
                Release source bed + acquire transport & destination bed atomically
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            style={{
              background: 'none',
              border: 'none',
              fontSize: '1.2rem',
              color: 'var(--ink-muted)',
              cursor: 'pointer',
              padding: '4px 8px',
            }}
          >
            ✕
          </button>
        </div>

        {/* Modal Body / Form */}
        <form onSubmit={handleSubmit} style={{ padding: '20px', display: 'flex', flexDirection: 'column', gap: '14px' }}>
          {errorMsg && (
            <div
              style={{
                padding: '10px 14px',
                borderRadius: 'var(--radius-input)',
                backgroundColor: '#FEF2F2',
                border: '1px solid #FECACA',
                color: 'var(--critical-red)',
                fontFamily: 'var(--font-body)',
                fontSize: '0.78rem',
              }}
            >
              ⚠️ {errorMsg}
            </div>
          )}

          {/* Source Bed Selection */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
            <label
              style={{
                fontFamily: 'var(--font-body)',
                fontSize: '0.75rem',
                fontWeight: 600,
                color: 'var(--ink)',
              }}
            >
              1. Source Bed (Currently Occupied)
            </label>
            <select
              value={sourceBedId}
              onChange={(e) => setSourceBedId(e.target.value)}
              style={{
                fontFamily: 'var(--font-body)',
                fontSize: 'var(--text-caption)',
                padding: '8px 12px',
                borderRadius: 'var(--radius-input)',
                border: '1px solid var(--line)',
                backgroundColor: 'var(--surface)',
                color: 'var(--ink)',
              }}
            >
              {occupiedBeds.length === 0 ? (
                <option value="">No occupied beds available</option>
              ) : (
                occupiedBeds.map((b) => (
                  <option key={b.id} value={b.id}>
                    {b.bed_number} ({b.bed_type}) — Patient: {b.current_patient_id} ({b.ward})
                  </option>
                ))
              )}
            </select>
          </div>

          {/* Destination Bed Selection */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
            <label
              style={{
                fontFamily: 'var(--font-body)',
                fontSize: '0.75rem',
                fontWeight: 600,
                color: 'var(--ink)',
              }}
            >
              2. Destination Bed (Must be READY)
            </label>
            <select
              value={destBedId}
              onChange={(e) => setDestBedId(e.target.value)}
              style={{
                fontFamily: 'var(--font-body)',
                fontSize: 'var(--text-caption)',
                padding: '8px 12px',
                borderRadius: 'var(--radius-input)',
                border: '1px solid var(--line)',
                backgroundColor: 'var(--surface)',
                color: 'var(--ink)',
              }}
            >
              {readyBeds.length === 0 ? (
                <option value="">No READY beds available</option>
              ) : (
                readyBeds.map((b) => (
                  <option key={b.id} value={b.id}>
                    {b.bed_number} ({b.bed_type}) — {b.ward}, Floor {b.floor} (READY)
                  </option>
                ))
              )}
            </select>
          </div>

          {/* Transfer Reason */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
            <label
              style={{
                fontFamily: 'var(--font-body)',
                fontSize: '0.75rem',
                fontWeight: 600,
                color: 'var(--ink)',
              }}
            >
              3. Clinical Transfer Reason
            </label>
            <select
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              style={{
                fontFamily: 'var(--font-body)',
                fontSize: 'var(--text-caption)',
                padding: '8px 12px',
                borderRadius: 'var(--radius-input)',
                border: '1px solid var(--line)',
                backgroundColor: 'var(--surface)',
                color: 'var(--ink)',
              }}
            >
              {TRANSFER_REASONS.map((r) => (
                <option key={r.key} value={r.key}>
                  {r.label}
                </option>
              ))}
            </select>
          </div>

          {/* Transport Checkbox */}
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              padding: '10px 12px',
              borderRadius: 'var(--radius-input)',
              backgroundColor: 'var(--surface-recessed)',
              border: '1px solid var(--line)',
            }}
          >
            <div>
              <span style={{ fontFamily: 'var(--font-body)', fontSize: '0.78rem', fontWeight: 600, color: 'var(--ink)' }}>
                🚑 Assign Transport Unit (Gurney / Wheelchair)
              </span>
              <p style={{ fontFamily: 'var(--font-body)', fontSize: '0.68rem', color: 'var(--ink-muted)', margin: 0 }}>
                Locks a dedicated internal transport escort resource during transit
              </p>
            </div>
            <input
              type="checkbox"
              checked={needTransport}
              onChange={(e) => setNeedTransport(e.target.checked)}
              style={{ width: '18px', height: '18px', cursor: 'pointer' }}
            />
          </div>

          {/* Notice & Invariant */}
          <div
            style={{
              padding: '8px 12px',
              borderRadius: 'var(--radius-input)',
              backgroundColor: 'var(--signal-green-soft)',
              border: '1px solid #A7F3D0',
              fontFamily: 'var(--font-body)',
              fontSize: '0.7rem',
              color: '#065F46',
            }}
          >
            🛡️ <strong>Safety Invariant:</strong> Destination bed is held for <strong>5 minutes (300s TTL)</strong>. If transfer aborts mid-flight, source bed is guaranteed to re-attach the patient to prevent homelessness.
          </div>

          {/* Action Buttons */}
          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '8px', marginTop: '4px' }}>
            <button
              type="button"
              onClick={onClose}
              style={{
                fontFamily: 'var(--font-body)',
                fontSize: 'var(--text-caption)',
                fontWeight: 500,
                padding: '8px 16px',
                borderRadius: 'var(--radius-input)',
                border: '1px solid var(--line)',
                backgroundColor: 'transparent',
                color: 'var(--ink-muted)',
                cursor: 'pointer',
              }}
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={submitting || !sourceBedId || !destBedId}
              style={{
                fontFamily: 'var(--font-body)',
                fontSize: 'var(--text-caption)',
                fontWeight: 600,
                padding: '8px 20px',
                borderRadius: 'var(--radius-input)',
                border: 'none',
                backgroundColor: 'var(--pulse-blue)',
                color: '#FFFFFF',
                cursor: submitting ? 'not-allowed' : 'pointer',
                opacity: submitting ? 0.7 : 1,
              }}
            >
              {submitting ? 'Initiating...' : 'Initiate Transfer'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}
