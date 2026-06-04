import React from 'react';

interface SkeletonProps {
  rows?: number;
  className?: string;
}

export function LoadingSkeleton({ rows = 5, className = '' }: SkeletonProps) {
  return (
    <div className={`space-y-2 animate-pulse ${className}`}>
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className="h-12 bg-terminal-card rounded border border-terminal-border" />
      ))}
    </div>
  );
}

export function InlineSpinner({ className = '' }: { className?: string }) {
  return (
    <div
      className={`inline-block w-4 h-4 border-2 border-primary/30 border-t-primary rounded-full animate-spin ${className}`}
    />
  );
}
