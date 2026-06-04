/**
 * Gemini AI 服务
 * 使用 Google Gemini API 生成 AI 解释
 */

import { GoogleGenAI } from '@google/genai';

const ai = new GoogleGenAI({ apiKey: import.meta.env.VITE_GEMINI_API_KEY });

/**
 * 获取 AI 解释 (异步)
 */
export const getAIExplanation = async (
  symbol: string,
  score: number,
  reason: string
): Promise<string> => {
  try {
    const prompt = `你是一个量化交易 AI 智能体。请用中文解释 ${symbol} 的交易信号逻辑，其 AI 评分为 ${score}，检测到的原因为 "${reason}"。请保持专业、简洁，像一个战术顾问。字数控制在 80 字以内。`;

    const response = await ai.models.generateContent({
      model: 'gemini-3-flash-preview',
      contents: prompt,
      config: {
        systemInstruction:
          "你是 Rabbit Hunter V4.3 神经引擎。在适当的地方使用技术术语，如 '黄金影线' (Golden Wick)、'ATR 吊灯止损' (ATR Chandelier)、'订单块' (Order Block) 和 '流动性真空' (Liquidity Void)。",
        temperature: 0.7
      }
    });

    return response.text || '正在分析交易信号...';
  } catch (error) {
    console.error('AI Explanation Error:', error);
    // 降级到本地默认文本
    return `AI: 在 ${symbol} 上检测到交易信号。评分 ${score} 表示高概率设置。`;
  }
};

/**
 * 缓存 AI 解释 (避免重复调用)
 */
const explanationCache = new Map<string, { text: string; timestamp: number }>();
const CACHE_TTL = 5 * 60 * 1000; // 5 分钟

export const getAIExplanationCached = async (
  symbol: string,
  score: number,
  reason: string
): Promise<string> => {
  const cacheKey = `${symbol}_${score}_${reason}`;

  // 检查缓存
  const cached = explanationCache.get(cacheKey);
  if (cached && Date.now() - cached.timestamp < CACHE_TTL) {
    console.log('[AI Cache] Hit:', cacheKey);
    return cached.text;
  }

  // 获取新的解释
  const explanation = await getAIExplanation(symbol, score, reason);

  // 存储到缓存
  explanationCache.set(cacheKey, {
    text: explanation,
    timestamp: Date.now()
  });

  return explanation;
};

/**
 * 清空缓存
 */
export const clearAIExplanationCache = (): void => {
  explanationCache.clear();
};
