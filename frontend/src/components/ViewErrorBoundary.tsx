import { Component, type ReactNode } from "react";

interface Props {
  viewId: string;
  children: ReactNode;
}

interface State {
  error: Error | null;
}

// Per-view error boundary: a single view throwing (bad backend shape, render
// bug) degrades to a recoverable error card instead of blanking the whole app.
export class ViewErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error) {
    // Surface in the console so transient render failures are debuggable.
    console.error(`admin view "${this.props.viewId}" crashed:`, error);
  }

  reset = () => {
    this.setState({ error: null });
  };

  render() {
    if (this.state.error) {
      return (
        <div className="alert alert-error rounded-lg">
          <div className="grid gap-1">
            <strong>This view failed to render</strong>
            <span className="text-sm opacity-80">{this.state.error.message}</span>
          </div>
          <button
            type="button"
            className="btn btn-sm btn-ghost rounded-lg self-end"
            onClick={this.reset}
          >
            Try again
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}
