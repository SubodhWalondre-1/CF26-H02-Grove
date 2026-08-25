import React, { useEffect, useState } from 'react'
import Button from '../components/ui/Button'
import Card from '../components/ui/Card'
import EmptyState from '../components/ui/EmptyState'
import StateBadge from '../components/ui/StateBadge'
import Table from '../components/ui/Table'
import {
  getAdminConfig,
  getIncompleteTransactions,
  getPolicies,
  updateAdminConfig,
  updatePolicies,
} from '../lib/api'
import { useAuthStore } from '../store/authStore'

export default function Admin() {
  const user = useAuthStore((state) => state.user)

  const [config, setConfig] = useState({
    hold_ttl_seconds: 30,
    wait_coefficient_per_min: 0.1,
    acuity_override_threshold: 9.5,
    override_frequency_flag_limit: 3,
  })
  const [policies, setPolicies] = useState([])
  const [incompleteTxs, setIncompleteTxs] = useState([])
  const [overrideEvents, setOverrideEvents] = useState([])
  const [filterFlaggedOnly, setFilterFlaggedOnly] = useState(false)

  const [isSavingConfig, setIsSavingConfig] = useState(false)
  const [saveConfigSuccess, setSaveConfigSuccess] = useState(false)
  const [configError, setConfigError] = useState('')

  const [isEditingPolicies, setIsEditingPolicies] = useState(false)
  const [isSavingPolicies, setIsSavingPolicies] = useState(false)
  const [savePolicySuccess, setSavePolicySuccess] = useState(false)
  const [policyError, setPolicyError] = useState('')

  useEffect(() => {
    if (user?.role === 'admin') {
      getAdminConfig()
        .then((res) => {
          if (res.data) setConfig(res.data)
        })
        .catch((err) => console.warn('Failed to load admin config:', err))

      getPolicies()
        .then((res) => {
          if (res.data) {
            const rawPolicies = Array.isArray(res.data) ? res.data : res.data.policies || []
            setPolicies(rawPolicies)
          }
        })
        .catch((err) => console.warn('Failed to load policies:', err))

      getIncompleteTransactions()
        .then((res) => {
          if (res.data && res.data.items) setIncompleteTxs(res.data.items)
        })
        .catch((err) => console.warn('Failed to load incomplete txs:', err))

      api.get('/admin/overrides')
        .then((res) => {
          if (res.data && res.data.items) setOverrideEvents(res.data.items)
        })
        .catch((err) => console.warn('Failed to load override events:', err))
    }
  }, [user])

  // Admin Role Guard
  if (user?.role !== 'admin') {
    return (
      <EmptyState message="Admin access required. You don't have permission to view this page." />
    )
  }

  const handleSaveConfig = async () => {
    setIsSavingConfig(true)
    setSaveConfigSuccess(false)
    setConfigError('')
    try {
      const res = await updateAdminConfig({
        hold_ttl_seconds: Number(config.hold_ttl_seconds),
        wait_coefficient_per_min: Number(config.wait_coefficient_per_min),
        acuity_override_threshold: Number(config.acuity_override_threshold || 9.5),
        override_frequency_flag_limit: Number(config.override_frequency_flag_limit || 3),
      })
      setConfig(res.data)
      setSaveConfigSuccess(true)
      setTimeout(() => setSaveConfigSuccess(false), 4000)
    } catch (err) {
      setConfigError(err.response?.data?.detail || 'Failed to update system configuration')
    } finally {
      setIsSavingConfig(false)
    }
  }

  const handleSavePolicies = async () => {
    setIsSavingPolicies(true)
    setSavePolicySuccess(false)
    setPolicyError('')
    try {
      const res = await updatePolicies(policies)
      const updated = Array.isArray(res.data) ? res.data : res.data.policies || []
      setPolicies(updated)
      setIsEditingPolicies(false)
      setSavePolicySuccess(true)
      setTimeout(() => setSavePolicySuccess(false), 4000)
    } catch (err) {
      setPolicyError(err.response?.data?.detail || 'Failed to update policies')
    } finally {
      setIsSavingPolicies(false)
    }
  }

  const handlePolicyChange = (index, field, value) => {
    setPolicies((prev) => {
      const copy = [...prev]
      copy[index] = { ...copy[index], [field]: value }
      return copy
    })
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-4)' }}>
      {/* Page Header */}
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
          System Administration
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
          Dynamic runtime controls, RBAC permission policies, and crash-recovery engine monitors.
        </p>
      </div>

      {/* Section 1: System Configuration */}
      <Card title="System Configuration">
        <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-3)' }}>
          {/* Hold TTL */}
          <div>
            <label
              style={{
                fontFamily: 'var(--font-body)',
                fontWeight: 600,
                display: 'block',
                marginBottom: '4px',
                fontSize: 'var(--text-body)',
              }}
            >
              Hold TTL (seconds)
            </label>
            <p
              style={{
                fontSize: 'var(--text-caption)',
                color: 'var(--ink-muted)',
                marginBottom: '8px',
              }}
            >
              Time allowed for a care bundle prepare phase before automatic rollback. Not a fixed
              clinical constant — adjust based on observed transaction latency.
            </p>
            <input
              type="number"
              min="5"
              max="300"
              value={config.hold_ttl_seconds || 30}
              onChange={(e) => setConfig((c) => ({ ...c, hold_ttl_seconds: +e.target.value }))}
              style={{
                width: '140px',
                padding: '8px 12px',
                border: '1px solid var(--line)',
                borderRadius: 'var(--radius-input)',
                fontFamily: 'var(--font-mono)',
                fontSize: 'var(--text-body)',
                backgroundColor: 'var(--surface)',
                color: 'var(--ink)',
              }}
            />
          </div>

          {/* Wait Coefficient */}
          <div>
            <label
              style={{
                fontFamily: 'var(--font-body)',
                fontWeight: 600,
                display: 'block',
                marginBottom: '4px',
                fontSize: 'var(--text-body)',
              }}
            >
              Wait Coefficient (per minute)
            </label>
            <p
              style={{
                fontSize: 'var(--text-caption)',
                color: 'var(--ink-muted)',
                marginBottom: '8px',
              }}
            >
              Fairness coefficient in clinical arbitration — increases effective score for
              longer-waiting transactions.
            </p>
            <input
              type="number"
              min="0"
              max="1"
              step="0.01"
              value={config.wait_coefficient_per_min != null ? config.wait_coefficient_per_min : 0.1}
              onChange={(e) =>
                setConfig((c) => ({ ...c, wait_coefficient_per_min: +e.target.value }))
              }
              style={{
                width: '140px',
                padding: '8px 12px',
                border: '1px solid var(--line)',
                borderRadius: 'var(--radius-input)',
                fontFamily: 'var(--font-mono)',
                fontSize: 'var(--text-body)',
                backgroundColor: 'var(--surface)',
                color: 'var(--ink)',
              }}
            />
          </div>

          {/* Override Acuity Threshold */}
          <div>
            <label
              style={{
                fontFamily: 'var(--font-body)',
                fontWeight: 600,
                display: 'block',
                marginBottom: '4px',
                fontSize: 'var(--text-body)',
              }}
            >
              Emergency Override Acuity Threshold
            </label>
            <p
              style={{
                fontSize: 'var(--text-caption)',
                color: 'var(--ink-muted)',
                marginBottom: '8px',
              }}
            >
              Automatic bypass threshold — transactions for patients with acuity &ge; this score skip normal arbitration.
            </p>
            <input
              type="number"
              min="1"
              max="10"
              step="0.1"
              value={config.acuity_override_threshold != null ? config.acuity_override_threshold : 9.5}
              onChange={(e) =>
                setConfig((c) => ({ ...c, acuity_override_threshold: +e.target.value }))
              }
              style={{
                width: '140px',
                padding: '8px 12px',
                border: '1px solid var(--line)',
                borderRadius: 'var(--radius-input)',
                fontFamily: 'var(--font-mono)',
                fontSize: 'var(--text-body)',
                backgroundColor: 'var(--surface)',
                color: 'var(--ink)',
              }}
            />
          </div>

          {/* Override Frequency Limit */}
          <div>
            <label
              style={{
                fontFamily: 'var(--font-body)',
                fontWeight: 600,
                display: 'block',
                marginBottom: '4px',
                fontSize: 'var(--text-body)',
              }}
            >
              Manual Override 24h Frequency Limit
            </label>
            <p
              style={{
                fontSize: 'var(--text-caption)',
                color: 'var(--ink-muted)',
                marginBottom: '8px',
              }}
            >
              Governance safeguard — manual declarations exceeding this count in 24 hours are flagged for retrospective review.
            </p>
            <input
              type="number"
              min="1"
              max="20"
              value={config.override_frequency_flag_limit != null ? config.override_frequency_flag_limit : 3}
              onChange={(e) =>
                setConfig((c) => ({ ...c, override_frequency_flag_limit: +e.target.value }))
              }
              style={{
                width: '140px',
                padding: '8px 12px',
                border: '1px solid var(--line)',
                borderRadius: 'var(--radius-input)',
                fontFamily: 'var(--font-mono)',
                fontSize: 'var(--text-body)',
                backgroundColor: 'var(--surface)',
                color: 'var(--ink)',
              }}
            />
          </div>

          {configError && (
            <p style={{ color: 'var(--critical-red)', fontSize: 'var(--text-caption)', margin: 0 }}>
              {configError}
            </p>
          )}

          {/* Save Configuration Button */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-2)' }}>
            <Button
              variant="primary"
              onClick={handleSaveConfig}
              disabled={isSavingConfig}
            >
              {isSavingConfig ? 'Saving...' : 'Save Configuration'}
            </Button>
            {saveConfigSuccess && (
              <span
                style={{
                  color: 'var(--signal-green)',
                  fontSize: 'var(--text-caption)',
                  fontWeight: 600,
                  fontFamily: 'var(--font-body)',
                }}
              >
                ✓ Configuration updated successfully.
              </span>
            )}
          </div>
        </div>
      </Card>

      {/* Section 2: Policy Matrix */}
      <Card title="Role Policy Matrix">
        <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-3)' }}>
          <div
            style={{
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
            }}
          >
            <p
              style={{
                fontSize: 'var(--text-caption)',
                color: 'var(--ink-muted)',
                margin: 0,
              }}
            >
              Policy changes take effect immediately. Role capabilities are re-evaluated on the next
              authenticated request.
            </p>

            <div style={{ display: 'flex', gap: '8px' }}>
              <Button
                variant="secondary"
                size="sm"
                onClick={() => setIsEditingPolicies(!isEditingPolicies)}
              >
                {isEditingPolicies ? 'Cancel Edit' : 'Edit Policies'}
              </Button>
              {isEditingPolicies && (
                <Button
                  variant="primary"
                  size="sm"
                  onClick={handleSavePolicies}
                  disabled={isSavingPolicies}
                >
                  {isSavingPolicies ? 'Saving...' : 'Save Policies'}
                </Button>
              )}
            </div>
          </div>

          {policyError && (
            <p style={{ color: 'var(--critical-red)', fontSize: 'var(--text-caption)', margin: 0 }}>
              {policyError}
            </p>
          )}
          {savePolicySuccess && (
            <p style={{ color: 'var(--signal-green)', fontSize: 'var(--text-caption)', margin: 0 }}>
              ✓ Policies updated successfully.
            </p>
          )}

          {/* Policy Table */}
          <div
            style={{
              overflowX: 'auto',
              borderRadius: 'var(--radius-input)',
              border: '1px solid var(--line)',
              backgroundColor: 'var(--surface)',
            }}
          >
            <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left' }}>
              <thead>
                <tr
                  style={{
                    backgroundColor: 'var(--surface-recessed)',
                    borderBottom: '1px solid var(--line)',
                  }}
                >
                  <th style={{ padding: '10px 14px', fontSize: 'var(--text-caption)', color: 'var(--ink-muted)' }}>ROLE</th>
                  <th style={{ padding: '10px 14px', fontSize: 'var(--text-caption)', color: 'var(--ink-muted)' }}>ACTION</th>
                  <th style={{ padding: '10px 14px', fontSize: 'var(--text-caption)', color: 'var(--ink-muted)' }}>RESOURCE TYPE</th>
                  <th style={{ padding: '10px 14px', fontSize: 'var(--text-caption)', color: 'var(--ink-muted)' }}>PERMISSION RULE</th>
                </tr>
              </thead>
              <tbody>
                {policies.length === 0 ? (
                  <tr>
                    <td colSpan={4} style={{ padding: '16px', textAlign: 'center', color: 'var(--ink-muted)' }}>
                      No policy records found.
                    </td>
                  </tr>
                ) : (
                  policies.map((p, idx) => (
                    <tr
                      key={p.policy_id || idx}
                      style={{
                        backgroundColor: idx % 2 === 0 ? 'var(--surface)' : 'var(--surface-recessed)',
                        borderBottom: '1px solid var(--line)',
                      }}
                    >
                      <td style={{ padding: '10px 14px', fontWeight: 600, textTransform: 'capitalize' }}>
                        {p.role}
                      </td>
                      <td style={{ padding: '10px 14px', fontFamily: 'var(--font-mono)', fontSize: '0.875rem' }}>
                        {p.action}
                      </td>
                      <td style={{ padding: '10px 14px', fontFamily: 'var(--font-mono)', fontSize: '0.875rem' }}>
                        {p.resource_type || '*'}
                      </td>
                      <td style={{ padding: '10px 14px' }}>
                        {isEditingPolicies ? (
                          <input
                            type="text"
                            value={p.permission_rule || ''}
                            onChange={(e) => handlePolicyChange(idx, 'permission_rule', e.target.value)}
                            style={{
                              padding: '4px 8px',
                              borderRadius: 'var(--radius-input)',
                              border: '1px solid var(--line)',
                              fontFamily: 'var(--font-mono)',
                              fontSize: '0.8125rem',
                              width: '100%',
                            }}
                          />
                        ) : (
                          <span
                            style={{
                              fontFamily: 'var(--font-mono)',
                              fontSize: '0.8125rem',
                              color: p.permission_rule === 'allow' ? 'var(--signal-green)' : 'var(--ink)',
                              fontWeight: 500,
                            }}
                          >
                            {p.permission_rule || 'allow'}
                          </span>
                        )}
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>
      </Card>

      {/* Section 3: Recovery Status */}
      <Card title="Recovery Status">
        <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-2)' }}>
          <p
            style={{
              fontSize: 'var(--text-caption)',
              color: 'var(--ink-muted)',
              margin: 0,
            }}
          >
            Transactions found in incomplete states after a server restart. The recovery engine resolves
            these automatically via Celery scans.
          </p>

          <Table
            columns={[
              { key: 'tx_id', label: 'TX ID', mono: true },
              {
                key: 'state',
                label: 'State',
                render: (row) => <StateBadge status={row.state} />,
              },
              {
                key: 'ttl_expired',
                label: 'TTL Expired',
                render: (row) => (row.ttl_expired ? 'Yes (Expired)' : 'No'),
              },
            ]}
            rows={incompleteTxs}
            emptyMessage="No incomplete transactions. Recovery engine is idle."
          />
        </div>
      </Card>

      {/* Section 4: Emergency Override Governance & Auditing */}
      <Card title="🚨 Emergency Override Governance & Retrospective Audit">
        <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-3)' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <p
              style={{
                fontSize: 'var(--text-caption)',
                color: 'var(--ink-muted)',
                margin: 0,
              }}
            >
              Audited log of automatic and manual override events. Anomalous frequency or acuity mismatches are flagged for review.
            </p>
            <label style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: 'var(--text-caption)', color: 'var(--ink)' }}>
              <input
                type="checkbox"
                checked={filterFlaggedOnly}
                onChange={(e) => setFilterFlaggedOnly(e.target.checked)}
              />
              Show Flagged Anomalies Only
            </label>
          </div>

          <Table
            columns={[
              { key: 'tx_id', label: 'TX ID', mono: true },
              { key: 'patient_id', label: 'Patient', mono: true },
              {
                key: 'trigger_type',
                label: 'Trigger',
                render: (row) => (
                  <span
                    style={{
                      padding: '2px 8px',
                      borderRadius: '4px',
                      fontSize: '0.75rem',
                      fontWeight: 600,
                      backgroundColor: row.trigger_type === 'AUTOMATIC' ? 'rgba(59, 130, 246, 0.15)' : 'rgba(245, 158, 11, 0.15)',
                      color: row.trigger_type === 'AUTOMATIC' ? '#2563EB' : '#D97706',
                    }}
                  >
                    {row.trigger_type}
                  </span>
                ),
              },
              {
                key: 'acuity_score_at_trigger',
                label: 'Acuity',
                mono: true,
                render: (row) => Number(row.acuity_score_at_trigger).toFixed(1),
              },
              {
                key: 'latency_ms',
                label: 'Latency',
                mono: true,
                render: (row) => `${row.latency_ms || '<50'}ms`,
              },
              {
                key: 'requested_by',
                label: 'Staff',
                mono: true,
              },
              {
                key: 'flagged_for_review',
                label: 'Governance Status',
                render: (row) => (
                  row.flagged_for_review ? (
                    <span
                      style={{
                        padding: '2px 8px',
                        borderRadius: '4px',
                        fontSize: '0.75rem',
                        fontWeight: 700,
                        backgroundColor: 'rgba(239, 68, 68, 0.15)',
                        color: '#DC2626',
                        border: '1px solid rgba(239, 68, 68, 0.3)',
                      }}
                    >
                      ⚠️ FLAGGED ({row.flag_reason || 'REVIEW'})
                    </span>
                  ) : (
                    <span style={{ color: 'var(--signal-green)', fontSize: '0.8rem', fontWeight: 600 }}>
                      ✓ Cleared
                    </span>
                  )
                ),
              },
            ]}
            rows={
              filterFlaggedOnly
                ? overrideEvents.filter((e) => e.flagged_for_review)
                : overrideEvents
            }
            emptyMessage="No emergency override events recorded."
          />
        </div>
      </Card>
    </div>
  )
}
