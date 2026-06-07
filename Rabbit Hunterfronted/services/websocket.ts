/**
 * WebSocket 客户端服务
 * 提供实时数据推送功能
 */

import { useV43Store, useUIStore } from './store';
import { CoinData, Position, EvolutionEvent, SystemState } from '../types';

// WebSocket URL - 确保使用正确的路径
const WS_URL = import.meta.env.VITE_WS_URL || 'ws://localhost:8000/ws/v43';

// v45: bearer token via query string（浏览器 WS 升级不能带自定义 header）
const WS_TOKEN: string | undefined = (
  (import.meta as any).env?.VITE_API_TOKEN ||
  (import.meta as any).env?.VITE_API_BEARER_TOKEN ||
  ''
).toString().trim() || undefined;

// 如果环境变量设置了错误的路径，自动修正；并附加 token query
const getWebSocketUrl = () => {
  const envUrl = import.meta.env.VITE_WS_URL;
  let base = WS_URL;
  if (envUrl && !envUrl.includes('/v43')) {
    console.warn(`[WebSocket] 环境变量 VITE_WS_URL 缺少 /v43 路径，自动修正: ${envUrl} -> ${envUrl}/v43`);
    base = `${envUrl}/v43`;
  }
  if (WS_TOKEN) {
    const sep = base.includes('?') ? '&' : '?';
    return `${base}${sep}token=${encodeURIComponent(WS_TOKEN)}`;
  }
  return base;
};

interface WebSocketMessage {
  type: string;
  data?: any;
  metadata?: any;
  timestamp?: string;
}

class WebSocketClient {
  private ws: WebSocket | null = null;
  private reconnectAttempts = 0;
  private maxReconnectAttempts = 5;
  private reconnectDelay = 1000; // 初始延迟 1 秒
  private subscriptions: Set<string> = new Set();
  private isConnecting = false;

  connect() {
    if (this.ws?.readyState === WebSocket.OPEN || this.isConnecting) {
      return;
    }

    this.isConnecting = true;
    // v45: 把"连接中/重连/失败"状态写到 UI store，Layout 顶栏能据此显示 banner
    useUIStore.getState().setWsStatus(
      this.reconnectAttempts > 0 ? 'reconnecting' : 'connecting',
      this.reconnectAttempts,
    );

    const wsUrl = getWebSocketUrl();
    console.log(`[WebSocket] 正在连接到: ${wsUrl}`);
    this.ws = new WebSocket(wsUrl);

    this.ws.onopen = () => {
      console.log('[WebSocket] 连接已建立');
      this.isConnecting = false;
      this.reconnectAttempts = 0;
      this.reconnectDelay = 1000;
      useUIStore.getState().setWsStatus('connected', 0);

      // 重新订阅之前订阅的事件
      this.subscriptions.forEach(eventType => {
        this.subscribe(eventType);
      });
    };

    this.ws.onmessage = (event) => {
      try {
        const message: WebSocketMessage = JSON.parse(event.data);
        this.handleMessage(message);
      } catch (error) {
        console.error('[WebSocket] 消息解析失败:', error);
      }
    };

    this.ws.onclose = (ev) => {
      console.log('[WebSocket] 连接已关闭', ev.code, ev.reason);
      this.isConnecting = false;
      this.ws = null;

      // 4401 = 我们自己定义的"鉴权失败"。这种情况不重连（重连也是 401）。
      if (ev.code === 4401) {
        console.error('[WebSocket] 鉴权失败（4401）— 检查 VITE_API_TOKEN 是否和后端 API_BEARER_TOKEN 一致');
        useUIStore.getState().setWsStatus('failed', this.reconnectAttempts);
        return;
      }

      // 自动重连
      if (this.reconnectAttempts < this.maxReconnectAttempts) {
        this.reconnectAttempts++;
        const delay = this.reconnectDelay * Math.pow(2, this.reconnectAttempts - 1); // 指数退避
        console.log(`[WebSocket] ${delay}ms 后尝试重连 (${this.reconnectAttempts}/${this.maxReconnectAttempts})...`);
        useUIStore.getState().setWsStatus('reconnecting', this.reconnectAttempts);
        setTimeout(() => this.connect(), delay);
      } else {
        console.error('[WebSocket] 达到最大重连次数，停止重连');
        useUIStore.getState().setWsStatus('failed', this.reconnectAttempts);
      }
    };

    this.ws.onerror = (error) => {
      console.error('[WebSocket] 连接错误:', error);
      this.isConnecting = false;
      // onerror 后通常紧跟 onclose；这里不抢先 setStatus('failed')，让 onclose 决定
    };
  }

  disconnect() {
    if (this.ws) {
      this.ws.close();
      this.ws = null;
    }
    this.subscriptions.clear();
  }

  subscribe(eventType: string) {
    if (!this.ws || this.ws.readyState !== WebSocket.OPEN) {
      // 如果未连接，先连接
      this.connect();
      // 保存订阅请求，连接成功后自动订阅
      this.subscriptions.add(eventType);
      return;
    }

    this.subscriptions.add(eventType);
    this.ws.send(JSON.stringify({
      action: 'subscribe',
      event_type: eventType,
    }));
  }

  unsubscribe(eventType: string) {
    this.subscriptions.delete(eventType);
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify({
        action: 'unsubscribe',
        event_type: eventType,
      }));
    }
  }

  private handleMessage(message: WebSocketMessage) {
    const { setKillQueue, setPositions, setEvolutionEvents, setSystemState } = useV43Store.getState();

    switch (message.type) {
      case 'connection':
        console.log('[WebSocket] 连接确认:', message);
        break;

      case 'subscription':
        console.log('[WebSocket] 订阅确认:', message);
        break;

      case 'kill_queue_update':
        if (message.data) {
          setKillQueue(Array.isArray(message.data) ? message.data : []);
        }
        break;

      case 'position_update':
        if (message.data) {
          setPositions(Array.isArray(message.data) ? message.data : []);
        }
        break;

      case 'ai_evolution_event':
        if (message.data) {
          const currentEvents = useV43Store.getState().evolutionEvents;
          setEvolutionEvents([...currentEvents, message.data as EvolutionEvent]);
        }
        break;

      case 'system_status_update':
        if (message.data) {
          setSystemState(message.data as SystemState);
        }
        break;

      case 'chart_data_update':
        // 图表数据更新需要由具体组件处理
        console.log('[WebSocket] 图表数据更新:', message.data);
        break;

      case 'trade_confirmation':
        console.log('[WebSocket] 交易确认:', message.data);
        // 可以触发通知或更新持仓
        break;

      case 'error':
        console.error('[WebSocket] 服务器错误:', message);
        break;

      default:
        console.log('[WebSocket] 未知消息类型:', message.type, message);
    }
  }

  isConnected(): boolean {
    return this.ws?.readyState === WebSocket.OPEN;
  }
}

// 全局单例
let wsClient: WebSocketClient | null = null;

export const getWebSocketClient = (): WebSocketClient => {
  if (!wsClient) {
    wsClient = new WebSocketClient();
  }
  return wsClient;
};

export const connectWebSocket = () => {
  const client = getWebSocketClient();
  client.connect();
  return client;
};

export const disconnectWebSocket = () => {
  if (wsClient) {
    wsClient.disconnect();
  }
};
