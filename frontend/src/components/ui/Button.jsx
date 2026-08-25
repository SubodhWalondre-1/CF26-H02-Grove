import React from 'react'

export default function Button({
  variant = 'primary',
  size = 'md',
  disabled = false,
  onClick,
  type = 'button',
  className = '',
  style = {},
  children,
  ...props
}) {
  const isSm = size === 'sm'

  const getVariantStyles = () => {
    switch (variant) {
      case 'primary':
        return {
          backgroundColor: 'var(--signal-green)',
          color: '#FFFFFF',
          border: '1px solid transparent',
        }
      case 'secondary':
        return {
          backgroundColor: '#FFFFFF',
          color: 'var(--ink)',
          border: '1px solid var(--line)',
        }
      case 'destructive':
        return {
          backgroundColor: '#FFFFFF',
          color: 'var(--critical-red)',
          border: '1px solid var(--critical-red)',
        }
      default:
        return {
          backgroundColor: 'var(--signal-green)',
          color: '#FFFFFF',
          border: '1px solid transparent',
        }
    }
  }

  const baseStyles = {
    display: 'inline-flex',
    alignItems: 'center',
    justifyContent: 'center',
    fontFamily: 'var(--font-body)',
    fontWeight: 600,
    fontSize: isSm ? '0.8125rem' : '0.875rem',
    padding: isSm ? '8px 16px' : '10px 20px',
    borderRadius: 'var(--radius-input)',
    cursor: disabled ? 'not-allowed' : 'pointer',
    opacity: disabled ? 0.5 : 1,
    lineHeight: 1.25,
    userSelect: 'none',
    transition: 'filter 0.15s ease, background-color 0.15s ease',
    ...getVariantStyles(),
    ...style,
  }

  return (
    <>
      <style>{`
        .mediora-btn-primary:not(:disabled):hover {
          filter: brightness(1.08);
        }
        .mediora-btn-secondary:not(:disabled):hover {
          background-color: var(--surface-recessed) !important;
        }
        .mediora-btn-destructive:not(:disabled):hover {
          background-color: #FBE9E9 !important;
        }
      `}</style>
      <button
        type={type}
        disabled={disabled}
        onClick={disabled ? undefined : onClick}
        className={`mediora-btn mediora-btn-${variant} ${className}`}
        style={baseStyles}
        {...props}
      >
        {children}
      </button>
    </>
  )
}
