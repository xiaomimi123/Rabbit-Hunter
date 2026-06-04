/**
 * API 请求拦截器
 * 提供统一的请求/响应处理、错误处理、重试机制
 */

const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000/api';

interface RequestConfig extends RequestInit {
  retries?: number;
  retryDelay?: number;
  timeout?: number;
}

interface ApiError extends Error {
  status?: number;
  statusText?: string;
  response?: any;
}

// 请求去重：防止同一请求被多次发起
const pendingRequests = new Map<string, Promise<any>>();

// 生成请求唯一标识
function getRequestKey(endpoint: string, options: RequestInit = {}): string {
  const method = options.method || 'GET';
  const body = options.body ? JSON.stringify(options.body) : '';
  return `${method}:${endpoint}:${body}`;
}

/**
 * 创建带超时的 fetch
 */
async function fetchWithTimeout(
  url: string,
  options: RequestInit = {},
  timeout: number = 10000
): Promise<Response> {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), timeout);

  try {
    const response = await fetch(url, {
      ...options,
      signal: controller.signal,
    });
    clearTimeout(timeoutId);
    return response;
  } catch (error) {
    clearTimeout(timeoutId);
    if (error instanceof Error && error.name === 'AbortError') {
      throw new Error('请求超时');
    }
    throw error;
  }
}

/**
 * 请求重试
 */
async function fetchWithRetry(
  url: string,
  config: RequestConfig,
  retries: number = 2, // 减少默认重试次数
  retryDelay: number = 1000
): Promise<Response> {
  let lastError: Error | null = null;

  for (let attempt = 0; attempt <= retries; attempt++) {
    try {
      const timeout = config.timeout || 5000; // 减少超时时间
      const response = await fetchWithTimeout(url, config, timeout);

      // 如果是 5xx 错误，重试
      if (response.status >= 500 && attempt < retries) {
        await new Promise((resolve) => setTimeout(resolve, retryDelay * (attempt + 1)));
        continue;
      }

      return response;
    } catch (error) {
      lastError = error instanceof Error ? error : new Error('Unknown error');

      // 检查是否是资源不足错误（不应该重试）
      const errorMessage = lastError.message || '';
      if (
        errorMessage.includes('ERR_INSUFFICIENT_RESOURCES') ||
        errorMessage.includes('Failed to fetch') ||
        errorMessage.includes('NetworkError')
      ) {
        // 连接错误，不重试，直接抛出
        throw new Error('无法连接到服务器，请检查后端服务是否启动');
      }

      // 只有 5xx 错误才重试，网络连接错误不重试
      if (attempt < retries) {
        await new Promise((resolve) => setTimeout(resolve, retryDelay * (attempt + 1)));
        continue;
      }
    }
  }

  throw lastError || new Error('请求失败');
}

/**
 * 统一的 API 请求函数
 */
export async function apiRequest<T = any>(
  endpoint: string,
  options: RequestConfig = {}
): Promise<T> {
  const url = endpoint.startsWith('http') ? endpoint : `${API_BASE}${endpoint}`;

  // 请求去重：如果相同的请求正在进行，返回同一个 Promise
  const requestKey = getRequestKey(endpoint, options);
  if (pendingRequests.has(requestKey)) {
    // 静默去重，不输出日志（避免控制台噪音）
    return pendingRequests.get(requestKey)!;
  }

  // 请求拦截：添加默认 headers
  const headers = new Headers(options.headers);
  if (!headers.has('Content-Type') && options.method !== 'GET') {
    headers.set('Content-Type', 'application/json');
  }

  const config: RequestConfig = {
    ...options,
    headers,
    retries: options.retries ?? 1, // 默认只重试 1 次
    retryDelay: options.retryDelay ?? 1000,
    timeout: options.timeout ?? 5000, // 减少超时时间
  };

  // 创建请求 Promise
  const requestPromise = (async () => {
    try {
      // 执行请求（带重试）
      const response = await fetchWithRetry(url, config, config.retries, config.retryDelay);

      // 响应拦截：处理错误状态码
      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        const error: ApiError = new Error(
          errorData.detail || errorData.message || `HTTP ${response.status}: ${response.statusText}`
        );
        error.status = response.status;
        error.statusText = response.statusText;
        error.response = errorData;
        throw error;
      }

      // 解析响应
      const data = await response.json();
      return data as T;
    } catch (error) {
      // 错误处理
      if (error instanceof Error) {
        // 网络错误
        if (error.message === '请求超时') {
          throw new Error('请求超时，请检查网络连接或后端服务是否启动');
        }
        if (
          error.message.includes('Failed to fetch') ||
          error.message.includes('ERR_INSUFFICIENT_RESOURCES') ||
          error.message.includes('无法连接到服务器')
        ) {
          throw new Error('无法连接到后端服务，请确保后端 API 已启动（http://localhost:8000）');
        }
        throw error;
      }
      throw new Error('未知错误');
    } finally {
      // 请求完成后从 pending 中移除
      pendingRequests.delete(requestKey);
    }
  })();

  // 将请求添加到 pending
  pendingRequests.set(requestKey, requestPromise);

  return requestPromise;
}

/**
 * GET 请求
 */
export async function apiGet<T = any>(endpoint: string, options?: RequestConfig): Promise<T> {
  return apiRequest<T>(endpoint, {
    ...options,
    method: 'GET',
  });
}

/**
 * POST 请求
 */
export async function apiPost<T = any>(
  endpoint: string,
  data?: any,
  options?: RequestConfig
): Promise<T> {
  return apiRequest<T>(endpoint, {
    ...options,
    method: 'POST',
    body: data ? JSON.stringify(data) : undefined,
  });
}

/**
 * PUT 请求
 */
export async function apiPut<T = any>(
  endpoint: string,
  data?: any,
  options?: RequestConfig
): Promise<T> {
  return apiRequest<T>(endpoint, {
    ...options,
    method: 'PUT',
    body: data ? JSON.stringify(data) : undefined,
  });
}

/**
 * DELETE 请求
 */
export async function apiDelete<T = any>(endpoint: string, options?: RequestConfig): Promise<T> {
  return apiRequest<T>(endpoint, {
    ...options,
    method: 'DELETE',
  });
}

