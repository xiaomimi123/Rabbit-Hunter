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
        <div className="rounded-md border border-accent-short/30 bg-accent-short/10 p-4 text-sm text-accent-short">
          本页加载失败:{error.message}
          <button onClick={this.reset} className="ml-3 underline">重试</button>
        </div>
      );
    }
    return this.props.children;
  }
}
