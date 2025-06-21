# 使用Playwright官方Python镜像作为基础镜像
FROM mcr.microsoft.com/playwright/python:v1.40.0-jammy

# 设置工作目录
WORKDIR /app

# 设置环境变量
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# 使用清华大学镜像源
RUN sed -i 's/archive.ubuntu.com/mirrors.tuna.tsinghua.edu.cn/g' /etc/apt/sources.list && \
    sed -i 's/security.ubuntu.com/mirrors.tuna.tsinghua.edu.cn/g' /etc/apt/sources.list

# 安装系统依赖
RUN apt-get update && apt-get install -y \
    unrar \
    p7zip-full \
    && rm -rf /var/lib/apt/lists/*

# 复制项目文件
COPY . /app/

# 设置pip国内源
RUN pip config set global.index-url https://pypi.tuna.tsinghua.edu.cn/simple && \
    pip config set global.trusted-host pypi.tuna.tsinghua.edu.cn

# 安装Python依赖
RUN pip install --no-cache-dir -r requirements.txt

# 安装Playwright浏览器（基础镜像已经包含了浏览器，所以这步可以跳过）
# RUN playwright install chromium

# 暴露端口（根据您的应用需求设置端口）
EXPOSE 5000

# 设置启动命令
CMD ["python", "main.py"] 