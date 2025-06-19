#!/bin/bash

echo "🚀 开始快速安装Playwright环境（使用国内镜像源）"

# 配置pip国内源
echo "📦 配置pip国内源..."
mkdir -p ~/.pip
cat > ~/.pip/pip.conf << EOF
[global]
index-url = https://pypi.tuna.tsinghua.edu.cn/simple
trusted-host = pypi.tuna.tsinghua.edu.cn
timeout = 120
EOF

# 更新apt源为国内镜像
echo "🔄 更新系统包管理器..."
sed -i 's/archive.ubuntu.com/mirrors.aliyun.com/g' /etc/apt/sources.list
sed -i 's/security.ubuntu.com/mirrors.aliyun.com/g' /etc/apt/sources.list
apt-get update

# 安装基础依赖
echo "📥 安装基础依赖..."
apt-get install -y wget curl

# 升级pip
echo "⬆️ 升级pip..."
python -m pip install --upgrade pip -i https://pypi.tuna.tsinghua.edu.cn/simple

# 安装playwright
echo "🎭 安装Playwright..."
pip install playwright -i https://pypi.tuna.tsinghua.edu.cn/simple

# 设置playwright下载镜像
echo "🌐 配置Playwright浏览器下载镜像..."
export PLAYWRIGHT_DOWNLOAD_HOST=https://npmmirror.com/mirrors/playwright

# 安装浏览器
echo "🔽 下载浏览器（使用国内镜像）..."
python -m playwright install chromium

# 安装常用依赖
echo "📦 安装常用Python包..."
pip install -i https://pypi.tuna.tsinghua.edu.cn/simple \
    flask \
    requests \
    asyncio \
    websockets \
    aiohttp

echo "✅ 安装完成！"
echo "�� 现在可以运行您的抖音上传脚本了" 