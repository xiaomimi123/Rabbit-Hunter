# Rabbit Hunter 前端 — multi-stage 构建
#   Stage 1: Node 构建 → vite build
#   Stage 2: nginx 静态服务 80 端口

# ─── Stage 1: build ──────────────────────────────────────────────────
FROM node:20-alpine AS builder

WORKDIR /app

# package*.json 先单独 copy 触发 layer cache
COPY package.json package-lock.json* ./
# React 19 + @testing-library/react 14 有 peer 冲突，沿用 --legacy-peer-deps
RUN npm ci --no-audit --no-fund --legacy-peer-deps || \
    npm install --no-audit --no-fund --legacy-peer-deps

# Vite build：构建时把 VITE_* 变量注入 bundle
ARG VITE_API_URL=/api
ARG VITE_WS_URL
ARG VITE_API_TOKEN
ENV VITE_API_URL=${VITE_API_URL} \
    VITE_WS_URL=${VITE_WS_URL} \
    VITE_API_TOKEN=${VITE_API_TOKEN}

COPY . .
RUN npm run build


# ─── Stage 2: serve ──────────────────────────────────────────────────
FROM nginx:1.27-alpine

# 自定义 nginx config：SPA fallback + /api、/ws/v43 反代到 api 容器
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=builder /app/dist /usr/share/nginx/html

EXPOSE 80

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD wget -qO- http://127.0.0.1/ >/dev/null 2>&1 || exit 1

CMD ["nginx", "-g", "daemon off;"]
