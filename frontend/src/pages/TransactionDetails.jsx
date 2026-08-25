import React, { useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import Button from '../components/ui/Button'
import Card from '../components/ui/Card'
import StateBadge from '../components/ui/StateBadge'
import TTLRing from '../components/ui/TTLRing'
import { downloadRecordPdf, getCompensationStatus, getRecordStatus, regenerateRecord } from '../lib/api'
import { useAuthStore } from '../store/authStore'
import { useTransactionStore } from '../store/transactionStore'

export default function TransactionDetails() {
  const { txId } = useParams()
  const navigate = useNavigate()

  const currentTx = useTransactionStore((state) => state.currentTx)
  const stateHistory = useTransactionStore((state) => state.stateHistory)
  const fetchTransaction = useTransactionStore((state) => state.fetchTransaction)
  const fetchStateHistory = useTransactionStore((state) => state.fetchStateHistory)
  const cancelTransaction = useTransactionStore((state) => state.cancelTransaction)
  const completeTransaction = useTransactionStore((state) => state.completeTransaction)

  const [compensationData, setCompensationData] = useState(null)
  const [isProcessing, setIsProcessing] = useState(false)
  const [actionError, setActionError] = useState('')
  const [recordStatus, setRecordStatus] = useState(null)
  const [isDownloadingPdf, setIsDownloadingPdf] = useState(false)

  const user = useAuthStore((state) => state.user)
  const isAdmin = user?.role === 'admin'

  useEffect(() => {
    if (txId) {
      fetchTransaction(txId).catch(() => {})
      fetchStateHistory(txId).catch(() => {})
    }
  }, [txId, fetchTransaction, fetchStateHistory])

  // Poll record status if closed/completed/cancelled
  useEffect(() => {
    let intervalId
    if (currentTx && ['CLOSED', 'COMPLETED', 'CANCELLED'].includes((currentTx.status || '').toUpperCase())) {
      const pollStatus = () => {
        getRecordStatus(txId)
          .then((res) => setRecordStatus(res.data))
          .catch(() => {})
      }
      pollStatus()
      intervalId = setInterval(pollStatus, 4000)
    }
    return () => {
      if (intervalId) clearInterval(intervalId)
    }
  }, [currentTx, txId])

  const handleDownloadPdf = async () => {
    setIsDownloadingPdf(true)
    try {
      const res = await downloadRecordPdf(txId)
      const blob = new Blob([res.data], { type: 'application/pdf' })
      const url = window.URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url
      link.setAttribute('download', `operation-record-${txId}.pdf`)
      document.body.appendChild(link)
      link.click()
      link.remove()
      window.URL.revokeObjectURL(url)
    } catch (err) {
      alert(err.response?.data?.detail || 'Failed to download operation record PDF')
    } finally {
      setIsDownloadingPdf(false)
    }
  }

  const handleRetryRegenerate = async () => {
    try {
      await regenerateRecord(txId)
      setRecordStatus((prev) => ({ ...prev, status: 'PENDING' }))
    } catch (err) {
      alert(err.response?.data?.detail || 'Failed to trigger regeneration')
    }
  }

  // Fetch saga compensation data if transaction is cancelled
  useEffect(() => {
    if (currentTx && currentTx.status === 'CANCELLED') {
      getCompensationStatus(txId)
        .then((res) => setCompensationData(res.data))
        .catch(() => setCompensationData(null))
    }
  }, [currentTx, txId])

  if (!currentTx) {
    return (
      <div style={{ padding: 'var(--space-4)', color: 'var(--ink-muted)', textAlign: 'center' }}>
        Loading transaction {txId}...
      </div>
    )
  }

  const status = (currentTx.status || '').toUpperCase()
  const isPreparing = status === 'PREPARING'
  const isActive = status === 'ACTIVE'
  const isCareBundle = currentTx.request_type === 'care_bundle'

  const handleComplete = async () => {
    setActionError('')
    setIsProcessing(true)
    try {
      await completeTransaction(txId)
    } catch (err) {
      setActionError(err.message || 'Failed to complete transaction')
    } finally {
      setIsProcessing(false)
    }
  }

  const handleCancel = async () => {
    const reason = window.prompt('Enter reason for cancelling this transaction:', 'Clinical priority change')
    if (reason === null) return // cancelled prompt

    setActionError('')
    setIsProcessing(true)
    try {
      await cancelTransaction(txId, reason || 'User cancellation')
    } catch (err) {
      setActionError(err.message || 'Failed to cancel transaction')
    } finally {
      setIsProcessing(false)
    }
  }

  const formatDate = (isoStr) => {
    if (!isoStr) return '—'
    try {
      const d = new Date(isoStr)
      return `${d.toLocaleDateString()} ${d.toLocaleTimeString()}`
    } catch {
      return isoStr
    }
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-4)' }}>
      {/* 1. Top Header Row with Actions */}
      <div
        style={{
          display: 'flex',
          flexWrap: 'wrap',
          alignItems: 'center',
          justifyContent: 'space-between',
          gap: 'var(--space-3)',
          borderBottom: '1px solid var(--line)',
          paddingBottom: 'var(--space-3)',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-2)' }}>
          <StateBadge status={status} />
          <h1
            style={{
              fontFamily: 'var(--font-mono)',
              fontSize: 'var(--text-h2)',
              fontWeight: 600,
              color: 'var(--ink)',
              margin: 0,
            }}
          >
            {currentTx.tx_id}
          </h1>
        </div>

        {/* Status Actions */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-2)' }}>
          {isActive && (
            <Button
              variant="primary"
              disabled={isProcessing}
              onClick={handleComplete}
            >
              {isProcessing ? 'Completing...' : 'Complete Care'}
            </Button>
          )}

          {(isActive || isPreparing) && (
            <Button
              variant="destructive"
              disabled={isProcessing}
              onClick={handleCancel}
            >
              {isProcessing ? 'Cancelling...' : 'Cancel Request'}
            </Button>
          )}

          {/* Download Operation Record PDF Button */}
          {['CLOSED', 'COMPLETED', 'CANCELLED'].includes(status) && (
            <>
              {recordStatus?.status === 'GENERATED' && (
                <Button
                  variant="primary"
                  disabled={isDownloadingPdf}
                  onClick={handleDownloadPdf}
                  style={{ backgroundColor: '#1E3A8A' }}
                >
                  {isDownloadingPdf ? 'Downloading...' : '📄 Download Report (PDF)'}
                </Button>
              )}

              {(!recordStatus || recordStatus.status === 'PENDING') && (
                <Button variant="outline" disabled>
                  ⏳ Generating Record...
                </Button>
              )}

              {recordStatus?.status === 'FAILED' && (
                <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                  <span style={{ fontSize: '0.75rem', color: 'var(--critical-red)', fontWeight: 600 }}>
                    ⚠️ PDF Generation Failed
                  </span>
                  {isAdmin && (
                    <Button variant="outline" size="small" onClick={handleRetryRegenerate}>
                      Retry
                    </Button>
                  )}
                </div>
              )}
            </>
          )}

          <Button variant="secondary" onClick={() => navigate('/transactions')}>
            Back to List
          </Button>
        </div>
      </div>

      {actionError && (
        <div
          role="alert"
          style={{
            padding: '10px 14px',
            backgroundColor: '#FBE9E9',
            border: '1px solid var(--critical-red)',
            borderRadius: 'var(--radius-input)',
            color: 'var(--critical-red)',
            fontSize: 'var(--text-caption)',
            fontFamily: 'var(--font-body)',
          }}
        >
          {actionError}
        </div>
      )}

      {/* 2. Metadata Cards (2-Column Grid) */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))',
          gap: 'var(--space-3)',
        }}
      >
        {/* Left Card: Transaction Details */}
        <Card title="Transaction Information">
          <div style={{ display: 'flex', flexDirection: 'column', gap: '10px', fontSize: 'var(--text-body)' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between' }}>
              <span style={{ color: 'var(--ink-muted)' }}>Patient ID</span>
              <span style={{ fontFamily: 'var(--font-mono)', fontWeight: 500 }}>
                {currentTx.patient_id || '—'}
              </span>
            </div>

            <div style={{ display: 'flex', justifyContent: 'space-between' }}>
              <span style={{ color: 'var(--ink-muted)' }}>Request Type</span>
              <span>{isCareBundle ? 'Care Bundle (2PC)' : 'Single Resource'}</span>
            </div>

            <div style={{ display: 'flex', justifyContent: 'space-between' }}>
              <span style={{ color: 'var(--ink-muted)' }}>Conflict</span>
              {currentTx.conflict_id ? (
                <Link
                  to="/conflicts"
                  style={{
                    fontFamily: 'var(--font-mono)',
                    color: 'var(--pulse-blue)',
                    textDecoration: 'none',
                    fontWeight: 500,
                  }}
                >
                  {currentTx.conflict_id} →
                </Link>
              ) : (
                <span style={{ color: 'var(--ink-muted)' }}>None</span>
              )}
            </div>

            <div style={{ display: 'flex', justifyContent: 'space-between' }}>
              <span style={{ color: 'var(--ink-muted)' }}>Created At</span>
              <span style={{ fontFamily: 'var(--font-mono)', fontSize: 'var(--text-caption)' }}>
                {formatDate(currentTx.created_at)}
              </span>
            </div>
          </div>
        </Card>

        {/* Right Card: TTL / Hold Status */}
        <Card title="Hold TTL Status">
          <div
            style={{
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'center',
              justifyContent: 'center',
              minHeight: '130px',
              gap: '10px',
            }}
          >
            {isPreparing && currentTx.hold_remaining_seconds != null ? (
              <>
                <TTLRing
                  totalSeconds={currentTx.hold_ttl_seconds || 30}
                  remainingSeconds={currentTx.hold_remaining_seconds}
                />
                <span
                  style={{
                    fontFamily: 'var(--font-body)',
                    fontSize: 'var(--text-caption)',
                    color: 'var(--ink-muted)',
                  }}
                >
                  Automatic 2PC rollback if not committed before expiration
                </span>
              </>
            ) : (
              <span style={{ color: 'var(--ink-muted)', fontFamily: 'var(--font-body)' }}>
                {status === 'ACTIVE'
                  ? 'All holds confirmed committed'
                  : 'No active TTL timer in current state'}
              </span>
            )}
          </div>
        </Card>
      </div>

      {/* 3. Resources Panel (for Care Bundles or Transactions with Resources) */}
      {(isCareBundle || (currentTx.resources && currentTx.resources.length > 0)) && (
        <Card title="Bundle Resources">
          <div style={{ display: 'flex', flexDirection: 'column' }}>
            {(currentTx.resources || []).map((resourceId) => (
              <div
                key={resourceId}
                style={{
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                  padding: '10px 0',
                  borderBottom: '1px solid var(--line)',
                }}
              >
                <span
                  style={{
                    fontFamily: 'var(--font-mono)',
                    fontSize: 'var(--text-body)',
                    fontWeight: 500,
                  }}
                >
                  {resourceId}
                </span>
                <span
                  style={{
                    fontFamily: 'var(--font-body)',
                    fontSize: 'var(--text-caption)',
                    color: 'var(--signal-green)',
                    fontWeight: 500,
                  }}
                >
                  Confirmed
                </span>
              </div>
            ))}
          </div>
        </Card>
      )}

      {/* 4. State History Timeline */}
      <Card title="State Timeline">
        {stateHistory.length === 0 ? (
          <div style={{ color: 'var(--ink-muted)', padding: '8px 0' }}>No state transitions recorded.</div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column' }}>
            {stateHistory.map((entry, index) => (
              <div
                key={index}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  padding: '10px 0',
                  borderBottom:
                    index === stateHistory.length - 1 ? 'none' : '1px solid var(--line)',
                }}
              >
                <StateBadge status={entry.state} />
                <span
                  style={{
                    fontFamily: 'var(--font-mono)',
                    color: 'var(--ink-muted)',
                    fontSize: 'var(--text-caption)',
                  }}
                >
                  {formatDate(entry.at)}
                </span>
              </div>
            ))}
          </div>
        )}
      </Card>

      {/* 5. Compensation Panel (if CANCELLED) */}
      {status === 'CANCELLED' && compensationData && (
        <Card title="Saga Compensation Status">
          <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-2)' }}>
            <div>
              <div style={{ fontWeight: 600, fontSize: 'var(--text-caption)', color: 'var(--ink-muted)', marginBottom: '6px' }}>
                RELEASED RESOURCES:
              </div>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px' }}>
                {(compensationData.released || []).map((resId) => (
                  <span
                    key={resId}
                    style={{
                      fontFamily: 'var(--font-mono)',
                      fontSize: 'var(--text-caption)',
                      color: 'var(--signal-green)',
                      backgroundColor: 'var(--signal-green-soft)',
                      padding: '4px 10px',
                      borderRadius: 'var(--radius-pill)',
                      border: '1px solid var(--line)',
                    }}
                  >
                    ✓ {resId}
                  </span>
                ))}
              </div>
            </div>

            {compensationData.pending && compensationData.pending.length > 0 && (
              <div>
                <div style={{ fontWeight: 600, fontSize: 'var(--text-caption)', color: 'var(--ink-muted)', marginBottom: '6px' }}>
                  PENDING COMPENSATION:
                </div>
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px' }}>
                  {compensationData.pending.map((resId) => (
                    <span
                      key={resId}
                      style={{
                        fontFamily: 'var(--font-mono)',
                        fontSize: 'var(--text-caption)',
                        color: 'var(--alert-amber)',
                        backgroundColor: '#FEF3E2',
                        padding: '4px 10px',
                        borderRadius: 'var(--radius-pill)',
                        border: '1px solid var(--line)',
                      }}
                    >
                      ⏳ {resId}
                    </span>
                  ))}
                </div>
              </div>
            )}
          </div>
        </Card>
      )}
    </div>
  )
}
