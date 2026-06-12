import { useEffect, useRef, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { useUIStore } from '../services/store';
import type { WsEvent } from '../types';

const HEARTBEAT_MS = 30_000;
const SILENCE_TIMEOUT_MS = 60_000;
const BACKOFF_STEPS = [1000, 2000, 4000, 8000, 16000, 30000];

interface Status {
  connected: boolean;
  unhealthyCount: number;
  lastReceivedAt: number | null;
}

export function useV5WebSocket(url: string): Status {
  const qc = useQueryClient();
  const pushWsEvent = useUIStore((s) => s.pushWsEvent);
  const setEffectiveAi = useUIStore((s) => s.setEffectiveAiProvider);

  const [status, setStatus] = useState<Status>({
    connected: false,
    unhealthyCount: 0,
    lastReceivedAt: null,
  });

  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const heartbeatTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const watchdogRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const attemptRef = useRef<number>(0);
  const lastReceivedRef = useRef<number>(Date.now());
  const teardownRef = useRef<boolean>(false);

  useEffect(() => {
    teardownRef.current = false;

    const dispatchInvalidate = (ev: WsEvent) => {
      switch (ev.type) {
        case 'position_opened':
        case 'position_closed':
        case 'position_extended':
          qc.invalidateQueries({ queryKey: ['v5', 'active'] });
          qc.invalidateQueries({ queryKey: ['v5', 'history'] });
          qc.invalidateQueries({ queryKey: ['v5', 'dashboard'] });
          break;
        case 'ai_health':
          qc.invalidateQueries({ queryKey: ['v5', 'ai'] });
          setEffectiveAi((ev as any).provider ?? null);
          break;
        case 'scoring_stalled':
          break;
      }
    };

    const connect = () => {
      if (teardownRef.current) return;
      const ws = new WebSocket(url);
      wsRef.current = ws;

      ws.onopen = () => {
        attemptRef.current = 0;
        lastReceivedRef.current = Date.now();
        setStatus((s) => ({ ...s, connected: true, unhealthyCount: 0 }));
        if (heartbeatTimerRef.current) clearInterval(heartbeatTimerRef.current);
        heartbeatTimerRef.current = setInterval(() => {
          try {
            ws.send(JSON.stringify({ type: 'ping', ts: Date.now() }));
          } catch { /* ignore */ }
        }, HEARTBEAT_MS);

        if (watchdogRef.current) clearInterval(watchdogRef.current);
        watchdogRef.current = setInterval(() => {
          if (Date.now() - lastReceivedRef.current > SILENCE_TIMEOUT_MS) {
            try { ws.close(); } catch { /* ignore */ }
          }
        }, 10_000);
      };

      ws.onmessage = (msg) => {
        lastReceivedRef.current = Date.now();
        setStatus((s) => ({ ...s, lastReceivedAt: lastReceivedRef.current }));
        let payload: WsEvent | null = null;
        try {
          payload = JSON.parse(msg.data);
        } catch {
          return;
        }
        if (!payload || typeof payload !== 'object') return;
        if (payload.type === 'ping') return;
        pushWsEvent(payload);
        dispatchInvalidate(payload);
      };

      ws.onclose = () => {
        setStatus((s) => ({ ...s, connected: false, unhealthyCount: s.unhealthyCount + 1 }));
        if (heartbeatTimerRef.current) clearInterval(heartbeatTimerRef.current);
        if (watchdogRef.current) clearInterval(watchdogRef.current);
        if (teardownRef.current) return;
        const idx = Math.min(attemptRef.current, BACKOFF_STEPS.length - 1);
        const delay = BACKOFF_STEPS[idx];
        attemptRef.current += 1;
        reconnectTimerRef.current = setTimeout(connect, delay);
      };

      ws.onerror = () => {
        // onclose follows
      };
    };

    connect();

    return () => {
      teardownRef.current = true;
      if (reconnectTimerRef.current) clearTimeout(reconnectTimerRef.current);
      if (heartbeatTimerRef.current) clearInterval(heartbeatTimerRef.current);
      if (watchdogRef.current) clearInterval(watchdogRef.current);
      try { wsRef.current?.close(); } catch { /* ignore */ }
    };
  }, [url, qc, pushWsEvent, setEffectiveAi]);

  return status;
}
