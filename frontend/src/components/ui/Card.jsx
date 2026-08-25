import React from 'react'

export default function Card({
  title,
  className = '',
  style = {},
  children,
  ...props
}) {
  return (
    <div
      className={`mediora-card ${className}`}
      style={{
        backgroundColor: 'var(--surface-recessed)',
        border: '1px solid var(--line)',
        borderRadius: 'var(--radius-card)',
        padding: 'var(--space-3)',
        ...style,
      }}
      {...props}
    >
      {title && (
        <h3
          style={{
            fontFamily: 'var(--font-body)',
            fontWeight: 600,
            fontSize: 'var(--text-h3)',
            color: 'var(--ink)',
            marginBottom: 'var(--space-2)',
          }}
        >
          {title}
        </h3>
      )}
      {children}
    </div>
  )
}
