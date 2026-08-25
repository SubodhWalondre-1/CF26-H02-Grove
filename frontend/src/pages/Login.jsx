import React, { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import Button from '../components/ui/Button'
import PulseLine from '../components/ui/PulseLine'
import { useAuthStore } from '../store/authStore'

export default function Login() {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [localError, setLocalError] = useState('')

  const navigate = useNavigate()
  const login = useAuthStore((state) => state.login)
  const isLoading = useAuthStore((state) => state.isLoading)
  const storeError = useAuthStore((state) => state.error)

  const handleSubmit = async (e) => {
    e.preventDefault()
    setLocalError('')

    if (!username.trim() || !password.trim()) {
      setLocalError('Please enter username and password.')
      return
    }

    try {
      await login(username.trim(), password)
      navigate('/')
    } catch (err) {
      // Error handled in store and displayed below
    }
  }

  const handleQuickFill = (user, pass) => {
    setUsername(user)
    setPassword(pass)
    setLocalError('')
  }

  const displayedError = localError || storeError

  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        minHeight: '100vh',
        backgroundColor: 'var(--surface)',
        padding: 'var(--space-3)',
      }}
    >
      <div
        style={{
          width: '100%',
          maxWidth: '420px',
          borderRadius: 'var(--radius-card)',
          border: '1px solid var(--line)',
          backgroundColor: 'var(--surface-recessed)',
          padding: 'var(--space-4)',
          display: 'flex',
          flexDirection: 'column',
          gap: 'var(--space-3)',
        }}
      >
        {/* Header Branding */}
        <div style={{ textAlign: 'center', display: 'flex', flexDirection: 'column', gap: '4px' }}>
          <h1
            style={{
              fontFamily: 'var(--font-display)',
              fontSize: 'var(--text-h1)',
              fontWeight: 480,
              color: 'var(--pulse-blue)',
              letterSpacing: '-0.01em',
              textTransform: 'uppercase',
              margin: 0,
            }}
          >
            Mediora
          </h1>
          <p
            style={{
              fontFamily: 'var(--font-body)',
              fontSize: 'var(--text-caption)',
              color: 'var(--ink-muted)',
              margin: 0,
            }}
          >
            Clinical Resource Transaction Coordinator
          </p>
        </div>

        {/* PulseLine Divider */}
        <div style={{ width: '100%', overflow: 'hidden' }}>
          <PulseLine variant="idle" animated width="100%" height={20} />
        </div>

        {/* Authentication Form */}
        <form
          onSubmit={handleSubmit}
          style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-2)' }}
        >
          <div>
            <input
              id="username"
              type="text"
              placeholder="Username"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              disabled={isLoading}
              style={{
                width: '100%',
                padding: '10px 12px',
                borderRadius: 'var(--radius-input)',
                border: '1px solid var(--line)',
                backgroundColor: 'var(--surface)',
                fontFamily: 'var(--font-body)',
                fontSize: 'var(--text-body)',
                color: 'var(--ink)',
              }}
            />
          </div>

          <div>
            <input
              id="password"
              type="password"
              placeholder="Password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              disabled={isLoading}
              style={{
                width: '100%',
                padding: '10px 12px',
                borderRadius: 'var(--radius-input)',
                border: '1px solid var(--line)',
                backgroundColor: 'var(--surface)',
                fontFamily: 'var(--font-body)',
                fontSize: 'var(--text-body)',
                color: 'var(--ink)',
              }}
            />
          </div>

          {displayedError && (
            <p
              role="alert"
              style={{
                fontFamily: 'var(--font-body)',
                fontSize: 'var(--text-caption)',
                color: 'var(--critical-red)',
                textAlign: 'center',
                margin: '2px 0 0 0',
              }}
            >
              {displayedError}
            </p>
          )}

          <div style={{ marginTop: '4px' }}>
            <Button
              type="submit"
              variant="primary"
              disabled={isLoading}
              style={{ width: '100%' }}
            >
              {isLoading ? 'Signing in...' : 'Sign in'}
            </Button>
          </div>
        </form>

        {/* Demo Roles Quick Fill Hint */}
        <div
          style={{
            backgroundColor: 'var(--surface)',
            border: '1px solid var(--line)',
            borderRadius: 'var(--radius-input)',
            padding: 'var(--space-2)',
            fontFamily: 'var(--font-body)',
            fontSize: 'var(--text-caption)',
            color: 'var(--ink-muted)',
            lineHeight: 1.4,
          }}
        >
          <div style={{ fontWeight: 600, color: 'var(--ink)', marginBottom: '4px' }}>
            Demo Accounts:
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
            <button
              type="button"
              onClick={() => handleQuickFill('dr.mehta', 'mediora123')}
              style={{
                background: 'none',
                border: 'none',
                padding: 0,
                textAlign: 'left',
                color: 'var(--pulse-blue)',
                cursor: 'pointer',
                fontFamily: 'inherit',
                fontSize: 'inherit',
              }}
            >
              • <strong>dr.mehta</strong> (Doctor)
            </button>
            <button
              type="button"
              onClick={() => handleQuickFill('nurse.priya', 'mediora123')}
              style={{
                background: 'none',
                border: 'none',
                padding: 0,
                textAlign: 'left',
                color: 'var(--pulse-blue)',
                cursor: 'pointer',
                fontFamily: 'inherit',
                fontSize: 'inherit',
              }}
            >
              • <strong>nurse.priya</strong> (Nurse)
            </button>
            <button
              type="button"
              onClick={() => handleQuickFill('admin.ops', 'mediora123')}
              style={{
                background: 'none',
                border: 'none',
                padding: 0,
                textAlign: 'left',
                color: 'var(--pulse-blue)',
                cursor: 'pointer',
                fontFamily: 'inherit',
                fontSize: 'inherit',
              }}
            >
              • <strong>admin.ops</strong> (Admin)
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
