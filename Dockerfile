FROM mcr.microsoft.com/playwright/python:v1.40.0-jammy

# 设置工作目录
WORKDIR /app

# 使用阿里云镜像源
RUN sed -i 's/archive.ubuntu.com/mirrors.aliyun.com/g' /etc/apt/sources.list && \
    sed -i 's/security.ubuntu.com/mirrors.aliyun.com/g' /etc/apt/sources.list

# 安装额外的系统依赖
RUN apt-get update && apt-get install -y \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# 配置pip国内源
RUN pip config set global.index-url https://mirrors.aliyun.com/pypi/simple/ && \
    pip config set install.trusted-host mirrors.aliyun.com

# 复制项目文件
COPY requirements.txt .
COPY . .

# 安装Python依赖
RUN pip install --no-cache-dir -r requirements.txt

# 设置环境变量
ENV PYTHONUNBUFFERED=1 \
    FLASK_ENV=development \
    FLASK_APP=app.py

# 创建必要的目录
RUN mkdir -p /app/downloads /app/logs

# 暴露端口
EXPOSE 5000

# 启动命令
CMD ["python", "app.py"] 