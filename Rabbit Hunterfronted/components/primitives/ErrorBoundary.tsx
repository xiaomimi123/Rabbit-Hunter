import React from 'react';

interface State { error: Error | null }
interface Props { children: React.ReactNode; fallback?: (err: Error) => React.ReactNode }

export class ErrorBoundary extends React.Component<Props, State> {
  state: State = { error: null };
  static getDerivedStateFromError(error: Error): State {
    return { error };
  }
  componentDidCatch(error: Error) {
    // eslint-disable-next-line no-console
    console.error('[ErrorBoundary]', error);
  }
  reset = () => this.setState({ error: null });
  render() {
    const { error } = this.state;
    if (error) {
      if (this.props.fallback) return this.props.fallback(error);
      return (
        <div className="border border-oxblood-soft bg-oxblood-soft px-4 py-3 font-mono text-[0.85rem] text-oxblood">
          <span className="mr-2 opacity-60">▌</span>本页加载失败:{error.message}
          <button onClick={this.reset} className="ml-3 underline">重试</button>
        </div>
      );
    }
    return this.props.children;
  }
}
