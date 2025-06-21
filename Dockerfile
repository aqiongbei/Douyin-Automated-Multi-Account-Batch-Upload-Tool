FROM python:3.9-slim

# 设置工作目录
WORKDIR /app

# 安装系统依赖
RUN apt-get update && apt-get install -y \
    build-essential \
    ffmpeg \
    chromium \
    chromium-driver \
    xvfb \
    && rm -rf /var/lib/apt/lists/*

# 设置Chrome环境变量
ENV CHROME_BIN=/usr/bin/chromium \
    CHROME_DRIVER=/usr/bin/chromedriver \
    DISPLAY=:99

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

# 设置权限
RUN chmod +x start.sh

# 暴露端口
EXPOSE 5000

# 启动命令
CMD ["./start.sh"] 