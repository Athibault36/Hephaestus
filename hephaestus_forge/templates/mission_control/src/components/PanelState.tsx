import type { ReactNode } from 'react';

type PanelStateTone = 'empty' | 'loading' | 'error' | 'offline' | 'degraded';

interface PanelStateProps {
  tone: PanelStateTone;
  icon: string;
  title: string;
  message: string;
  children?: ReactNode;
}

export function PanelState({ tone, icon, title, message, children }: PanelStateProps) {
  return (
    <div className={`panel-state ${tone}`} role={tone === 'error' ? 'alert' : 'status'} aria-busy={tone === 'loading'}>
      <span className="panel-state-icon" aria-hidden="true">
        {tone === 'loading' ? <span className="state-spinner" /> : icon}
      </span>
      <h3>{title}</h3>
      <p>{message}</p>
      {children ? <div className="panel-state-actions">{children}</div> : null}
    </div>
  );
}
