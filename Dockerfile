# 甲骨文 AI 助教（龟宝）· 零依赖镜像
# 没有 pip install：项目只用 Python 标准库，构建应当几秒完成
FROM python:3.13-slim

WORKDIR /app

# 只拷运行所需（密钥、截图、申报材料由 .dockerignore 挡在外面）
COPY src ./src
COPY web ./web
COPY data ./data

ENV PYTHONUNBUFFERED=1 \
    ZQ_HOST=0.0.0.0 \
    PORT=8770

EXPOSE 8770

# 模型/Dify 的 key 一律走平台环境变量注入，绝不进镜像
CMD ["python", "src/server.py"]
