/**
 * 数据缓存工具
 * 用于缓存 API 响应，减少请求次数
 */

interface CacheEntry<T> {
  data: T;
  timestamp: number;
  ttl: number; // 缓存有效期（毫秒）
}

class DataCache {
  private cache: Map<string, CacheEntry<any>> = new Map();
  private defaultTTL = 5000; // 默认 5 秒

  /**
   * 获取缓存数据
   */
  get<T>(key: string): T | null {
    const entry = this.cache.get(key);
    if (!entry) {
      return null;
    }

    // 检查是否过期
    const now = Date.now();
    if (now - entry.timestamp > entry.ttl) {
      this.cache.delete(key);
      return null;
    }

    return entry.data as T;
  }

  /**
   * 设置缓存数据
   */
  set<T>(key: string, data: T, ttl: number = this.defaultTTL): void {
    this.cache.set(key, {
      data,
      timestamp: Date.now(),
      ttl,
    });
  }

  /**
   * 删除缓存
   */
  delete(key: string): void {
    this.cache.delete(key);
  }

  /**
   * 清空所有缓存
   */
  clear(): void {
    this.cache.clear();
  }

  /**
   * 清理过期缓存
   */
  cleanup(): void {
    const now = Date.now();
    for (const [key, entry] of this.cache.entries()) {
      if (now - entry.timestamp > entry.ttl) {
        this.cache.delete(key);
      }
    }
  }
}

// 全局缓存实例
export const dataCache = new DataCache();

// 定期清理过期缓存
if (typeof window !== 'undefined') {
  setInterval(() => {
    dataCache.cleanup();
  }, 60000); // 每分钟清理一次
}

/**
 * 带缓存的 fetch 函数
 */
export async function cachedFetch<T>(
  url: string,
  options?: RequestInit,
  ttl: number = 5000
): Promise<T> {
  const cacheKey = `fetch:${url}:${JSON.stringify(options)}`;
  
  // 尝试从缓存获取
  const cached = dataCache.get<T>(cacheKey);
  if (cached !== null) {
    return cached;
  }

  // 发起请求
  const response = await fetch(url, options);
  if (!response.ok) {
    throw new Error(`HTTP error! status: ${response.status}`);
  }

  const data = await response.json();
  
  // 存入缓存
  dataCache.set(cacheKey, data, ttl);
  
  return data;
}

