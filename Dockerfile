# Rabbit Hunter — Python 后端镜像（API + Collector 共用）
#
# 通过 docker-compose 的 command 覆盖切换两种模式：
#   - api:       uvicorn api.main:app --host 0.0.0.0 --port 8000
#   - collector: python -m scripts.tasks.collector_main
#
# 二者共享同一镜像、同一代码、同一依赖；只是入口不同。
# 这避免了"两个 Dockerfile 维护一份依赖"的麻烦。

FROM python:3.11-slim

# 注意：刻意**不**装 build-essential / curl —
#   - numpy / pandas / ccxt 等都有 manylinux wheel，python:3.11-slim 自带 ca-certificates
#   - healthcheck 用 python -c 替代 curl，避免 apt 步骤把 Docker VM 内存撑爆
# 这让构建在 Docker Desktop 默认 RAM 配置下也能跑过。

# 不缓存 pip 包，镜像更小；不写 .pyc
# PYTHONPATH 包含 /app（让 `from scripts.xxx` 工作）和 /app/scripts
# （让 v43_kill_queue_manager 等内部 `from v43_feature_extractor` 这种相对裸名 import 工作）
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONPATH=/app:/app/scripts

WORKDIR /app

# 先复制 requirements.txt 单独安装，触发 docker layer cache：
# 改代码不重装依赖，启动飞快。
COPY requirements.txt ./
RUN pip install -r requirements.txt

# 复制项目代码（注意 .dockerignore 已经排除前端 / data / .git）
COPY scripts/ ./scripts/
COPY api/ ./api/

# 持久化 SQLite + AI 学习日志在这里
RUN mkdir -p /app/data
VOLUME ["/app/data"]

# v45：默认绑 0.0.0.0 + 显式 fail-open（compose 把 ports 限到 host 127.0.0.1）
ENV API_BIND_HOST=0.0.0.0 \
    API_PORT=8000 \
    API_ALLOW_REMOTE_NO_AUTH=true \
    AI_TRADE_LOG_PATH=/app/data/ai_trade_log.jsonl

EXPOSE 8000

# Healthcheck — /healthz 是 v45 的无鉴权探活端点
# 用 python -c 而不是 curl，省一个 apt 包
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:'+__import__('os').environ.get('API_PORT','8000')+'/healthz').status==200 else 1)" || exit 1

# 默认入口 = API；compose 中可以用 command 覆盖为 collector_main
CMD ["python", "-m", "uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
