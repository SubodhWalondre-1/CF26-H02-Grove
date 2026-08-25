import React from 'react'

export default class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props)
    this.state = { hasError: false, error: null }
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, error }
  }

  componentDidCatch(error, info) {
    // In Phase 6 this would send to an error reporting service.
    // For hackathon: log to console only.
    console.error('[Mediora] Render error:', error, info?.componentStack)
  }

  render() {
    if (this.state.hasError) {
      return (
        <div
          style={{
            padding: 'var(--space-8)',
            textAlign: 'center',
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            gap: 'var(--space-3)',
          }}
        >
          <p
            style={{
              fontFamily: 'var(--font-display)',
              fontSize: 'var(--text-h2)',
              color: 'var(--ink)',
              fontWeight: 460,
              margin: 0,
            }}
          >
            Something went wrong.
          </p>
          <p
            style={{
              fontFamily: 'var(--font-body)',
              fontSize: 'var(--text-body)',
              color: 'var(--ink-muted)',
              maxWidth: 480,
              margin: 0,
            }}
          >
            This view encountered an error. The backend and other pages are unaffected.
            Refresh to try again, or navigate to a different section.
          </p>
          <button
            type="button"
            onClick={() => this.setState({ hasError: false, error: null })}
            style={{
              background: 'var(--signal-green)',
              color: 'white',
              border: 'none',
              borderRadius: 'var(--radius-input)',
              padding: '10px 20px',
              fontFamily: 'var(--font-body)',
              fontWeight: 600,
              cursor: 'pointer',
            }}
          >
            Try again
          </button>
          {(this.props.showDetail ?? (typeof import.meta !== 'undefined' && import.meta.env?.DEV)) &&
            this.state.error && (
              <pre
                style={{
                  fontFamily: 'var(--font-mono)',
                  fontSize: 'var(--text-caption)',
                  color: 'var(--ink-muted)',
                  textAlign: 'left',
                  background: 'var(--surface-recessed)',
                  border: '1px solid var(--line)',
                  borderRadius: 'var(--radius-input)',
                  padding: 'var(--space-2)',
                  maxWidth: 600,
                  overflow: 'auto',
                  marginTop: 'var(--space-2)',
                }}
              >
                {this.state.error.toString()}
              </pre>
            )}
        </div>
      )
    }
    return this.props.children
  }
}
