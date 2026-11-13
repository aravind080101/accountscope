import { Component, type ReactNode } from "react";

/** Catches a drawing error in one part of the screen and shows a message there, instead of blanking the whole app. */
export class ErrorBoundary extends Component<{ children: ReactNode; label?: string; resetKey?: unknown }, { error: Error | null }> {
  state = { error: null as Error | null };
  static getDerivedStateFromError(error: Error) { return { error }; }
  componentDidCatch(error: Error) { console.error("[AccountScope] screen error", this.props.label || "", error); }
  componentDidUpdate(prev: { resetKey?: unknown }) {
    if (this.state.error && prev.resetKey !== this.props.resetKey) this.setState({ error: null });
  }
  render() {
    if (!this.state.error) return this.props.children;
    return (
      <div className="m-6 rounded-md border border-danger/30 bg-danger-soft px-4 py-3 text-[13px] text-danger">
        <div className="font-semibold">Couldn't show {this.props.label || "this part of the page"}.</div>
        <div className="mt-1 text-[12.5px]">{this.state.error.message}</div>
        <button className="mt-2 underline" onClick={() => this.setState({ error: null })}>Try again</button>
      </div>
    );
  }
}
