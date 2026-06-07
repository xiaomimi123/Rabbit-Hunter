/**
 * useSystemMode (v0.5.4)
 *
 * 替代 useUIStore.systemState — 把 SHADOW/LIVE 状态搬到后端 DB 持久化。
 * 之前 useUIStore 只是 localStorage，刷新或换浏览器就丢；现在 system_settings
 * 表里有真实的 system_state 行，所有端点 / scorer 都看到同一份事实。
 *
 * 用法：
 *   const { mode, isLive, isShadow, setMode } = useSystemMode();
 *   setMode.mutate('LIVE');   // 会被后端拦截如果 trader 鉴权不通过
 */

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { apiGet, apiPost } from '../services/apiInterceptor';

const API_BASE = (import.meta as any).env?.VITE_API_URL || 'http://localhost:8000/api';

export type SystemMode = 'SHADOW' | 'LIVE';

interface ModeResp {
  mode:       SystemMode;
  is_live:    boolean;
  is_shadow:  boolean;
}

export function useSystemMode() {
  const qc = useQueryClient();

  const query = useQuery<ModeResp>({
    queryKey:        ['systemMode'],
    queryFn:         () => apiGet(`${API_BASE}/v43/system/mode`),
    refetchInterval: 15_000,
    staleTime:       10_000,
  });

  const setMode = useMutation({
    mutationFn: (mode: SystemMode) => apiPost(`${API_BASE}/v43/system/mode`, { mode }),
    onSuccess:  () => qc.invalidateQueries({ queryKey: ['systemMode'] }),
  });

  return {
    mode:      query.data?.mode      ?? 'SHADOW' as SystemMode,  // 默认 SHADOW（安全姿态）
    isLive:    query.data?.is_live   ?? false,
    isShadow:  query.data?.is_shadow ?? true,
    loading:   query.isLoading,
    setMode,
  };
}
