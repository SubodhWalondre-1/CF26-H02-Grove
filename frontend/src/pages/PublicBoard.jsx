import React, { useEffect, useState } from 'react'
import { Activity, AlertCircle, CheckCircle, Droplets, HeartHandshake, PhoneCall, QrCode, Radio, ShieldAlert } from 'lucide-react'
import { QRCodeSVG } from 'qrcode.react'
import { getPublicAlerts } from '../lib/api'

export default function PublicBoard() {
  const [alerts, setAlerts] = useState([])
  const [loading, setLoading] = useState(true)
  const [connected, setConnected] = useState(false)
  const [lastUpdated, setLastUpdated] = useState(new Date())

  // 1. Initial REST fetch
  const fetchAlerts = async () => {
    try {
      const res = await getPublicAlerts()
      setAlerts(res.data || [])
      setLastUpdated(new Date())
    } catch (err) {
      console.error('Failed to fetch public shortage alerts:', err)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchAlerts()
    const fallbackPoll = setInterval(fetchAlerts, 10000)
    return () => clearInterval(fallbackPoll)
  }, [])

  // 2. Real-time Unauthenticated WebSocket
  useEffect(() => {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const host = window.location.host || 'localhost:8000'
    const wsUrl = `${protocol}//${host}/ws/public-alerts`

    let ws
    const connectWs = () => {
      try {
        ws = new WebSocket(wsUrl)
        ws.onopen = () => {
          setConnected(true)
        }
        ws.onmessage = (event) => {
          try {
            const data = JSON.parse(event.data)
            if (data.event === 'SHORTAGE_ALERT_RAISED') {
              setAlerts((prev) => {
                const existing = prev.findIndex((a) => a.resource_type === data.resource_type && a.subtype === data.subtype)
                if (existing >= 0) {
                  const updated = [...prev]
                  updated[existing] = {
                    ...updated[existing],
                    units_needed: data.units_needed,
                    unit_label: data.unit_label || updated[existing].unit_label,
                  }
                  return updated
                }
                return [
                  {
                    alert_id: data.alert_id,
                    resource_type: data.resource_type,
                    subtype: data.subtype,
                    units_needed: data.units_needed,
                    unit_label: data.unit_label || 'units',
                    created_at: data.timestamp,
                    helpline_phone: data.helpline || '+1 (800) 555-CARE',
                    helpline_url: 'https://mediora.hospital/donate',
                  },
                  ...prev,
                ]
              })
            } else if (data.event === 'SHORTAGE_ALERT_RESOLVED') {
              setAlerts((prev) => prev.filter((a) => !(a.resource_type === data.resource_type && a.subtype === data.subtype)))
            }
            setLastUpdated(new Date())
          } catch (e) {
            console.error('Error parsing public alert ws message:', e)
          }
        }
        ws.onclose = () => {
          setConnected(false)
          setTimeout(connectWs, 5000)
        }
      } catch (err) {
        setConnected(false)
        setTimeout(connectWs, 5000)
      }
    }

    connectWs()
    return () => {
      if (ws) ws.close()
    }
  }, [])

  return (
    <div
      style={{
        minHeight: '100vh',
        backgroundColor: '#090D16',
        color: '#F8FAFC',
        fontFamily: 'Inter, system-ui, -apple-system, sans-serif',
        padding: '24px 32px',
        display: 'flex',
        flexDirection: 'column',
        justifyContent: 'space-between',
      }}
    >
      {/* 1. Header Banner */}
      <div>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderBottom: '2px solid #1E293B', paddingBottom: '18px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '14px' }}>
            <div style={{ padding: '10px', borderRadius: '12px', background: '#DC2626' }}>
              <HeartHandshake size={32} color="#fff" />
            </div>
            <div>
              <h1 style={{ fontSize: '1.8rem', fontWeight: 800, margin: 0, letterSpacing: '-0.02em', color: '#FFFFFF' }}>
                COMMUNITY EMERGENCY DONATION BOARD
              </h1>
              <p style={{ margin: '3px 0 0', fontSize: '0.9rem', color: '#94A3B8' }}>
                Mediora Hospital Network · Real-Time Critical Supply & Blood Dispatch Center
              </p>
            </div>
          </div>

          {/* Live Pulse Indicator */}
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px', background: '#1E293B', padding: '8px 16px', borderRadius: '30px' }}>
            <span
              style={{
                width: '10px',
                height: '10px',
                borderRadius: '50%',
                backgroundColor: connected ? '#22C55E' : '#EAB308',
                boxShadow: connected ? '0 0 10px #22C55E' : 'none',
              }}
            />
            <span style={{ fontSize: '0.85rem', fontWeight: 600, color: '#E2E8F0' }}>
              {connected ? 'LIVE BROADCAST' : 'CONNECTING...'}
            </span>
          </div>
        </div>

        {/* 2. Main Alert Grid */}
        <div style={{ marginTop: '28px' }}>
          {loading ? (
            <div style={{ textAlign: 'center', padding: '60px 0', color: '#94A3B8', fontSize: '1.1rem' }}>
              Loading current shortage indicators...
            </div>
          ) : alerts.length === 0 ? (
            <div
              style={{
                backgroundColor: '#0F172A',
                border: '2px dashed #22C55E',
                borderRadius: '16px',
                padding: '50px 30px',
                textAlign: 'center',
                display: 'flex',
                flexDirection: 'column',
                alignItems: 'center',
                gap: '12px',
              }}
            >
              <CheckCircle size={48} color="#22C55E" />
              <h2 style={{ fontSize: '1.5rem', fontWeight: 700, margin: 0, color: '#F8FAFC' }}>
                All Critical Supplies Fully Stocked
              </h2>
              <p style={{ color: '#94A3B8', maxWidth: '500px', margin: 0, fontSize: '0.95rem' }}>
                There are currently no active critical consumable or blood unit shortages reported. Thank you to all our generous donors!
              </p>
            </div>
          ) : (
            <div
              style={{
                display: 'grid',
                gridTemplateColumns: 'repeat(auto-fill, minmax(340px, 1fr))',
                gap: '20px',
              }}
            >
              {alerts.map((alert) => {
                const isBlood = alert.resource_type === 'BLOOD_UNIT'
                const isOxygen = alert.resource_type === 'OXYGEN_UNIT'

                return (
                  <div
                    key={alert.alert_id}
                    style={{
                      backgroundColor: '#111827',
                      border: '2px solid #EF4444',
                      borderRadius: '16px',
                      padding: '20px',
                      display: 'flex',
                      flexDirection: 'column',
                      justifyContent: 'space-between',
                      boxShadow: '0 8px 24px rgba(239, 68, 68, 0.2)',
                    }}
                  >
                    <div>
                      {/* Top Badge */}
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '14px' }}>
                        <span
                          style={{
                            display: 'inline-flex',
                            alignItems: 'center',
                            gap: '6px',
                            backgroundColor: '#7F1D1D',
                            color: '#FCA5A5',
                            padding: '4px 10px',
                            borderRadius: '20px',
                            fontSize: '0.75rem',
                            fontWeight: 700,
                            letterSpacing: '0.04em',
                          }}
                        >
                          <ShieldAlert size={14} />
                          CRITICAL DEMAND
                        </span>
                        <span style={{ fontSize: '0.75rem', color: '#94A3B8', fontFamily: 'monospace' }}>
                          {alert.alert_id}
                        </span>
                      </div>

                      {/* Main Title / Subtype */}
                      <div style={{ fontSize: '1.4rem', fontWeight: 800, color: '#FFFFFF', marginBottom: '4px' }}>
                        {isBlood ? `Blood Type: ${alert.subtype}` : alert.subtype.replace(/_/g, ' ')}
                      </div>
                      <div style={{ fontSize: '0.85rem', color: '#94A3B8', marginBottom: '16px' }}>
                        Category: {alert.resource_type.replace(/_/g, ' ')}
                      </div>

                      {/* Units Needed Counter */}
                      <div
                        style={{
                          backgroundColor: '#1E293B',
                          padding: '14px 18px',
                          borderRadius: '12px',
                          display: 'flex',
                          alignItems: 'baseline',
                          justifyContent: 'space-between',
                          marginBottom: '16px',
                        }}
                      >
                        <span style={{ fontSize: '0.9rem', color: '#CBD5E1', fontWeight: 600 }}>
                          Immediate Requirement:
                        </span>
                        <span style={{ fontSize: '1.8rem', fontWeight: 900, color: '#EF4444' }}>
                          {alert.units_needed}{' '}
                          <span style={{ fontSize: '0.9rem', fontWeight: 500, color: '#94A3B8' }}>
                            {alert.unit_label}
                          </span>
                        </span>
                      </div>
                    </div>

                    {/* QR Code & Helpline Footer */}
                    <div
                      style={{
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'space-between',
                        borderTop: '1px solid #1E293B',
                        paddingTop: '14px',
                      }}
                    >
                      <div>
                        <div style={{ fontSize: '0.75rem', color: '#94A3B8', marginBottom: '2px' }}>
                          Scan to Coordinate Donation:
                        </div>
                        <div style={{ fontSize: '0.9rem', fontWeight: 700, color: '#38BDF8', display: 'flex', alignItems: 'center', gap: '4px' }}>
                          <PhoneCall size={14} />
                          {alert.helpline_phone || '+1 (800) 555-CARE'}
                        </div>
                      </div>

                      <div style={{ padding: '6px', background: '#FFFFFF', borderRadius: '8px' }}>
                        <QRCodeSVG
                          value={alert.helpline_url || 'https://mediora.hospital/donate'}
                          size={64}
                          level="M"
                        />
                      </div>
                    </div>
                  </div>
                )
              })}
            </div>
          )}
        </div>
      </div>

      {/* 3. Bottom Kiosk Footer */}
      <div
        style={{
          borderTop: '1px solid #1E293B',
          paddingTop: '16px',
          marginTop: '30px',
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          flexWrap: 'wrap',
          gap: '10px',
          fontSize: '0.8rem',
          color: '#64748B',
        }}
      >
        <div>
          🛡️ <b>Public Kiosk Display</b> — Automated threshold detection. Zero Patient Identifiers (Zero-PHI compliant).
        </div>
        <div>
          Last Sync: {lastUpdated.toLocaleTimeString()}
        </div>
      </div>
    </div>
  )
}
