import { Component, type ReactNode } from "react";

/**
 * Catches a render error in one view so a malformed response or link shows a message instead of
 * a blank page. A new `resetKey` (the route) clears the error without remounting healthy views.
 */
type Props = { resetKey: string; children: ReactNode };
type State = { error: string | null; failedKey: string | null };

export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null, failedKey: null };

  static getDerivedStateFromError(e: unknown): Partial<State> {
    return { error: e instanceof Error ? e.message : String(e) };
  }

  static getDerivedStateFromProps(props: Props, state: State): Partial<State> | null {
    if (state.error === null) return null;
    if (state.failedKey === null) return { failedKey: props.resetKey };
    return state.failedKey === props.resetKey ? null : { error: null, failedKey: null };
  }

  render() {
    if (this.state.error === null) return this.props.children;
    return (
      <div className="view">
        <div className="notice notice-bad" role="alert">
          <strong>This view couldn't be shown.</strong> {this.state.error}{" "}
          <a href="#/ask">Go to Ask</a> or pick another view above.
        </div>
      </div>
    );
  }
}
