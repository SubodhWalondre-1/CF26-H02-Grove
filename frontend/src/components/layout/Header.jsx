import React from 'react'
import { Link } from 'react-router-dom'
import { useAuthStore } from '../../store/authStore'
import PulseLine from '../ui/PulseLine'

export default function Header() {
  const user = useAuthStore((state) => state.user)
  const logout = useAuthStore((state) => state.logout)

  const displayName = user?.display_name || user?.username || 'Authenticated User'
  const roleName = user?.role ? user.role.charAt(0).toUpperCase() + user.role.slice(1) : 'Staff'

  return (
    <header
      style={{
        position: 'fixed',
        top: 0,
        left: 0,
        right: 0,
        zIndex: 100,
        backgroundColor: 'var(--surface)',
        height: '76px',
        display: 'flex',
        flexDirection: 'column',
      }}
    >
      {/* Main Navigation Bar */}
      <div
        style={{
          height: 'var(--header-height)',
          display: 'flex',
          alignItems: 'center',
          padding: '0 var(--space-4)',
          borderBottom: '1px solid var(--line)',
        }}
      >
        {/* Wordmark */}
        <Link
          to="/"
          style={{
            textDecoration: 'none',
            display: 'flex',
            alignItems: 'center',
            gap: '8px',
          }}
        >
          <span
            style={{
              fontFamily: 'var(--font-display)',
              fontSize: '1.375rem',
              fontWeight: 480,
              color: 'var(--pulse-blue)',
              letterSpacing: '-0.01em',
              textTransform: 'uppercase',
            }}
          >
            Mediora
          </span>
        </Link>

        {/* Flexible Spacer */}
        <div style={{ flex: 1 }} />

        {/* User Info & Actions */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-3)' }}>
          {/* User Role Chip */}
          <div
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: '6px',
              backgroundColor: 'var(--surface-recessed)',
              border: '1px solid var(--line)',
              padding: '4px 12px',
              borderRadius: 'var(--radius-pill)',
              fontFamily: 'var(--font-body)',
              fontSize: 'var(--text-caption)',
              color: 'var(--ink-muted)',
              fontWeight: 500,
            }}
          >
            <span style={{ color: 'var(--ink)', fontWeight: 600 }}>{displayName}</span>
            <span>·</span>
            <span>{roleName}</span>
          </div>

          {/* Text-Only Logout Button */}
          <button
            type="button"
            onClick={logout}
            style={{
              background: 'none',
              border: 'none',
              padding: '4px 8px',
              fontFamily: 'var(--font-body)',
              fontSize: 'var(--text-caption)',
              color: 'var(--ink-muted)',
              fontWeight: 500,
              cursor: 'pointer',
              borderRadius: 'var(--radius-input)',
              transition: 'color 0.15s ease',
            }}
            onMouseEnter={(e) => (e.currentTarget.style.color = 'var(--critical-red)')}
            onMouseLeave={(e) => (e.currentTarget.style.color = 'var(--ink-muted)')}
          >
            Sign out
          </button>
        </div>
      </div>

      {/* Full-width ambient pulse line divider */}
      <div style={{ height: '20px', width: '100%', overflow: 'hidden' }}>
        <PulseLine variant="idle" width="100%" height={20} animated />
      </div>
    </header>
  )
}
