import { Component, type ReactNode } from 'react'

// ── Error Boundary ────────────────────────────────────────────────────────

interface EBState { error: Error | null }

export class ErrorBoundary extends Component<{ children: ReactNode }, EBState> {
  state: EBState = { error: null }

  static getDerivedStateFromError(error: Error): EBState {
    return { error }
  }

  render() {
    if (this.state.error) {
      return (
        <div className="error-boundary">
          <div className="error-boundary-icon">⚠</div>
          <div className="error-boundary-title">Something went wrong</div>
          <pre className="error-boundary-message">{this.state.error.message}</pre>
          <button
            className="btn-send"
            style={{ marginTop: 12 }}
            onClick={() => this.setState({ error: null })}
          >
            Try again
          </button>
        </div>
      )
    }
    return this.props.children
  }
}

// ── Spinner ───────────────────────────────────────────────────────────────

export function Spinner({ size = 16 }: { size?: number }) {
  return (
    <span
      className="spinner"
      style={{ width: size, height: size, borderWidth: size > 20 ? 3 : 2 }}
    />
  )
}

// ── Inline error message ──────────────────────────────────────────────────

export function InlineError({ message }: { message: string }) {
  return <div className="inline-error">⚠ {message}</div>
}
