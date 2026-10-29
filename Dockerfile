# HVAC Energy Agent — FastAPI 后端镜像
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# 依赖先行（利用层缓存）
COPY requirements.txt .
RUN pip install -i https://pypi.tuna.tsinghua.edu.cn/simple --trusted-host pypi.tuna.tsinghua.edu.cn -r requirements.txt \
    || pip install -r requirements.txt

# 业务代码（调研表模板/skills 为运行必需资产）
COPY core ./core
COPY config ./config
COPY agent ./agent
COPY evaluation ./evaluation
COPY apps/api ./apps/api
COPY simulation ./simulation
COPY quote_module ./quote_module
COPY .claude/skills .claude/skills
COPY "00_sample/模板测算表" "00_sample/模板测算表"

# tmp：会话工作目录（生产挂卷）；data：SQLite 开发库（生产用 Postgres 不需要）
RUN mkdir -p tmp data
VOLUME ["/app/tmp"]

EXPOSE 8000
CMD ["uvicorn", "apps.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
