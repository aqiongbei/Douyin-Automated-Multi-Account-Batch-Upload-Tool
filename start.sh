#!/bin/bash

# 抖音上传一键启动脚本

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 配置
COMPOSE_FILE="docker-compose-auto.yml"
SAFE_COMPOSE_FILE="docker-compose-safe.yml"
CONTAINER_NAME="douyin-upload-auto"
SAFE_CONTAINER_NAME="douyin-upload-safe"
SERVICE_URL="http://0.0.0.0:5000"

# 检查Docker是否运行
check_docker() {
    if ! docker info >/dev/null 2>&1; then
        echo -e "${RED}❌ Docker未运行或权限不足${NC}"
        echo "请检查Docker服务状态或使用sudo运行此脚本"
        exit 1
    fi
}

# 启动服务
start_service() {
    echo -e "${BLUE}🚀 启动抖音上传服务...${NC}"
    
    # 创建必要目录
    mkdir -p cookie videos downloads database logs
    
    # 启动容器
    docker-compose -f $COMPOSE_FILE up -d
    
    if [ $? -eq 0 ]; then
        echo -e "${GREEN}✅ 服务启动成功！${NC}"
        echo ""
        echo -e "${YELLOW}📋 服务信息:${NC}"
        echo -e "🌐 本地访问: http://localhost:5000"
        echo -e "🌍 外网访问: http://YOUR_SERVER_IP:5000"
        echo -e "📊 容器名称: ${CONTAINER_NAME}"
        echo ""
        echo -e "${YELLOW}💡 常用命令:${NC}"
        echo -e "查看日志: ./start.sh logs"
        echo -e "停止服务: ./start.sh stop"
        echo -e "重启服务: ./start.sh restart"
        echo ""
        
        # 等待服务启动
        echo -e "${BLUE}⏳ 等待服务完全启动...${NC}"
        sleep 5
        
        # 检查服务健康状态
        check_health
    else
        echo -e "${RED}❌ 服务启动失败${NC}"
        echo "请查看错误信息或运行 './start.sh logs' 查看详细日志"
        exit 1
    fi
}

# 停止服务
stop_service() {
    echo -e "${BLUE}🛑 停止抖音上传服务...${NC}"
    docker-compose -f $COMPOSE_FILE down 2>/dev/null || true
    docker-compose -f $SAFE_COMPOSE_FILE down 2>/dev/null || true
    # 强制停止所有相关容器
    docker stop $(docker ps -q --filter "name=douyin") 2>/dev/null || true
    
    echo -e "${GREEN}✅ 服务已停止${NC}"
}

# 安全模式启动
start_safe_service() {
    echo -e "${YELLOW}🔧 使用安全模式启动（原始镜像）...${NC}"
    
    # 创建必要目录
    mkdir -p cookie videos downloads database logs
    
    # 启动容器
    docker-compose -f $SAFE_COMPOSE_FILE up -d
    
    if [ $? -eq 0 ]; then
        echo -e "${GREEN}✅ 服务启动成功（安全模式）！${NC}"
        echo ""
        echo -e "${YELLOW}📋 服务信息:${NC}"
        echo -e "🌐 本地访问: http://localhost:5000"
        echo -e "🌍 外网访问: http://YOUR_SERVER_IP:5000"
        echo -e "📊 容器名称: ${SAFE_CONTAINER_NAME}"
        echo ""
        echo -e "${YELLOW}💡 常用命令:${NC}"
        echo -e "查看日志: ./start.sh logs-safe"
        echo -e "停止服务: ./start.sh stop"
        echo ""
        
        # 等待服务启动
        echo -e "${BLUE}⏳ 等待依赖安装和服务启动...${NC}"
        sleep 10
        
        # 检查服务健康状态
        check_health_safe
    else
        echo -e "${RED}❌ 安全模式服务启动失败${NC}"
        echo "请查看错误信息或运行 './start.sh logs-safe' 查看详细日志"
        exit 1
    fi
}

# 检查安全模式服务健康状态
check_health_safe() {
    echo -e "${BLUE}🏥 检查安全模式服务健康状态...${NC}"
    
    # 检查容器是否运行
    if docker ps --filter "name=${SAFE_CONTAINER_NAME}" --filter "status=running" | grep -q ${SAFE_CONTAINER_NAME}; then
        echo -e "${GREEN}✅ 容器运行正常${NC}"
        
        # 检查Web服务是否响应
        if curl -s --max-time 5 ${SERVICE_URL} >/dev/null 2>&1; then
            echo -e "${GREEN}✅ Web服务响应正常${NC}"
            echo -e "${GREEN}🎉 服务完全正常，可以访问: ${SERVICE_URL}${NC}"
        else
            echo -e "${YELLOW}⚠️  Web服务可能还在启动中，请稍等片刻后再试${NC}"
        fi
    else
        echo -e "${RED}❌ 容器未运行${NC}"
    fi
}

# 查看安全模式日志
show_safe_logs() {
    echo -e "${BLUE}📝 安全模式服务日志 (按Ctrl+C退出):${NC}"
    docker-compose -f $SAFE_COMPOSE_FILE logs -f --tail=50
}

# 重启服务
restart_service() {
    echo -e "${BLUE}🔄 重启抖音上传服务...${NC}"
    stop_service
    sleep 2
    start_service
}

# 查看服务状态
show_status() {
    echo -e "${BLUE}📊 服务状态:${NC}"
    docker-compose -f $COMPOSE_FILE ps
    
    echo ""
    echo -e "${BLUE}🔍 容器详细信息:${NC}"
    docker ps --filter "name=${CONTAINER_NAME}" --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
    
    echo ""
    check_health
}

# 查看日志
show_logs() {
    echo -e "${BLUE}📝 服务日志 (按Ctrl+C退出):${NC}"
    docker-compose -f $COMPOSE_FILE logs -f --tail=50
}

# 检查服务健康状态
check_health() {
    echo -e "${BLUE}🏥 检查服务健康状态...${NC}"
    
    # 检查容器是否运行
    if docker ps --filter "name=${CONTAINER_NAME}" --filter "status=running" | grep -q ${CONTAINER_NAME}; then
        echo -e "${GREEN}✅ 容器运行正常${NC}"
        
        # 检查Web服务是否响应
        if curl -s --max-time 5 ${SERVICE_URL} >/dev/null 2>&1; then
            echo -e "${GREEN}✅ Web服务响应正常${NC}"
            echo -e "${GREEN}🎉 服务完全正常，可以访问: ${SERVICE_URL}${NC}"
        else
            echo -e "${YELLOW}⚠️  Web服务可能还在启动中，请稍等片刻后再试${NC}"
        fi
    else
        echo -e "${RED}❌ 容器未运行${NC}"
    fi
}

# 进入容器
enter_container() {
    echo -e "${BLUE}🐚 进入容器...${NC}"
    docker exec -it ${CONTAINER_NAME} bash
}

# 更新镜像
update_image() {
    echo -e "${BLUE}🔄 更新镜像...${NC}"
    echo -e "${YELLOW}⚠️  这将停止当前服务并重新构建镜像${NC}"
    read -p "确认继续？(y/N): " -n 1 -r
    echo
    
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        stop_service
        
        # 重新构建镜像
        echo -e "${BLUE}🔨 重新构建镜像...${NC}"
        docker build -t douyin-upload:latest .
        
        if [ $? -eq 0 ]; then
            echo -e "${GREEN}✅ 镜像构建成功${NC}"
            start_service
        else
            echo -e "${RED}❌ 镜像构建失败${NC}"
        fi
    fi
}

# 清理资源
cleanup() {
    echo -e "${YELLOW}⚠️  这将删除所有相关容器、镜像和卷${NC}"
    read -p "确认继续？(y/N): " -n 1 -r
    echo
    
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        echo -e "${BLUE}🧹 清理资源...${NC}"
        docker-compose -f $COMPOSE_FILE down -v --rmi all
        echo -e "${GREEN}✅ 清理完成${NC}"
    fi
}

# 显示帮助信息
show_help() {
    echo -e "${BLUE}🤖 抖音上传服务管理脚本${NC}"
    echo ""
    echo "用法: $0 [命令]"
    echo ""
    echo "命令:"
    echo "  start      启动服务（自定义镜像）"
    echo "  safe       启动服务（安全模式，原始镜像）"
    echo "  stop       停止服务"
    echo "  restart    重启服务"
    echo "  status     查看状态"
    echo "  logs       查看日志"
    echo "  logs-safe  查看安全模式日志"
    echo "  enter      进入容器"
    echo "  update     更新镜像"
    echo "  clean      清理资源"
    echo "  health     检查健康状态"
    echo "  help       显示帮助"
    echo ""
    echo "示例:"
    echo "  $0 start     # 启动服务"
    echo "  $0 logs      # 查看实时日志"
    echo "  $0 status    # 查看服务状态"
}

# 主逻辑
main() {
    check_docker
    
    case "${1:-help}" in
        start)
            start_service
            ;;
        safe)
            start_safe_service
            ;;
        stop)
            stop_service
            ;;
        restart)
            restart_service
            ;;
        status)
            show_status
            ;;
        logs)
            show_logs
            ;;
        logs-safe)
            show_safe_logs
            ;;
        enter)
            enter_container
            ;;
        update)
            update_image
            ;;
        clean)
            cleanup
            ;;
        health)
            check_health
            ;;
        help|--help|-h)
            show_help
            ;;
        *)
            echo -e "${RED}❌ 未知命令: $1${NC}"
            echo ""
            show_help
            exit 1
            ;;
    esac
}

main "$@" 