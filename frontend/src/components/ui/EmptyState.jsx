import React from 'react'

export default function EmptyState({
  message = 'No records found.',
  className = '',
}) {
  return (
    <div
      className={`mediora-empty-state ${className}`}
      style={{
        padding: 'var(--space-4)',
        textAlign: 'center',
      }}
    >
      <p
        style={{
          color: 'var(--ink-muted)',
          fontFamily: 'var(--font-body)',
          fontSize: 'var(--text-body)',
          margin: 0,
        }}
      >
        {message}
      </p>
    </div>
  )
}
