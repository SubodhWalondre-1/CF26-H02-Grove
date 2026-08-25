import React, { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import Button from '../components/ui/Button'
import Card from '../components/ui/Card'
import EmptyState from '../components/ui/EmptyState'
import StateBadge from '../components/ui/StateBadge'
import { useRecommendationStore } from '../store/recommendationStore'

const PROCEDURE_OPTIONS = [
  { value: 'trauma_surgery', label: 'Trauma Surgery (OT + Surg + Anes + ICU Bed)' },
  { value: 'cardiac_emergency', label: 'Cardiac Emergency (OT + Surg + Anes + Vent + ICU Bed)' },
  { value: 'general_admission', label: 'General Inpatient Admission (Ward Bed)' },
  { value: 'diagnostic_only', label: 'Diagnostic Scan & Lab (CT/MRI + Lab Slot)' },
  { value: 'transfer_stabilization', label: 'Patient Transfer (Stepdown Bed + Transport)' },
]

export default function Recommendations() {
  const navigate = useNavigate()
  const { results, selectedBundles, loading, error, fetchRecommendations, selectBundle } =
    useRecommendationStore()

  // Intake Form State (supporting multi-patient mass casualty)
  const [patients, setPatients] = useState([
    {
      patient_id: 'PT-0001',
      procedure_type: 'trauma_surgery',
      acuity_score: 9.2,
      clinical_notes: 'Blunt force trauma, severe internal hemorrhage',
    },
  ])

  const handleAddPatient = () => {
    setPatients((prev) => [
      ...prev,
      {
        patient_id: `PT-${String(prev.length + 1).padStart(4, '0')}`,
        procedure_type: 'trauma_surgery',
        acuity_score: 7.5,
        clinical_notes: 'Mass casualty trauma intake',
      },
    ])
  }

  const handleRemovePatient = (index) => {
    setPatients((prev) => prev.filter((_, i) => i !== index))
  }

  const handlePatientChange = (index, field, value) => {
    setPatients((prev) => {
      const updated = [...prev]
      updated[index] = { ...updated[index], [field]: value }
      return updated
    })
  }

  const handleGenerate = async (e) => {
    e.preventDefault()
    try {
      await fetchRecommendations(patients)
    } catch (err) {
      // Handled in store
    }
  }

  const getAcuityColor = (score) => {
    const num = parseFloat(score)
    if (num >= 9.0) return { bg: '#FBE9E9', color: 'var(--critical-red)', border: '#F5C6CB' }
    if (num >= 7.0) return { bg: '#FEF3C7', color: 'var(--alert-amber)', border: '#FDE68A' }
    return { bg: 'var(--signal-green-soft)', color: 'var(--signal-green)', border: '#C3E6CB' }
  }

  const handleAcceptBundle = (patientId, bundle) => {
    // Navigate to Bundles creation page with pre-filled items
    navigate('/bundles', {
      state: {
        prefillPatientId: patientId,
        prefillResources: bundle.resources.map((r) => r.resource_id),
      },
    })
  }

  const handleModifyManually = (patientId, bundle) => {
    navigate('/bundles', {
      state: {
        prefillPatientId: patientId,
        prefillResources: bundle ? bundle.resources.map((r) => r.resource_id) : [],
        isManualEdit: true,
      },
    })
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-4)' }}>
      {/* Header */}
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
          AI Emergency Resource Recommendations
        </h1>
        <p style={{ margin: '4px 0 0', color: 'var(--ink-muted)', fontSize: 'var(--text-caption)' }}>
          Real-time advisory engine evaluating live ready resources, proximity, wait times, and conflict risk.
        </p>
      </div>

      {/* Intake / Request Builder Panel */}
      <Card style={{ padding: 'var(--space-3)' }}>
        <form onSubmit={handleGenerate} style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-3)' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <h3 style={{ margin: 0, fontSize: '1rem', color: 'var(--ink)', fontWeight: 600 }}>
              Emergency Patient Intake & Triage
            </h3>
            <Button
              type="button"
              variant="outline"
              size="small"
              onClick={handleAddPatient}
            >
              + Add Mass-Casualty Patient
            </Button>
          </div>

          {patients.map((pat, idx) => (
            <div
              key={idx}
              style={{
                display: 'grid',
                gridTemplateColumns: '140px 1fr 120px 1.5fr auto',
                gap: 'var(--space-2)',
                alignItems: 'center',
                padding: 'var(--space-2)',
                backgroundColor: 'var(--surface-sunken)',
                borderRadius: 'var(--radius-input)',
                border: '1px solid var(--line)',
              }}
            >
              {/* Patient ID */}
              <div>
                <label style={{ fontSize: '0.72rem', color: 'var(--ink-muted)', display: 'block' }}>Patient ID</label>
                <input
                  type="text"
                  required
                  value={pat.patient_id}
                  onChange={(e) => handlePatientChange(idx, 'patient_id', e.target.value)}
                  style={{
                    width: '100%',
                    padding: '6px 8px',
                    borderRadius: 'var(--radius-input)',
                    border: '1px solid var(--line)',
                    fontFamily: 'var(--font-mono)',
                    fontSize: '0.85rem',
                  }}
                />
              </div>

              {/* Procedure */}
              <div>
                <label style={{ fontSize: '0.72rem', color: 'var(--ink-muted)', display: 'block' }}>Procedure</label>
                <select
                  value={pat.procedure_type}
                  onChange={(e) => handlePatientChange(idx, 'procedure_type', e.target.value)}
                  style={{
                    width: '100%',
                    padding: '6px 8px',
                    borderRadius: 'var(--radius-input)',
                    border: '1px solid var(--line)',
                    fontSize: '0.85rem',
                  }}
                >
                  {PROCEDURE_OPTIONS.map((opt) => (
                    <option key={opt.value} value={opt.value}>
                      {opt.label}
                    </option>
                  ))}
                </select>
              </div>

              {/* Acuity */}
              <div>
                <label style={{ fontSize: '0.72rem', color: 'var(--ink-muted)', display: 'block' }}>Acuity (1-10)</label>
                <input
                  type="number"
                  step="0.1"
                  min="1.0"
                  max="10.0"
                  required
                  value={pat.acuity_score}
                  onChange={(e) => handlePatientChange(idx, 'acuity_score', parseFloat(e.target.value) || 1.0)}
                  style={{
                    width: '100%',
                    padding: '6px 8px',
                    borderRadius: 'var(--radius-input)',
                    border: '1px solid var(--line)',
                    fontWeight: 600,
                    fontSize: '0.85rem',
                  }}
                />
              </div>

              {/* Clinical Notes */}
              <div>
                <label style={{ fontSize: '0.72rem', color: 'var(--ink-muted)', display: 'block' }}>Clinical Triage Notes</label>
                <input
                  type="text"
                  placeholder="e.g. blunt trauma, chest pain, internal bleeding"
                  value={pat.clinical_notes || ''}
                  onChange={(e) => handlePatientChange(idx, 'clinical_notes', e.target.value)}
                  style={{
                    width: '100%',
                    padding: '6px 8px',
                    borderRadius: 'var(--radius-input)',
                    border: '1px solid var(--line)',
                    fontSize: '0.85rem',
                  }}
                />
              </div>

              {/* Remove button */}
              {patients.length > 1 && (
                <button
                  type="button"
                  onClick={() => handleRemovePatient(idx)}
                  style={{
                    background: 'none',
                    border: 'none',
                    color: 'var(--critical-red)',
                    cursor: 'pointer',
                    fontSize: '1.1rem',
                    padding: '4px 8px',
                  }}
                  title="Remove patient"
                >
                  ✕
                </button>
              )}
            </div>
          ))}

          {error && (
            <div style={{ padding: '8px 12px', backgroundColor: '#FBE9E9', color: 'var(--critical-red)', borderRadius: '4px', fontSize: '0.85rem' }}>
              {error}
            </div>
          )}

          <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: '4px' }}>
            <Button type="submit" variant="primary" disabled={loading}>
              {loading ? 'Evaluating Live Resource Pool...' : '⚡ Generate AI Emergency Recommendations'}
            </Button>
          </div>
        </form>
      </Card>

      {/* Recommendations Results View */}
      {results.length > 0 && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-4)' }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            <h2 style={{ fontSize: '1.25rem', margin: 0, fontWeight: 600, color: 'var(--ink)' }}>
              Ranked Resource Combinations ({results.length} Patients Evaluated)
            </h2>
            <span style={{ fontSize: '0.8rem', color: 'var(--ink-muted)', fontFamily: 'var(--font-mono)' }}>
              Sorted by Acuity (High → Low) · Greedy Non-Colliding
            </span>
          </div>

          {results.map((pRec, pIdx) => {
            const acuityStyle = getAcuityColor(pRec.acuity_score)
            const chosenBundle = selectedBundles[pRec.patient_id]

            return (
              <Card
                key={pRec.patient_id}
                style={{
                  padding: 'var(--space-3)',
                  display: 'flex',
                  flexDirection: 'column',
                  gap: 'var(--space-3)',
                  borderLeft: `4px solid ${acuityStyle.color}`,
                }}
              >
                {/* Patient Header */}
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '8px' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                    <span style={{ fontFamily: 'var(--font-mono)', fontWeight: 700, fontSize: '1.1rem', color: 'var(--ink)' }}>
                      {pRec.patient_id}
                    </span>
                    <span
                      style={{
                        padding: '2px 8px',
                        borderRadius: 'var(--radius-pill)',
                        fontSize: '0.75rem',
                        fontWeight: 700,
                        backgroundColor: acuityStyle.bg,
                        color: acuityStyle.color,
                        border: `1px solid ${acuityStyle.border}`,
                      }}
                    >
                      ACUITY {pRec.acuity_score.toFixed(1)}
                    </span>
                    <span style={{ fontSize: '0.85rem', color: 'var(--ink-muted)', textTransform: 'capitalize' }}>
                      {pRec.procedure_type.replace('_', ' ')}
                    </span>
                  </div>

                  {/* Actions */}
                  <div style={{ display: 'flex', gap: '8px' }}>
                    <Button
                      variant="outline"
                      size="small"
                      onClick={() => handleModifyManually(pRec.patient_id, chosenBundle)}
                    >
                      Modify Manually
                    </Button>
                    <Button
                      variant="primary"
                      size="small"
                      disabled={!chosenBundle}
                      onClick={() => chosenBundle && handleAcceptBundle(pRec.patient_id, chosenBundle)}
                    >
                      ✓ Accept Recommendation
                    </Button>
                  </div>
                </div>

                {/* Zero-Ready Fallback Warning State */}
                {pRec.fallback && (
                  <div
                    style={{
                      padding: '12px 16px',
                      backgroundColor: '#FEF3C7',
                      borderRadius: 'var(--radius-input)',
                      border: '1px solid #FDE68A',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'space-between',
                      gap: '16px',
                    }}
                  >
                    <div>
                      <div style={{ fontWeight: 600, color: '#92400E', fontSize: '0.9rem' }}>
                        ⚠️ No Fully Ready Resources Immediately Available
                      </div>
                      <div style={{ color: '#B45309', fontSize: '0.8rem', marginTop: '2px' }}>
                        Nearest resource turnaround estimated in ~{pRec.nearest_eta_minutes || 15} minutes.
                      </div>
                    </div>
                    <Button
                      variant="outline"
                      size="small"
                      onClick={() => handleModifyManually(pRec.patient_id, null)}
                    >
                      Proceed Manually to Request Builder
                    </Button>
                  </div>
                )}

                {/* Top 3 Bundle Cards Grid */}
                {pRec.recommendations && pRec.recommendations.length > 0 && (
                  <div
                    style={{
                      display: 'grid',
                      gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))',
                      gap: 'var(--space-2)',
                    }}
                  >
                    {pRec.recommendations.map((bundle, bIdx) => {
                      const isSelected = chosenBundle?.bundle_id === bundle.bundle_id
                      const rankLabel = bIdx === 0 ? '🏆 Option #1 (Optimal Match)' : bIdx === 1 ? 'Option #2 (Alternative)' : 'Option #3 (Backup)'

                      return (
                        <div
                          key={bundle.bundle_id}
                          onClick={() => selectBundle(pRec.patient_id, bundle)}
                          style={{
                            padding: 'var(--space-2)',
                            borderRadius: 'var(--radius-card)',
                            border: `2px solid ${isSelected ? 'var(--pulse-blue)' : 'var(--line)'}`,
                            backgroundColor: isSelected ? 'var(--pulse-blue-soft)' : 'var(--surface)',
                            cursor: 'pointer',
                            display: 'flex',
                            flexDirection: 'column',
                            gap: '8px',
                            transition: 'all 0.15s ease',
                          }}
                        >
                          {/* Bundle Rank & Header */}
                          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                            <span style={{ fontSize: '0.85rem', fontWeight: 700, color: isSelected ? 'var(--pulse-blue)' : 'var(--ink)' }}>
                              {rankLabel}
                            </span>
                            {bundle.greedy_reserved && (
                              <span
                                style={{
                                  fontSize: '0.68rem',
                                  padding: '1px 6px',
                                  borderRadius: 'var(--radius-pill)',
                                  backgroundColor: '#DCFCE7',
                                  color: '#166534',
                                  fontWeight: 600,
                                }}
                              >
                                ⚡ Reserved for Batch
                              </span>
                            )}
                          </div>

                          {/* Resources in Bundle */}
                          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '4px' }}>
                            {bundle.resources.map((r) => (
                              <span
                                key={r.resource_id}
                                style={{
                                  padding: '2px 6px',
                                  borderRadius: '4px',
                                  backgroundColor: 'var(--surface-sunken)',
                                  border: '1px solid var(--line)',
                                  fontSize: '0.75rem',
                                  fontFamily: 'var(--font-mono)',
                                  fontWeight: 600,
                                  color: 'var(--ink)',
                                }}
                              >
                                {r.label || r.resource_id}
                              </span>
                            ))}
                          </div>

                          {/* Clinical Reasoning Bullets */}
                          <div style={{ marginTop: '4px' }}>
                            <ul style={{ margin: 0, paddingLeft: '16px', fontSize: '0.75rem', color: 'var(--ink-muted)' }}>
                              {bundle.reasoning.map((reason, rIdx) => (
                                <li key={rIdx}>{reason}</li>
                              ))}
                            </ul>
                          </div>

                          {/* Bundle Score */}
                          <div
                            style={{
                              marginTop: 'auto',
                              paddingTop: '4px',
                              borderTop: '1px dashed var(--line)',
                              display: 'flex',
                              justifyContent: 'space-between',
                              fontSize: '0.72rem',
                              color: 'var(--ink-muted)',
                            }}
                          >
                            <span>Fitness Score</span>
                            <span style={{ fontFamily: 'var(--font-mono)', fontWeight: 600 }}>
                              {bundle.bundle_score.toFixed(1)} pts
                            </span>
                          </div>
                        </div>
                      )
                    })}
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
