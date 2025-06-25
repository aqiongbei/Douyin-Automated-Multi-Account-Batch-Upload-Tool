from flask import Flask, render_template, request, jsonify, send_from_directory, redirect, url_for, session, flash
from conf.auth import login_required, verify_login, load_auth_config, save_auth_config
import os
import json
import asyncio
import threading
from datetime import datetime, timedelta
from main import douyin_cookie_gen, douyin_setup, DouYinVideo
import time
import uuid
import shutil
import zipfile
import tempfile
from utils.log import douyin_logger
from utils.history_db import init_db, log_upload_history, get_history, get_upload_count_last_hour
from utils.proxy_manager import proxy_manager
import base64
import io
from flask_socketio import SocketIO, emit
from collections import defaultdict
import weakref
import sys
import subprocess
import atexit
import signal

# 尝试导入压缩包解压库
try:
    import rarfile
    RARFILE_AVAILABLE = True
except ImportError:
    RARFILE_AVAILABLE = False
    print("警告: rarfile 库未安装，无法解压 .rar 文件")

try:
    import py7zr
    PY7ZR_AVAILABLE = True
except ImportError:
    PY7ZR_AVAILABLE = False
    print("警告: py7zr 库未安装，无法解压 .7z 文件")

# Downloader API 配置 - 使用HTTP调用而不是直接导入
import requests
import aiohttp
import httpx
import subprocess
import atexit
import signal
import threading
import queue

# Downloader API 基础配置
DOWNLOADER_API_BASE = "http://127.0.0.1:5555"
DOWNLOADER_AVAILABLE = True
downloader_process = None  # 存储Downloader进程
downloader_logs = []  # 存储日志
log_queue = queue.Queue()  # 日志队列
max_log_lines = 1000  # 最大日志行数

# 下载控制变量
download_stop_flag = False  # 下载停止标志
current_download_thread = None  # 当前下载线程

def start_downloader_service():
    """启动Downloader服务"""
    global downloader_process
    
    if downloader_process and downloader_process.poll() is None:
        douyin_logger.info("Downloader服务已在运行")
        return True
    
    try:
        douyin_logger.info("🚀 正在启动Downloader服务...")
        
        # 启动Downloader进程
        downloader_path = os.path.join(os.path.dirname(__file__), 'Downloader')
        main_py = os.path.join(downloader_path, 'main.py')
        
        if not os.path.exists(main_py):
            douyin_logger.error(f"❌ 找不到Downloader main.py文件: {main_py}")
            return False
        
        # 使用subprocess启动Downloader，并自动选择Web API模式(选项7)
        downloader_process = subprocess.Popen(
            [sys.executable, main_py],
            cwd=downloader_path,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,  # 将stderr重定向到stdout
            text=True,
            bufsize=1,  # 行缓冲
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == 'nt' else 0
        )
        
        # 启动日志读取线程
        start_log_reader()
        
        # 向Downloader进程发送选项7(Web API模式)
        time.sleep(2)  # 等待进程启动
        downloader_process.stdin.write("7\n")
        downloader_process.stdin.flush()
        
        # 添加启动日志
        add_log("INFO", "Downloader服务启动中，选择Web API模式...")
        
        # 等待服务启动
        max_wait = 30  # 最多等待30秒
        for i in range(max_wait):
            time.sleep(1)
            if check_downloader_status():
                douyin_logger.info("✅ Downloader服务启动成功!")
                return True
        
        douyin_logger.error("❌ Downloader服务启动超时")
        return False
        
    except Exception as e:
        douyin_logger.error(f"❌ 启动Downloader服务失败: {str(e)}")
        return False

def stop_downloader_service():
    """停止Downloader服务"""
    global downloader_process
    
    if downloader_process and downloader_process.poll() is None:
        try:
            douyin_logger.info("🛑 正在停止Downloader服务...")
            add_log("INFO", "停止Downloader服务...")
            
            if os.name == 'nt':  # Windows
                # 使用taskkill强制结束进程树
                subprocess.run(['taskkill', '/F', '/T', '/PID', str(downloader_process.pid)], 
                             capture_output=True)
            else:  # Unix/Linux/Mac
                downloader_process.terminate()
                downloader_process.wait(timeout=5)
            
            downloader_process = None
            douyin_logger.info("✅ Downloader服务已停止")
            add_log("SUCCESS", "Downloader服务已停止")
            
        except Exception as e:
            error_msg = f"停止Downloader服务失败: {str(e)}"
            douyin_logger.error(f"❌ {error_msg}")
            add_log("ERROR", error_msg)

# 注册退出时清理函数
def cleanup_on_exit():
    """程序退出时清理"""
    stop_downloader_service()

atexit.register(cleanup_on_exit)

# 处理Ctrl+C信号
def signal_handler(sig, frame):
    """处理中断信号"""
    print("\n⚠️  收到中断信号，正在安全退出...")
    stop_downloader_service()
    sys.exit(0)

signal.signal(signal.SIGINT, signal_handler)
if hasattr(signal, 'SIGTERM'):
    signal.signal(signal.SIGTERM, signal_handler)

def add_log(level, message):
    """添加日志到队列"""
    global downloader_logs
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    log_entry = f"[{timestamp}] {level}: {message}"
    
    downloader_logs.append(log_entry)
    
    # 限制日志数量
    if len(downloader_logs) > max_log_lines:
        downloader_logs = downloader_logs[-max_log_lines:]
    
    # 也输出到控制台
    print(f"📝 Downloader: {log_entry}")

def start_log_reader():
    """启动日志读取线程"""
    if downloader_process and downloader_process.stdout:
        def read_logs():
            try:
                while downloader_process and downloader_process.poll() is None:
                    try:
                        line = downloader_process.stdout.readline()
                        if line:
                            line = line.strip()
                            if line:
                                # 简单的日志级别判断
                                if any(word in line.lower() for word in ['error', '错误', 'failed', '失败']):
                                    add_log("ERROR", line)
                                elif any(word in line.lower() for word in ['warning', '警告', 'warn']):
                                    add_log("WARNING", line)
                                elif any(word in line.lower() for word in ['success', '成功', 'started', '启动']):
                                    add_log("SUCCESS", line)
                                else:
                                    add_log("INFO", line)
                        else:
                            # 如果没有更多数据，稍作等待
                            time.sleep(0.1)
                    except Exception as e:
                        # 如果读取出错，等待一会儿再继续
                        time.sleep(0.5)
                        continue
                        
            except Exception as e:
                add_log("ERROR", f"日志读取异常: {str(e)}")
        
        log_thread = threading.Thread(target=read_logs, daemon=True)
        log_thread.start()

def check_downloader_status():
    """检查Downloader服务是否运行"""
    global current_download_thread
    
    # 如果正在下载，且下载线程活跃，假设服务正常
    if current_download_thread and current_download_thread.is_alive():
        return True
    
    try:
        # 使用docs端点检查，因为根路径会重定向
        response = requests.get(f"{DOWNLOADER_API_BASE}/docs", timeout=3)
        return response.status_code == 200
    except requests.exceptions.RequestException as e:
        douyin_logger.debug(f"Downloader状态检查失败: {str(e)}")
        return False
    except Exception as e:
        douyin_logger.debug(f"Downloader状态检查异常: {str(e)}")
        return False

async def call_downloader_api(endpoint, data=None, method="POST"):
    """异步调用Downloader API"""
    try:
        async with aiohttp.ClientSession() as session:
            url = f"{DOWNLOADER_API_BASE}{endpoint}"
            headers = {"Content-Type": "application/json"}
            
            douyin_logger.info(f"调用Downloader API: {method} {url}")
            if data:
                douyin_logger.info(f"请求数据: {data}")
            
            if method == "POST":
                async with session.post(url, json=data, headers=headers, timeout=30) as response:
                    douyin_logger.info(f"API响应状态: {response.status}")
                    if response.status != 200:
                        error_text = await response.text()
                        douyin_logger.error(f"API错误响应: {error_text}")
                        return {"error": f"HTTP {response.status}", "message": error_text}
                    
                    result = await response.json()
                    douyin_logger.info(f"API返回数据类型: {type(result)}")
                    douyin_logger.info(f"API返回数据示例: {str(result)[:500]}...")
                    return result
            elif method == "GET":
                async with session.get(url, timeout=30) as response:
                    douyin_logger.info(f"API响应状态: {response.status}")
                    if response.status != 200:
                        error_text = await response.text()
                        douyin_logger.error(f"API错误响应: {error_text}")
                        return {"error": f"HTTP {response.status}", "message": error_text}
                    
                    result = await response.json()
                    douyin_logger.info(f"API返回数据类型: {type(result)}")
                    return result
                    
    except asyncio.TimeoutError:
        douyin_logger.error(f"Downloader API调用超时: {endpoint}")
        return {"error": "请求超时", "message": "Downloader服务响应超时"}
    except Exception as e:
        douyin_logger.error(f"Downloader API调用失败: {endpoint}, 错误: {str(e)}")
        return {"error": "连接错误", "message": f"无法连接到Downloader服务: {str(e)}"}

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key-here'
socketio = SocketIO(
    app, 
    cors_allowed_origins="*",
    logger=False,  # 减少日志噪音
    engineio_logger=False,
    ping_timeout=60,  # 增加ping超时时间
    ping_interval=25,  # 降低ping间隔
    max_http_buffer_size=16 * 1024 * 1024,  # 增加缓冲区大小到16MB
    async_mode='threading'  # 使用线程模式提升稳定性
)

# 确保必要的目录存在
os.makedirs("videos", exist_ok=True)
os.makedirs("cookie", exist_ok=True)
os.makedirs("database", exist_ok=True)

async def safe_screenshot(page, **kwargs):
    """安全的截图函数，避免PNG格式的quality参数错误"""
    # 移除PNG格式不支持的参数
    safe_kwargs = {}
    for key, value in kwargs.items():
        if key == 'quality' and kwargs.get('type') == 'png':
            # PNG格式不支持quality参数，跳过
            continue
        safe_kwargs[key] = value
    
    # 如果没有指定type，默认使用png
    if 'type' not in safe_kwargs:
        safe_kwargs['type'] = 'png'
    
    return await page.screenshot(**safe_kwargs)

VIDEO_EXTS = ('.mp4', '.mov', '.avi', '.mkv', '.flv', '.webm')

# 异步任务队列
upload_tasks = []
is_uploading = False

# 压缩包解压任务状态
archive_extraction_tasks = {}  # 存储解压任务状态

# 多账号任务队列系统
multi_account_tasks = []  # 存储所有账号的任务配置
is_multi_uploading = False  # 多账号上传状态
upload_mode = "sequential"  # 上传模式：sequential(轮询) 或 concurrent(并发)
current_task_index = 0  # 当前轮询任务索引

# 多账号任务数据持久化
MULTI_TASKS_FILE = "database/multi_tasks.json"

def load_multi_tasks_from_file():
    """从文件加载多账号任务数据"""
    global multi_account_tasks
    try:
        if os.path.exists(MULTI_TASKS_FILE):
            with open(MULTI_TASKS_FILE, 'r', encoding='utf-8') as f:
                multi_account_tasks = json.load(f)
                douyin_logger.info(f"已加载 {len(multi_account_tasks)} 个多账号任务")
    except Exception as e:
        douyin_logger.error(f"加载多账号任务数据失败: {str(e)}")
        multi_account_tasks = []

def save_multi_tasks_to_file():
    """保存多账号任务数据到文件"""
    try:
        douyin_logger.info(f"DEBUG: 准备保存 {len(multi_account_tasks)} 个任务到文件")
        for task in multi_account_tasks:
            douyin_logger.info(f"DEBUG: 保存任务 - Cookie: {task['cookie']}, Status: {task['status']}, Completed: {task.get('completed_videos', 0)}/{task.get('total_videos', 0)}")
        os.makedirs(os.path.dirname(MULTI_TASKS_FILE), exist_ok=True)
        with open(MULTI_TASKS_FILE, 'w', encoding='utf-8') as f:
            json.dump(multi_account_tasks, f, ensure_ascii=False, indent=2)
        douyin_logger.info(f"DEBUG: 任务数据已成功保存到 {MULTI_TASKS_FILE}")
    except Exception as e:
        douyin_logger.error(f"保存多账号任务数据失败: {str(e)}")

def update_task_status(task, status, current_video=None, save_to_file=True, clear_video=False):
    """更新任务状态并可选择保存到文件"""
    old_status = task.get("status", "unknown")
    task["status"] = status
    
    # 处理current_video字段
    if clear_video or (current_video is not None):
        task["current_video"] = current_video if current_video is not None else ""
        
    douyin_logger.info(f"DEBUG: 更新任务状态 - Cookie: {task['cookie']}, 从 {old_status} -> {status}, 完成: {task.get('completed_videos', 0)}/{task.get('total_videos', 0)}")
    if save_to_file:
        save_multi_tasks_to_file()
        douyin_logger.info(f"DEBUG: 任务状态已保存到文件")

# 浏览器截图共享相关 - 添加线程安全保护
browser_data_lock = threading.RLock()  # 可重入锁
browser_screenshot_data = {}
active_browser_sessions = {}
browser_click_queue = defaultdict(list)  # 使用defaultdict避免KeyError
browser_pages = weakref.WeakValueDictionary()  # 使用弱引用避免内存泄漏

# 内存管理配置
MAX_SCREENSHOT_CACHE = 50  # 最大截图缓存数量
MAX_CLICK_QUEUE_SIZE = 100  # 最大点击队列大小
CLEANUP_INTERVAL = 300  # 清理间隔：5分钟

# 定期清理过期数据
def cleanup_memory():
    """定期清理过期数据，防止内存泄漏"""
    with browser_data_lock:
        current_time = time.time()
        
        # 清理过期的截图数据（超过10分钟）
        expired_sessions = []
        for session_id, data in browser_screenshot_data.items():
            if isinstance(data, dict) and 'timestamp' in data:
                if current_time - data['timestamp'] > 600:  # 10分钟
                    expired_sessions.append(session_id)
        
        for session_id in expired_sessions:
            try:
                del browser_screenshot_data[session_id]
                if session_id in active_browser_sessions:
                    del active_browser_sessions[session_id]
                if session_id in browser_click_queue:
                    del browser_click_queue[session_id]
                douyin_logger.info(f"清理过期会话: {session_id}")
            except KeyError:
                pass
        
        # 限制截图缓存大小
        if len(browser_screenshot_data) > MAX_SCREENSHOT_CACHE:
            # 保留最新的截图
            sorted_sessions = sorted(
                browser_screenshot_data.items(),
                key=lambda x: x[1].get('timestamp', 0) if isinstance(x[1], dict) else 0,
                reverse=True
            )
            # 删除最旧的截图
            for session_id, _ in sorted_sessions[MAX_SCREENSHOT_CACHE:]:
                try:
                    del browser_screenshot_data[session_id]
                except KeyError:
                    pass
        
        # 清理点击队列
        for session_id, queue in list(browser_click_queue.items()):
            if len(queue) > MAX_CLICK_QUEUE_SIZE:
                browser_click_queue[session_id] = queue[-MAX_CLICK_QUEUE_SIZE:]

# 启动定期清理线程
def start_cleanup_thread():
    def cleanup_worker():
        while True:
            try:
                time.sleep(CLEANUP_INTERVAL)
                cleanup_memory()
            except Exception as e:
                douyin_logger.error(f"内存清理过程中出错: {str(e)}")
    
    cleanup_thread = threading.Thread(target=cleanup_worker, daemon=True)
    cleanup_thread.start()
    douyin_logger.info("内存清理线程已启动")

# 初始化数据库
init_db()

# 启动内存清理
start_cleanup_thread()

# 加载多账号任务数据
load_multi_tasks_from_file()

# WebSocket事件处理
@socketio.on('connect')
def handle_connect():
    print(f"🔗 WebSocket客户端连接成功: {request.sid}")
    douyin_logger.info(f"WebSocket客户端连接: {request.sid}")
    emit('connected', {'data': '连接成功', 'client_id': request.sid})

@socketio.on('disconnect')
def handle_disconnect():
    print(f"❌ WebSocket客户端断开连接: {request.sid}")
    douyin_logger.info(f"WebSocket客户端断开连接: {request.sid}")

@socketio.on('test_message')
def handle_test_message(data):
    print(f"🧪 收到测试消息: {data}")
    douyin_logger.info(f"收到测试消息: {data}")
    emit('test_response', {'message': '测试消息已收到', 'timestamp': time.time(), 'original_data': data})

@socketio.on('request_browser_view')
def handle_request_browser_view(data):
    """客户端请求查看浏览器内容"""
    session_id = data.get('session_id', 'default')
    with browser_data_lock:
        if session_id in browser_screenshot_data:
            screenshot_data = browser_screenshot_data[session_id]
            
            # 确保screenshot_data是正确的格式
            if isinstance(screenshot_data, dict) and 'data' in screenshot_data:
                emit('browser_screenshot', {
                    'session_id': session_id,
                    'screenshot': screenshot_data['data'],
                    'timestamp': screenshot_data.get('timestamp', time.time())
                })
                print(f"📤 刷新请求: 发送截图数据到客户端, session_id={session_id}")
            else:
                # 如果数据格式不正确，直接发送原始数据
                emit('browser_screenshot', {
                    'session_id': session_id,
                    'screenshot': screenshot_data,
                    'timestamp': time.time()
                })
                print(f"📤 刷新请求: 发送原始截图数据到客户端, session_id={session_id}")
        else:
            print(f"⚠️ 刷新请求失败: 没有找到session {session_id} 的截图数据")
            emit('error', {'message': f'没有找到会话 {session_id} 的截图数据'})

@socketio.on('browser_click')
def handle_browser_click(data):
    """处理前端点击事件，转发到后端浏览器"""
    session_id = data.get('session_id')
    x = data.get('x')
    y = data.get('y')
    
    if not session_id or not x or not y:
        emit('error', {'message': '无效的点击数据'})
        return
    
    with browser_data_lock:
        if session_id in active_browser_sessions:
            # 限制队列大小，防止内存泄漏
            if len(browser_click_queue[session_id]) >= MAX_CLICK_QUEUE_SIZE:
                browser_click_queue[session_id] = browser_click_queue[session_id][-MAX_CLICK_QUEUE_SIZE//2:]
            
            browser_click_queue[session_id].append({
                'type': 'click',
                'x': int(x),
                'y': int(y),
                'timestamp': time.time()
            })
            
            douyin_logger.info(f"收到点击事件: ({x}, {y}) for session {session_id}")
            
            emit('click_received', {
                'session_id': session_id,
                'x': x,
                'y': y,
                'message': f'点击位置: ({x}, {y})'
            })
        else:
            emit('error', {'message': f'会话 {session_id} 不活跃或不存在'})

@socketio.on('browser_input')
def handle_browser_input(data):
    """处理前端键盘输入事件，转发到后端浏览器"""
    session_id = data.get('session_id')
    text = data.get('text', '')
    key = data.get('key', '')
    action = data.get('action', 'type')  # type, press, key_down, key_up
    
    if not session_id:
        emit('error', {'message': '无效的会话ID'})
        return
    
    # 限制输入长度，防止恶意输入
    if len(text) > 1000:
        text = text[:1000]
    
    with browser_data_lock:
        if session_id in active_browser_sessions:
            # 限制队列大小
            if len(browser_click_queue[session_id]) >= MAX_CLICK_QUEUE_SIZE:
                browser_click_queue[session_id] = browser_click_queue[session_id][-MAX_CLICK_QUEUE_SIZE//2:]
            
            browser_click_queue[session_id].append({
                'type': 'input',
                'action': action,
                'text': text,
                'key': key,
                'timestamp': time.time()
            })
            
            douyin_logger.info(f"收到输入事件: action={action}, text='{text[:50]}', key='{key}' for session {session_id}")
            
            emit('input_received', {
                'session_id': session_id,
                'action': action,
                'text': text,
                'key': key,
                'message': f'输入内容: {text[:20]}...' if len(text) > 20 else f'输入内容: {text}' if text else f'按键: {key}'
            })
        else:
            emit('error', {'message': f'会话 {session_id} 不活跃或不存在'})

@socketio.on('close_browser')
def handle_close_browser(data):
    """处理前端关闭浏览器请求"""
    session_id = data.get('session_id')
    
    if not session_id:
        emit('error', {'message': '无效的会话ID'})
        return
    
    with browser_data_lock:
        if session_id in active_browser_sessions:
            douyin_logger.info(f"收到关闭浏览器请求: {session_id}")
            
            # 标记会话为关闭状态
            active_browser_sessions[session_id] = False
            
            emit('browser_status', {
                'session_id': session_id,
                'status': 'closing',
                'message': '正在关闭浏览器并保存Cookie...'
            })
            
            # 清理相关资源
            try:
                if session_id in browser_click_queue:
                    del browser_click_queue[session_id]
                
                if session_id in browser_pages:
                    del browser_pages[session_id]
                
                if session_id in browser_screenshot_data:
                    del browser_screenshot_data[session_id]
                    
            except KeyError:
                pass  # 资源已经被清理
            
            douyin_logger.info(f"浏览器会话已关闭: {session_id}")
        else:
            emit('error', {'message': f'会话 {session_id} 不存在或已关闭'})

@app.route('/')
@login_required
def index():
    return render_template('index.html')

@app.route('/usage-guide')
def usage_guide():
    """使用说明页面"""
    return render_template('usage_guide.html')

@app.route('/video-editor')
def video_editor():
    return render_template('video_editor.html')

# 获取downloads下的子文件夹列表
@app.route('/api/downloads/folders')
def get_downloads_folders():
    try:
        downloads_path = os.path.join(os.getcwd(), 'downloads')
        folders = []
        if os.path.exists(downloads_path):
            for item in os.listdir(downloads_path):
                item_path = os.path.join(downloads_path, item)
                if os.path.isdir(item_path):
                    folders.append(item)
        return jsonify({'success': True, 'folders': folders})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/downloads/videos/<folder_name>')
def get_folder_videos_api(folder_name):
    try:
        folder_path = os.path.join('downloads', folder_name)
        if not os.path.exists(folder_path):
            return jsonify({"success": False, "error": "文件夹不存在"})
        
        videos = [f for f in os.listdir(folder_path) if os.path.isfile(os.path.join(folder_path, f)) and f.lower().endswith(('.mp4', '.mov', '.avi', '.mkv'))]
        return jsonify({"success": True, "videos": videos})
    except Exception as e:
        douyin_logger.error(f"获取文件夹视频列表失败: {str(e)}")
        return jsonify({"success": False, "error": str(e)})

@app.route('/api/downloads/all_videos')
def get_all_folder_videos_api():
    try:
        downloads_path = 'downloads'
        if not os.path.exists(downloads_path):
            return jsonify({"success": False, "error": "downloads目录不存在"})
        
        # 获取所有视频文件
        all_videos = []
        folders = [f for f in os.listdir(downloads_path) if os.path.isdir(os.path.join(downloads_path, f))]
        
        for folder in folders:
            folder_path = os.path.join(downloads_path, folder)
            videos = [f for f in os.listdir(folder_path) if os.path.isfile(os.path.join(folder_path, f)) and f.lower().endswith(('.mp4', '.mov', '.avi', '.mkv'))]
            
            # 添加每个视频的文件夹和名称信息
            for video in videos:
                all_videos.append({
                    "folder": folder,
                    "name": video
                })
        
        return jsonify({"success": True, "videos": all_videos})
    except Exception as e:
        douyin_logger.error(f"获取所有视频列表失败: {str(e)}")
        return jsonify({"success": False, "error": str(e)})

@app.route('/api/video/upload_b_video', methods=['POST'])
def upload_b_video():
    """上传B视频文件"""
    try:
        if 'file' not in request.files:
            return jsonify({'error': '没有选择文件'}), 400
        
        file = request.files['file']
        if file.filename == '':
            return jsonify({'error': '没有选择文件'}), 400
        
        # 检查文件类型
        allowed_extensions = {'.mp4', '.avi', '.mov', '.mkv', '.flv', '.wmv'}
        file_extension = os.path.splitext(file.filename)[1].lower()
        if file_extension not in allowed_extensions:
            return jsonify({'error': '不支持的文件格式'}), 400
        
        # 保存B视频文件
        b_videos_dir = os.path.join('static', 'b_videos')
        os.makedirs(b_videos_dir, exist_ok=True)
        
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        safe_filename = f"b_video_{timestamp}{file_extension}"
        file_path = os.path.join(b_videos_dir, safe_filename)
        
        file.save(file_path)
        
        # 获取视频信息
        video_info = get_video_info(file_path)
        
        return jsonify({
            'success': True,
            'file_path': file_path,
            'filename': safe_filename,
            'video_info': video_info
        })
        
    except Exception as e:
        return jsonify({'error': f'上传失败: {str(e)}'}), 500

@app.route('/api/video/builtin_materials', methods=['GET'])
def get_builtin_materials():
    """获取内置素材库列表"""
    try:
        materials_dir = os.path.join('static', 'builtin_materials')
        materials = []
        
        if os.path.exists(materials_dir):
            for filename in os.listdir(materials_dir):
                if filename.lower().endswith(('.mp4', '.avi', '.mov')):
                    file_path = os.path.join(materials_dir, filename)
                    video_info = get_video_info(file_path)
                    materials.append({
                        'id': os.path.splitext(filename)[0],
                        'name': filename,
                        'path': file_path,
                        'info': video_info
                    })
        
        return jsonify({'materials': materials})
        
    except Exception as e:
        return jsonify({'error': f'获取素材库失败: {str(e)}'}), 500

@app.route('/api/video/generate_b_video', methods=['POST'])
def generate_b_video():
    """AI生成B视频"""
    try:
        data = request.get_json()
        generate_type = data.get('type', 'nature')
        duration = data.get('duration', 10)  # 默认10秒
        
        # 生成视频的目录
        generated_dir = os.path.join('static', 'generated_videos')
        os.makedirs(generated_dir, exist_ok=True)
        
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        output_filename = f"generated_{generate_type}_{timestamp}.mp4"
        output_path = os.path.join(generated_dir, output_filename)
        
        # 根据类型生成不同的FFmpeg命令
        if generate_type == 'nature':
            # 生成自然场景（使用testsrc2产生自然色彩）
            cmd = [
                'ffmpeg', '-f', 'lavfi', 
                '-i', f'testsrc2=duration={duration}:size=1920x1080:rate=25',
                '-f', 'lavfi', '-i', 'sine=frequency=220:duration=' + str(duration),
                '-vf', 'hue=s=0.8,eq=contrast=1.2:brightness=0.1,gblur=sigma=0.5',
                '-c:v', 'libx264', '-c:a', 'aac', '-shortest', output_path
            ]
        elif generate_type == 'abstract':
            # 生成抽象图案
            cmd = [
                'ffmpeg', '-f', 'lavfi',
                '-i', f'mandelbrot=size=1920x1080:rate=25:maxiter=100:outer=sierpinski:inner=manowar:bailout=10:duration={duration}',
                '-f', 'lavfi', '-i', 'sine=frequency=440:duration=' + str(duration),
                '-c:v', 'libx264', '-c:a', 'aac', '-shortest', output_path
            ]
        elif generate_type == 'noise':
            # 生成随机噪声
            cmd = [
                'ffmpeg', '-f', 'lavfi',
                '-i', f'noise=alls=1:allf=t:duration={duration}:size=1920x1080:rate=25',
                '-f', 'lavfi', '-i', 'anoisesrc=duration=' + str(duration),
                '-c:v', 'libx264', '-c:a', 'aac', '-shortest', output_path
            ]
        elif generate_type == 'gradient':
            # 生成渐变背景
            cmd = [
                'ffmpeg', '-f', 'lavfi',
                '-i', f'gradients=size=1920x1080:rate=25:duration={duration}:speed=0.01',
                '-f', 'lavfi', '-i', 'sine=frequency=330:duration=' + str(duration),
                '-c:v', 'libx264', '-c:a', 'aac', '-shortest', output_path
            ]
        
        # 执行FFmpeg命令
        result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='ignore')
        
        if result.returncode == 0:
            video_info = get_video_info(output_path)
            return jsonify({
                'success': True,
                'file_path': output_path,
                'filename': output_filename,
                'video_info': video_info
            })
        else:
            return jsonify({
                'error': f'生成视频失败: {result.stderr}'
            }), 500
            
    except Exception as e:
        return jsonify({'error': f'生成视频失败: {str(e)}'}), 500

@app.route('/api/video/process', methods=['POST'])
def process_video():
    """处理视频编辑请求"""
    try:
        # 获取设置
        if request.content_type == 'application/json':
            # JSON请求 - 来自文件夹选择
            data = request.get_json()
            settings = data.get('settings', {})
            
            # 处理全选所有文件夹的情况
            all_folders = data.get('all_folders', False)
            
            if all_folders:
                # 处理来自多个文件夹的视频
                videos = data.get('videos', [])
                if not videos:
                    return jsonify({'error': '缺少视频列表'}), 400
                
                # 批量处理多个视频
                processed_files = []
                failed_files = []
                
                for video_data in videos:
                    folder_name = video_data.get('folder')
                    video_filename = video_data.get('filename')
                    
                    if not folder_name or not video_filename:
                        failed_files.append(f'缺少文件夹或文件名: {video_data}')
                        continue
                        
                    try:
                        # 从downloads文件夹获取视频
                        input_path = os.path.join(os.getcwd(), 'downloads', folder_name, video_filename)
                        input_path = os.path.normpath(input_path)  # 规范化输入路径
                        if not os.path.exists(input_path):
                            failed_files.append(f'{folder_name}/{video_filename}: 文件不存在')
                            continue
                        
                        # 处理单个视频...
                        # 生成输出文件名和路径
                        name, ext = os.path.splitext(video_filename)
                        output_filename = f"{name}{ext}"
                        output_dir = os.path.join('videos', folder_name)
                        output_path = os.path.join(output_dir, output_filename)
                        
                        # 确保输出目录存在
                        os.makedirs(output_dir, exist_ok=True)
                        
                        # 如果文件已存在，添加数字后缀
                        counter = 1
                        base_name_for_conflict = name # 用于冲突处理的基础文件名
                        while os.path.exists(output_path):
                            output_filename = f"{base_name_for_conflict}_{counter}{ext}"
                            output_path = os.path.join(output_dir, output_filename)
                            counter += 1
                        
                        # 规范化路径格式，解决中文路径问题
                        output_path = os.path.normpath(output_path)
                        
                        # 处理分屏自动选择逻辑
                        split_screen = settings.get('splitScreen', {})
                        if split_screen.get('enabled', False) and split_screen.get('direction') == 'auto':
                            # 获取视频信息以确定分屏方向
                            video_info = get_video_info(input_path)
                            if video_info:
                                # 竖屏视频使用左右分屏，横屏视频使用上下分屏
                                if video_info['is_portrait']:
                                    settings['splitScreen']['direction'] = 'horizontal'  # 左右分屏
                                    douyin_logger.info(f"检测到竖屏视频 ({video_info['width']}x{video_info['height']})，自动选择左右分屏")
                                else:
                                    settings['splitScreen']['direction'] = 'vertical'    # 上下分屏
                                    douyin_logger.info(f"检测到横屏视频 ({video_info['width']}x{video_info['height']})，自动选择上下分屏")
                            else:
                                # 无法获取视频信息时默认使用左右分屏
                                settings['splitScreen']['direction'] = 'horizontal'
                                douyin_logger.warning("无法获取视频信息，默认使用左右分屏")
                        
                        # 构建FFmpeg命令
                        ffmpeg_cmd = build_ffmpeg_command(input_path, output_path, settings)
                        
                        # 打印FFmpeg命令以便调试
                        douyin_logger.info(f"执行FFmpeg命令: {' '.join(ffmpeg_cmd)}")
                        
                        # 执行FFmpeg命令
                        import subprocess
                        try:
                            result = subprocess.run(ffmpeg_cmd, capture_output=True, text=True, encoding='utf-8', errors='ignore')
                        except UnicodeDecodeError:
                            # 如果UTF-8解码失败，尝试使用gbk编码
                            result = subprocess.run(ffmpeg_cmd, capture_output=True, text=True, encoding='gbk', errors='ignore')
                        
                        # 处理执行结果...
                        if result.stdout:
                            douyin_logger.info(f"FFmpeg输出: {result.stdout}")
                        if result.stderr:
                            douyin_logger.error(f"FFmpeg错误: {result.stderr}")
                        douyin_logger.info(f"FFmpeg返回码: {result.returncode}")
                        
                        if result.returncode == 0:
                            # 处理成功，尝试复制对应的txt文件和图片
                            import urllib.parse
                            decoded_name = urllib.parse.unquote(name)
                            original_txt_path = os.path.join(os.getcwd(), 'downloads', folder_name, f"{decoded_name}.txt")
                            
                            # 如果解码后的文件不存在，尝试使用原始文件名
                            if not os.path.exists(original_txt_path):
                                original_txt_path = os.path.join(os.getcwd(), 'downloads', folder_name, f"{name}.txt")
                            
                            if os.path.exists(original_txt_path):
                                # 复制txt文件到输出目录
                                output_txt_path = os.path.join(output_dir, os.path.splitext(output_filename)[0] + ".txt")
                                try:
                                    import shutil
                                    shutil.copy2(original_txt_path, output_txt_path)
                                    print(f"已复制txt文件: {original_txt_path} -> {output_txt_path}")
                                except Exception as e:
                                    print(f"复制txt文件失败: {e}")
                            
                            # 复制可能存在的封面图片文件
                            for img_ext in ['.jpg', '.jpeg', '.png', '.webp']:
                                original_img_path = os.path.join(os.getcwd(), 'downloads', folder_name, f"{decoded_name}{img_ext}")
                                if not os.path.exists(original_img_path):
                                    original_img_path = os.path.join(os.getcwd(), 'downloads', folder_name, f"{name}{img_ext}")
                                
                                if os.path.exists(original_img_path):
                                    output_img_path = os.path.join(output_dir, os.path.splitext(output_filename)[0] + img_ext)
                                    try:
                                        import shutil
                                        shutil.copy2(original_img_path, output_img_path)
                                        print(f"已复制封面图片: {original_img_path} -> {output_img_path}")
                                        break  # 只复制第一个找到的图片
                                    except Exception as e:
                                        print(f"复制封面图片失败: {e}")
                            
                            # 记录处理成功的文件
                            relative_output = os.path.join(folder_name, output_filename).replace('\\', '/')
                            processed_files.append({
                                'original': f'{folder_name}/{video_filename}',
                                'processed': relative_output
                            })
                            
                            # 删除原视频文件
                            try:
                                original_video_path = os.path.join(os.getcwd(), 'downloads', folder_name, video_filename)
                                if os.path.exists(original_video_path):
                                    os.remove(original_video_path)
                                    douyin_logger.info(f"已删除原视频文件: {original_video_path}")
                                
                                # 删除对应的txt文件
                                if os.path.exists(original_txt_path):
                                    os.remove(original_txt_path)
                                    douyin_logger.info(f"已删除原视频txt文件: {original_txt_path}")
                                    
                                # 删除对应的封面图片文件
                                for img_ext in ['.jpg', '.jpeg', '.png', '.webp']:
                                    original_img_path = os.path.join(os.getcwd(), 'downloads', folder_name, f"{decoded_name}{img_ext}")
                                    if not os.path.exists(original_img_path):
                                        original_img_path = os.path.join(os.getcwd(), 'downloads', folder_name, f"{name}{img_ext}")
                                    
                                    if os.path.exists(original_img_path):
                                        os.remove(original_img_path)
                                        douyin_logger.info(f"已删除原视频封面图片: {original_img_path}")
                                        break
                                
                                # 检查文件夹是否为空，如果为空则删除
                                folder_path = os.path.join(os.getcwd(), 'downloads', folder_name)
                                if os.path.exists(folder_path):
                                    remaining_files = os.listdir(folder_path)
                                    if not remaining_files:
                                        os.rmdir(folder_path)
                                        douyin_logger.info(f"文件夹已清空，删除空文件夹: {folder_path}")
                            except Exception as e:
                                douyin_logger.error(f"删除原文件失败: {str(e)}")
                        else:
                            failed_files.append(f'{folder_name}/{video_filename}: {result.stderr}')
                    
                    except Exception as e:
                        failed_files.append(f'{folder_name}/{video_filename}: {str(e)}')
                
                # 返回批量处理结果
                if processed_files:
                    message = f'成功处理 {len(processed_files)} 个视频'
                    if failed_files:
                        message += f'，{len(failed_files)} 个视频处理失败'
                    
                    return jsonify({
                        'success': True,
                        'processed_files': processed_files,
                        'failed_files': failed_files,
                        'output_file': processed_files[0]['processed'] if len(processed_files) == 1 else '',  # 兼容单文件
                        'message': message
                    })
                else:
                    return jsonify({
                        'error': f'所有视频处理失败: {"; ".join(failed_files)}'
                    }), 500
            
            # 原有逻辑：处理单个文件夹中的视频
            else:
                folder_name = data.get('folder_name')
                video_filenames = data.get('video_filenames', [])
                
                # 向后兼容单个视频文件
                if not video_filenames:
                    video_filename = data.get('video_filename')
                    if video_filename:
                        video_filenames = [video_filename]
                
                if not folder_name or not video_filenames:
                    return jsonify({'error': '缺少文件夹或视频文件名'}), 400
            
            # 批量处理多个视频
            processed_files = []
            failed_files = []
            
            for video_filename in video_filenames:
                try:
                    # 从downloads文件夹获取视频
                    input_path = os.path.join(os.getcwd(), 'downloads', folder_name, video_filename)
                    input_path = os.path.normpath(input_path)  # 规范化输入路径
                    if not os.path.exists(input_path):
                        failed_files.append(f'{video_filename}: 文件不存在')
                        continue
                    
                    # 生成输出文件名和路径
                    name, ext = os.path.splitext(video_filename)
                    output_filename = f"{name}{ext}"
                    output_dir = os.path.join('videos', folder_name)
                    output_path = os.path.join(output_dir, output_filename)
                    
                    # 确保输出目录存在
                    os.makedirs(output_dir, exist_ok=True)
                    
                    # 如果文件已存在，添加数字后缀
                    counter = 1
                    base_name_for_conflict = name # 用于冲突处理的基础文件名
                    while os.path.exists(output_path):
                        output_filename = f"{base_name_for_conflict}_{counter}{ext}"
                        output_path = os.path.join(output_dir, output_filename)
                        counter += 1
                    
                    # 规范化路径格式，解决中文路径问题
                    output_path = os.path.normpath(output_path)
                    
                    # 处理分屏自动选择逻辑
                    split_screen = settings.get('splitScreen', {})
                    if split_screen.get('enabled', False) and split_screen.get('direction') == 'auto':
                        # 获取视频信息以确定分屏方向
                        video_info = get_video_info(input_path)
                        if video_info:
                            # 竖屏视频使用左右分屏，横屏视频使用上下分屏
                            if video_info['is_portrait']:
                                settings['splitScreen']['direction'] = 'horizontal'  # 左右分屏
                                douyin_logger.info(f"检测到竖屏视频 ({video_info['width']}x{video_info['height']})，自动选择左右分屏")
                            else:
                                settings['splitScreen']['direction'] = 'vertical'    # 上下分屏
                                douyin_logger.info(f"检测到横屏视频 ({video_info['width']}x{video_info['height']})，自动选择上下分屏")
                        else:
                            # 无法获取视频信息时默认使用左右分屏
                            settings['splitScreen']['direction'] = 'horizontal'
                            douyin_logger.warning("无法获取视频信息，默认使用左右分屏")
                    
                    # 构建FFmpeg命令
                    ffmpeg_cmd = build_ffmpeg_command(input_path, output_path, settings)
                    
                    # 打印FFmpeg命令以便调试
                    douyin_logger.info(f"执行FFmpeg命令: {' '.join(ffmpeg_cmd)}")
                    
                    # 执行FFmpeg命令
                    import subprocess
                    try:
                        result = subprocess.run(ffmpeg_cmd, capture_output=True, text=True, encoding='utf-8', errors='ignore')
                    except UnicodeDecodeError:
                        # 如果UTF-8解码失败，尝试使用gbk编码
                        result = subprocess.run(ffmpeg_cmd, capture_output=True, text=True, encoding='gbk', errors='ignore')
                    
                    # 打印FFmpeg执行结果
                    if result.stdout:
                        douyin_logger.info(f"FFmpeg输出: {result.stdout}")
                    if result.stderr:
                        douyin_logger.error(f"FFmpeg错误: {result.stderr}")
                    douyin_logger.info(f"FFmpeg返回码: {result.returncode}")
                    
                    if result.returncode == 0:
                        # 处理成功，尝试复制对应的txt文件和图片
                        import urllib.parse
                        decoded_name = urllib.parse.unquote(name)
                        original_txt_path = os.path.join(os.getcwd(), 'downloads', folder_name, f"{decoded_name}.txt")
                        
                        # 如果解码后的文件不存在，尝试使用原始文件名
                        if not os.path.exists(original_txt_path):
                            original_txt_path = os.path.join(os.getcwd(), 'downloads', folder_name, f"{name}.txt")
                        
                        if os.path.exists(original_txt_path):
                            # 复制txt文件到输出目录
                            output_txt_path = os.path.join(output_dir, os.path.splitext(output_filename)[0] + ".txt")
                            try:
                                import shutil
                                shutil.copy2(original_txt_path, output_txt_path)
                                print(f"已复制txt文件: {original_txt_path} -> {output_txt_path}")
                            except Exception as e:
                                print(f"复制txt文件失败: {e}")
                        
                        # 复制可能存在的封面图片文件
                        for img_ext in ['.jpg', '.jpeg', '.png', '.webp']:
                            original_img_path = os.path.join(os.getcwd(), 'downloads', folder_name, f"{decoded_name}{img_ext}")
                            if not os.path.exists(original_img_path):
                                original_img_path = os.path.join(os.getcwd(), 'downloads', folder_name, f"{name}{img_ext}")
                            
                            if os.path.exists(original_img_path):
                                output_img_path = os.path.join(output_dir, os.path.splitext(output_filename)[0] + img_ext)
                                try:
                                    import shutil
                                    shutil.copy2(original_img_path, output_img_path)
                                    print(f"已复制封面图片: {original_img_path} -> {output_img_path}")
                                    break  # 只复制第一个找到的图片
                                except Exception as e:
                                    print(f"复制封面图片失败: {e}")
                        
                        # 记录处理成功的文件
                        relative_output = os.path.join(folder_name, output_filename).replace('\\', '/')
                        processed_files.append({
                            'original': video_filename,
                            'processed': relative_output
                        })
                        
                        # 删除原视频文件
                        try:
                            original_video_path = os.path.join(os.getcwd(), 'downloads', folder_name, video_filename)
                            if os.path.exists(original_video_path):
                                os.remove(original_video_path)
                                douyin_logger.info(f"已删除原视频文件: {original_video_path}")
                            
                            # 删除对应的txt文件
                            if os.path.exists(original_txt_path):
                                os.remove(original_txt_path)
                                douyin_logger.info(f"已删除原视频txt文件: {original_txt_path}")
                                
                            # 删除对应的封面图片文件
                            for img_ext in ['.jpg', '.jpeg', '.png', '.webp']:
                                original_img_path = os.path.join(os.getcwd(), 'downloads', folder_name, f"{decoded_name}{img_ext}")
                                if not os.path.exists(original_img_path):
                                    original_img_path = os.path.join(os.getcwd(), 'downloads', folder_name, f"{name}{img_ext}")
                                
                                if os.path.exists(original_img_path):
                                    os.remove(original_img_path)
                                    douyin_logger.info(f"已删除原视频封面图片: {original_img_path}")
                                    break
                            
                            # 检查文件夹是否为空，如果为空则删除
                            folder_path = os.path.join(os.getcwd(), 'downloads', folder_name)
                            if os.path.exists(folder_path):
                                remaining_files = os.listdir(folder_path)
                                if not remaining_files:
                                    os.rmdir(folder_path)
                                    douyin_logger.info(f"文件夹已清空，删除空文件夹: {folder_path}")
                        except Exception as e:
                            douyin_logger.error(f"删除原文件失败: {str(e)}")
                    else:
                        failed_files.append(f'{video_filename}: {result.stderr}')
                
                except Exception as e:
                    failed_files.append(f'{video_filename}: {str(e)}')
            
            # 返回批量处理结果
            if processed_files:
                message = f'成功处理 {len(processed_files)} 个视频'
                if failed_files:
                    message += f'，{len(failed_files)} 个视频处理失败'
                
                return jsonify({
                    'success': True,
                    'processed_files': processed_files,
                    'failed_files': failed_files,
                    'output_file': processed_files[0]['processed'] if len(processed_files) == 1 else '',  # 兼容单文件
                    'message': message
                })
            else:
                return jsonify({
                    'error': f'所有视频处理失败: {"; ".join(failed_files)}'
                }), 500
        
        else:
            # 表单请求 - 来自文件上传
            video_file = request.files.get('video')
            settings = request.form.get('settings')
            
            if not video_file:
                return jsonify({'error': '未找到视频文件'}), 400
            
            if settings:
                import json
                settings = json.loads(settings)
            else:
                settings = {}
            
            # 保存上传的文件
            import tempfile
            temp_dir = tempfile.mkdtemp()
            input_path = os.path.join(temp_dir, video_file.filename)
            video_file.save(input_path)
            video_filename = video_file.filename
            
            # 生成输出文件名和路径
            name, ext = os.path.splitext(video_filename)
            output_filename = f"{name}{ext}"
            output_dir = 'videos'
            output_path = os.path.join(output_dir, output_filename)
            
            # 确保输出目录存在
            os.makedirs(output_dir, exist_ok=True)
            
            # 规范化路径格式，解决中文路径问题
            output_path = os.path.normpath(output_path)
            
            # 处理分屏自动选择逻辑
            split_screen = settings.get('splitScreen', {})
            if split_screen.get('enabled', False) and split_screen.get('direction') == 'auto':
                # 获取视频信息以确定分屏方向
                video_info = get_video_info(input_path)
                if video_info:
                    # 竖屏视频使用左右分屏，横屏视频使用上下分屏
                    if video_info['is_portrait']:
                        settings['splitScreen']['direction'] = 'horizontal'  # 左右分屏
                        douyin_logger.info(f"检测到竖屏视频 ({video_info['width']}x{video_info['height']})，自动选择左右分屏")
                    else:
                        settings['splitScreen']['direction'] = 'vertical'    # 上下分屏
                        douyin_logger.info(f"检测到横屏视频 ({video_info['width']}x{video_info['height']})，自动选择上下分屏")
                else:
                    # 无法获取视频信息时默认使用左右分屏
                    settings['splitScreen']['direction'] = 'horizontal'
                    douyin_logger.warning("无法获取视频信息，默认使用左右分屏")
            
            # 构建FFmpeg命令
            ffmpeg_cmd = build_ffmpeg_command(input_path, output_path, settings)
            
            # 打印FFmpeg命令以便调试
            douyin_logger.info(f"执行FFmpeg命令: {' '.join(ffmpeg_cmd)}")
            
            # 执行FFmpeg命令
            import subprocess
            try:
                result = subprocess.run(ffmpeg_cmd, capture_output=True, text=True, encoding='utf-8', errors='ignore')
            except UnicodeDecodeError:
                # 如果UTF-8解码失败，尝试使用gbk编码
                result = subprocess.run(ffmpeg_cmd, capture_output=True, text=True, encoding='gbk', errors='ignore')
            
            # 打印FFmpeg执行结果
            if result.stdout:
                douyin_logger.info(f"FFmpeg输出: {result.stdout}")
            if result.stderr:
                douyin_logger.error(f"FFmpeg错误: {result.stderr}")
            douyin_logger.info(f"FFmpeg返回码: {result.returncode}")
            
            if result.returncode == 0:
                # 临时文件处理完成后删除
                try:
                    import shutil
                    shutil.rmtree(temp_dir)
                    douyin_logger.info(f"已删除临时文件夹: {temp_dir}")
                except Exception as e:
                    douyin_logger.error(f"删除临时文件夹失败: {str(e)}")
                
                return jsonify({
                    'success': True,
                    'output_file': output_filename,
                    'message': '视频处理完成'
                })
            else:
                return jsonify({
                    'error': f'视频处理失败: {result.stderr}'
                }), 500
            
    except Exception as e:
        return jsonify({'error': f'处理错误: {str(e)}'}), 500

def get_video_info(video_path):
    """获取视频的基本信息（宽度、高度、时长等）"""
    import json
    try:
        cmd = [
            'ffprobe', '-v', 'quiet', '-print_format', 'json', '-show_format', '-show_streams', video_path
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='ignore')
        if result.returncode == 0:
            data = json.loads(result.stdout)
            video_stream = None
            for stream in data.get('streams', []):
                if stream.get('codec_type') == 'video':
                    video_stream = stream
                    break
            
            if video_stream:
                width = int(video_stream.get('width', 0))
                height = int(video_stream.get('height', 0))
                duration = float(video_stream.get('duration', 0))
                return {
                    'width': width,
                    'height': height,
                    'duration': duration,
                    'aspect_ratio': width / height if height > 0 else 1.0,
                    'is_portrait': height > width
                }
    except Exception as e:
        douyin_logger.warning(f"获取视频信息失败: {str(e)}")
    
    return None

def build_ffmpeg_command(input_path, output_path, settings):
    """构建FFmpeg命令"""
    # 规范化路径格式，确保FFmpeg能正确处理包含中文的路径
    input_path = os.path.normpath(input_path)
    output_path = os.path.normpath(output_path)
    
    # 基础命令，稍后会根据AB帧融合添加更多输入
    cmd = ['ffmpeg']
    
    # 强制禁用硬件加速，作为解决顽固崩溃的最终手段，提高稳定性
    cmd.extend(['-hwaccel', 'none'])
    
    # 添加主输入文件
    cmd.extend(['-i', input_path])
    
    # 检查AB帧融合是否需要额外的B视频输入
    ab_fusion = settings.get('abFusion', {})
    has_b_video = False
    b_video_path = None
    
    if ab_fusion.get('enabled', False):
        b_video_source = ab_fusion.get('bVideoSource', 'upload')
        builtin_material = ab_fusion.get('builtinMaterial', '')
        b_video_path = ab_fusion.get('bVideoPath')
        
        # 处理内置素材的路径
        if b_video_source == 'builtin' and builtin_material:
            b_video_path = builtin_material
        
        # 规范化B视频路径
        if b_video_path:
            b_video_path = os.path.normpath(b_video_path)
            if os.path.exists(b_video_path):
                cmd.extend(['-i', b_video_path])
                has_b_video = True
                douyin_logger.info(f"✅ 添加B视频输入: {b_video_path}")
            else:
                douyin_logger.warning(f"❌ B视频文件不存在: {b_video_path}")
    
    # --- 健壮的滤镜链构建 ---
    video_filters = []
    audio_filters = []
    current_stream = "[0:v]"
    stream_idx = 0

    def get_next_stream_label():
        nonlocal stream_idx
        label = f"[v{stream_idx}]"
        stream_idx += 1
        return label

    # 1. 抽帧 (已禁用以保持原始帧率)
    frame_skip = settings.get('frameSkip', {})
    if False:  # 禁用抽帧功能
        skip_start = frame_skip.get('start', 25)
        next_stream = get_next_stream_label()
        video_filters.append(f"{current_stream}select=not(mod(n\\,{skip_start})){next_stream}")
        current_stream = next_stream

    # 2. 旋转和翻转
    transform = settings.get('transform', {})
    if not transform.get('keep_original', False):
        rotation = transform.get('rotation', 0)
        if rotation == 90:
            next_stream = get_next_stream_label()
            video_filters.append(f"{current_stream}transpose=1{next_stream}")
            current_stream = next_stream
        elif rotation == 180:
            next_stream = get_next_stream_label()
            video_filters.append(f"{current_stream}transpose=1,transpose=1{next_stream}")
            current_stream = next_stream
        elif rotation == 270:
            next_stream = get_next_stream_label()
            video_filters.append(f"{current_stream}transpose=2{next_stream}")
            current_stream = next_stream
        
        if transform.get('flipH', False):
            next_stream = get_next_stream_label()
            video_filters.append(f"{current_stream}hflip{next_stream}")
            current_stream = next_stream
        
        if transform.get('flipV', False):
            next_stream = get_next_stream_label()
            video_filters.append(f"{current_stream}vflip{next_stream}")
            current_stream = next_stream

    # 3. 画面调整
    eq_filters = []
    if settings.get('brightness', 0) != 0: eq_filters.append(f"brightness={settings.get('brightness', 0) / 100.0}")
    if settings.get('contrast', 0) != 0: eq_filters.append(f"contrast={1 + settings.get('contrast', 0) / 100.0}")
    if settings.get('saturation', 0) != 0: eq_filters.append(f"saturation={1 + settings.get('saturation', 0) / 100.0}")
    if eq_filters:
        next_stream = get_next_stream_label()
        video_filters.append(f"{current_stream}eq={'_'.join(eq_filters)}{next_stream}")
        current_stream = next_stream

    # 4. 锐化
    if settings.get('sharpen', 0) > 0:
        sharpen_value = settings.get('sharpen', 0) / 100.0
        next_stream = get_next_stream_label()
        video_filters.append(f"{current_stream}unsharp=5:5:{sharpen_value}:5:5:0.0{next_stream}")
        current_stream = next_stream

    # 5. 降噪
    if settings.get('denoise', 0) > 0:
        denoise_value = settings.get('denoise', 0) / 100.0 * 10
        next_stream = get_next_stream_label()
        video_filters.append(f"{current_stream}hqdn3d={denoise_value}{next_stream}")
        current_stream = next_stream
        
    # 6. 分辨率
    resolution = settings.get('resolution', {})
    if resolution.get('width') and resolution.get('height'):
        width, height = resolution['width'], resolution['height']
        if width != 'original' and height != 'original':
            mode = resolution.get('mode', 'crop')
            next_stream = get_next_stream_label()
            if mode == 'stretch':
                video_filters.append(f"{current_stream}scale={width}:{height}{next_stream}")
            elif mode == 'crop':
                video_filters.append(f"{current_stream}scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height}{next_stream}")
            elif mode == 'letterbox':
                video_filters.append(f"{current_stream}scale={width}:{height}:force_original_aspect_ratio=decrease,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:black{next_stream}")
            elif mode == 'pad':
                 video_filters.append(f"{current_stream}scale={width}:{height}:force_original_aspect_ratio=decrease,gblur=sigma=20,scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height}{next_stream}")
            current_stream = next_stream
            
    # 7. 分屏效果
    split_screen = settings.get('splitScreen', {})
    if split_screen.get('enabled', False):
        direction = split_screen.get('direction', 'vertical')
        ratio = split_screen.get('ratio', 'equal')
        blur = split_screen.get('blur', False)
        blur_filter = f",boxblur=3.5:1" if blur else ""
        next_stream = get_next_stream_label()
        
        split_graph = ""
        if direction == 'vertical':
            if ratio == 'equal':
                split_graph = f"split=3[v_top_in][v_middle_in][v_bottom_in];[v_top_in]crop=iw:ih/2:0:0[c_top];[c_top]scale=iw:ih/3{blur_filter}[s_top];[v_middle_in]scale=iw:ih/3[s_middle];[v_bottom_in]crop=iw:ih/2:0:ih/2[c_bottom];[c_bottom]scale=iw:ih/3{blur_filter}[s_bottom];[s_top][s_middle][s_bottom]vstack=inputs=3{next_stream}"
            elif ratio == 'center-large':
                split_graph = f"split=3[v_top_in][v_middle_in][v_bottom_in];[v_top_in]crop=iw:ih/2:0:0[c_top];[c_top]scale=iw:ih/4{blur_filter}[s_top];[v_middle_in]scale=iw:ih/2[s_middle];[v_bottom_in]crop=iw:ih/2:0:ih/2[c_bottom];[c_bottom]scale=iw:ih/4{blur_filter}[s_bottom];[s_top][s_middle][s_bottom]vstack=inputs=3{next_stream}"
            elif ratio == 'edges-large':
                split_graph = f"split=3[v_top_in][v_middle_in][v_bottom_in];[v_top_in]crop=iw:ih/2:0:0[c_top];[c_top]scale=iw:3*ih/8{blur_filter}[s_top];[v_middle_in]scale=iw:ih/4[s_middle];[v_bottom_in]crop=iw:ih/2:0:ih/2[c_bottom];[c_bottom]scale=iw:3*ih/8{blur_filter}[s_bottom];[s_top][s_middle][s_bottom]vstack=inputs=3{next_stream}"
        elif direction == 'horizontal':
            if ratio == 'equal':
                split_graph = f"split=3[v_left_in][v_middle_in][v_right_in];[v_left_in]crop=iw/2:ih:0:0[c_left];[c_left]scale=iw/3:ih{blur_filter}[s_left];[v_middle_in]scale=iw/3:ih[s_middle];[v_right_in]crop=iw/2:ih:iw/2:0[c_right];[c_right]scale=iw/3:ih{blur_filter}[s_right];[s_left][s_middle][s_right]hstack=inputs=3{next_stream}"
            elif ratio == 'center-large':
                split_graph = f"split=3[v_left_in][v_middle_in][v_right_in];[v_left_in]crop=iw/2:ih:0:0[c_left];[c_left]scale=iw/4:ih{blur_filter}[s_left];[v_middle_in]scale=iw/2:ih[s_middle];[v_right_in]crop=iw/2:ih:iw/2:0[c_right];[c_right]scale=iw/4:ih{blur_filter}[s_right];[s_left][s_middle][s_right]hstack=inputs=3{next_stream}"
            elif ratio == 'edges-large':
                split_graph = f"split=3[v_left_in][v_middle_in][v_right_in];[v_left_in]crop=iw/2:ih:0:0[c_left];[c_left]scale=3*iw/8:ih{blur_filter}[s_left];[v_middle_in]scale=iw/4:ih[s_middle];[v_right_in]crop=iw/2:ih:iw/2:0[c_right];[c_right]scale=3*iw/8:ih{blur_filter}[s_right];[s_left][s_middle][s_right]hstack=inputs=3{next_stream}"
        
        video_filters.append(f"{current_stream}{split_graph}")
        current_stream = next_stream

    # 8. 动态缩放
    zoom = settings.get('zoom', {})
    if zoom.get('enabled', False):
        zoom_min = zoom.get('min', 0.01)
        zoom_max = zoom.get('max', 0.10)
        direction = zoom.get('direction', 'in')
        next_stream = get_next_stream_label()
        
        zoom_expr = ""
        if direction == 'in':
            zoom_expr = f"zoompan=z='min(zoom+{zoom_max},1.5)':d=1:x=iw/2-(iw/zoom/2):y=ih/2-(ih/zoom/2)"
        elif direction == 'out':
            zoom_expr = f"zoompan=z='max(zoom-{zoom_max},1)':d=1:x=iw/2-(iw/zoom/2):y=ih/2-(ih/zoom/2)"
        
        video_filters.append(f"{current_stream}{zoom_expr}{next_stream}")
        current_stream = next_stream

    # AB帧融合和其他复杂滤镜可以按此模式继续添加...
    # (为简化，此处暂不重构AB帧融合，因为它需要多路输入)

    # --- 音频滤镜 ---
    if ab_fusion.get('enabled', False) and ab_fusion.get('audioPhaseAdjust', False):
        audio_filters.append('aeval=val(0)*0.9+val(1)*0.1:c=same')
        douyin_logger.info("🎵 音频相位调整已启用")
    
    # --- 命令组装 ---

    # 应用视频滤镜
    if video_filters:
        filter_complex_string = ";".join(video_filters)
        cmd.extend(['-filter_complex', filter_complex_string])
        cmd.extend(['-map', current_stream])
        douyin_logger.info(f"应用视频滤镜链: {filter_complex_string}")
    else:
        cmd.extend(['-map', '0:v'])

    # 应用音频滤镜或复制音频流
    if audio_filters:
        cmd.extend(['-af', ",".join(audio_filters)])
        cmd.extend(['-c:a', 'aac', '-b:a', '192k'])
        cmd.extend(['-map', '0:a?'])
        douyin_logger.info(f"应用音频滤镜: {','.join(audio_filters)}")
    else:
        # 如果有视频滤镜，即使不处理音频，也需要显式映射
        cmd.extend(['-map', '0:a?'])
        cmd.extend(['-c:a', 'copy'])

    # 元数据伪装和关键帧修改（通常与AB融合相关）
    if ab_fusion.get('enabled', False):
        if ab_fusion.get('metadataDisguise', False):
            timestamp = int(time.time())
            cmd.extend([
                '-metadata', f'title=Processed_Video_{timestamp}',
                '-metadata', f'comment=Generated_at_{timestamp}'
            ])
            douyin_logger.info("🏷️  元数据伪装已启用")
        
        if ab_fusion.get('keyframeModify', False):
            cmd.extend(['-g', '25', '-keyint_min', '12'])
            douyin_logger.info("🔑 关键帧分布修改已启用")

    # 帧率设置 (保持原始帧率)
    framerate = settings.get('framerate', {})
    if False:  # 禁用帧率修改
        target_fps = framerate.get('target', 30)
        cmd.extend(['-r', str(target_fps)])
    
    # 码率设置
    bitrate = settings.get('bitrate', {})
    if not bitrate.get('keep_original', False):
        if bitrate.get('mode') == 'fixed':
            fixed_bitrate = bitrate.get('fixed', 3000)
            cmd.extend(['-b:v', f'{fixed_bitrate}k'])
        else:
            multiplier = (bitrate.get('min', 1.05) + bitrate.get('max', 1.95)) / 2
            cmd.extend(['-q:v', str(int(28 / multiplier))])

    # 输出设置
    cmd.extend(['-y', output_path])
    
    return cmd

@app.route('/test_status')
def test_status():
    return send_from_directory('.', 'test_status.html')

@app.route('/api/videos')
def list_videos():
    result = []
    
    def scan_dir(path, parent=""):
        items = []
        for item in sorted(os.listdir(path)):
            full_path = os.path.join(path, item)
            if os.path.isdir(full_path):
                children = scan_dir(full_path, os.path.join(parent, item))
                items.append({
                    "name": item,
                    "path": os.path.join(parent, item).replace('\\', '/'),  # 修复路径格式
                    "type": "folder",
                    "children": children
                })
            elif os.path.isfile(full_path) and full_path.lower().endswith(VIDEO_EXTS):
                items.append({
                    "name": item,
                    "path": os.path.join(parent, item).replace('\\', '/'),  # 修复路径格式
                    "type": "file"
                })
        return items
    
    if os.path.exists("videos"):
        result = scan_dir("videos")
    
    return jsonify(result)

@app.route('/api/folder_videos', methods=['POST'])
def get_folder_videos():
    """获取指定文件夹中的所有视频文件"""
    try:
        folder_path = request.json.get('folder_path')
        if not folder_path:
            return jsonify({"success": False, "message": "未提供文件夹路径"}), 400
        
        # 构建完整路径
        full_path = os.path.join("videos", folder_path)
        
        # 验证路径安全性
        if '..' in folder_path or not os.path.commonpath([os.path.abspath("videos"), os.path.abspath(full_path)]) == os.path.abspath("videos"):
            return jsonify({"success": False, "message": "无效的文件夹路径"}), 400
        
        if not os.path.exists(full_path) or not os.path.isdir(full_path):
            return jsonify({"success": False, "message": "文件夹不存在"}), 404
        
        # 递归获取文件夹中的所有视频文件
        def get_all_videos(directory, relative_path=""):
            videos = []
            try:
                for item in os.listdir(directory):
                    item_path = os.path.join(directory, item)
                    item_relative_path = os.path.join(relative_path, item) if relative_path else item
                    
                    if os.path.isdir(item_path):
                        # 递归处理子文件夹
                        videos.extend(get_all_videos(item_path, item_relative_path))
                    elif os.path.isfile(item_path) and item_path.lower().endswith(VIDEO_EXTS):
                        videos.append({
                            "name": item,
                            "path": os.path.join(folder_path, item_relative_path).replace('\\', '/')
                        })
            except Exception as e:
                douyin_logger.warning(f"扫描文件夹 {directory} 时出错: {str(e)}")
            
            return videos
        
        videos = get_all_videos(full_path)
        
        return jsonify({
            "success": True,
            "videos": videos,
            "count": len(videos)
        })
        
    except Exception as e:
        douyin_logger.error(f"获取文件夹视频列表时发生错误: {str(e)}")
        return jsonify({"success": False, "message": f"获取视频列表失败: {str(e)}"}), 500

@app.route('/api/cookies')
def list_cookies():
    cookies = []
    if os.path.exists("cookie"):
        for f in os.listdir("cookie"):
            if f.endswith(".json"):
                # 简单的名称处理，去掉.json后缀作为显示名称
                display_name = f.replace('.json', '')
                cookies.append({
                    "filename": f,
                    "name": display_name,
                    "expired": False  # 暂时设为False，可以后续添加过期检测逻辑
                })
    return jsonify({"cookies": cookies})

@app.route('/api/generate_cookie', methods=['POST'])
def generate_cookie():
    name = request.json.get('name')
    proxy_id = request.json.get('proxy_id')  # 获取代理ID
    
    if not name:
        return jsonify({"success": False, "message": "未提供cookie名称"}), 400
    
    filename = name.strip() + ".json"
    path = os.path.join("cookie", filename)
    session_id = f"cookie_gen_{int(time.time())}"
    
    def gen_cookie_thread():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            # 使用带截图功能的cookie生成函数，传入代理ID
            loop.run_until_complete(douyin_cookie_gen_with_screenshots(path, session_id, proxy_id))
            
            # 如果指定了代理，生成cookie后自动分配代理关系
            if proxy_id:
                try:
                    from utils.proxy_manager import proxy_manager
                    cookie_name = os.path.basename(path)
                    proxy_manager.assign_proxy_to_cookie(cookie_name, proxy_id)
                    douyin_logger.info(f"已自动为Cookie {cookie_name} 分配代理 {proxy_id}")
                except Exception as e:
                    douyin_logger.warning(f"分配代理失败: {str(e)}")
            
            return {"success": True, "message": f"cookie已保存到: {path}"}
        except Exception as e:
            return {"success": False, "message": f"生成cookie失败: {str(e)}"}
        finally:
            # 清理截图数据
            if session_id in browser_screenshot_data:
                del browser_screenshot_data[session_id]
            if session_id in active_browser_sessions:
                del active_browser_sessions[session_id]
            loop.close()
    
    thread = threading.Thread(target=gen_cookie_thread)
    thread.start()
    
    proxy_message = ""
    if proxy_id:
        try:
            from utils.proxy_manager import proxy_manager
            proxy_info = proxy_manager.get_proxy_by_id(proxy_id)
            if proxy_info:
                proxy_message = f"，使用代理: {proxy_info.get('name', 'Unknown')}"
        except:
            pass
    
    return jsonify({
        "success": True, 
        "message": f"正在生成cookie{proxy_message}，请稍后刷新列表",
        "session_id": session_id
    })

@app.route('/api/delete_cookie', methods=['DELETE'])
def delete_cookie():
    try:
        cookie_file = request.json.get('cookie_file')
        if not cookie_file:
            return jsonify({"success": False, "message": "未提供cookie文件名"}), 400
        
        # 验证文件名，防止路径遍历攻击
        if '..' in cookie_file or '/' in cookie_file or '\\' in cookie_file:
            return jsonify({"success": False, "message": "无效的文件名"}), 400
        
        # 确保是.json文件
        if not cookie_file.endswith('.json'):
            return jsonify({"success": False, "message": "只能删除.json格式的cookie文件"}), 400
        
        cookie_path = os.path.join("cookie", cookie_file)
        
        # 检查文件是否存在
        if not os.path.exists(cookie_path):
            return jsonify({"success": False, "message": "cookie文件不存在"}), 404
        
        # 删除文件
        os.remove(cookie_path)
        douyin_logger.info(f"已删除cookie文件: {cookie_file}")
        
        # 同时删除对应的代理映射关系
        try:
            from utils.proxy_manager import proxy_manager
            success, message = proxy_manager.remove_cookie_proxy(cookie_file)
            if success:
                douyin_logger.info(f"已删除cookie {cookie_file} 的代理映射关系")
            else:
                douyin_logger.warning(f"删除代理映射关系失败: {message}")
        except Exception as e:
            douyin_logger.warning(f"删除代理映射关系时发生异常: {str(e)}")
        
        # 同时删除对应的浏览器指纹
        try:
            from utils.fingerprint_manager import fingerprint_manager
            success, message = fingerprint_manager.delete_fingerprint(cookie_file)
            if success:
                douyin_logger.info(f"已删除cookie {cookie_file} 的浏览器指纹")
            else:
                douyin_logger.warning(f"删除浏览器指纹失败: {message}")
        except Exception as e:
            douyin_logger.warning(f"删除浏览器指纹时发生异常: {str(e)}")
        
        return jsonify({"success": True, "message": f"成功删除cookie文件和相关配置: {cookie_file}"})
        
    except Exception as e:
        douyin_logger.error(f"删除cookie文件时发生错误: {str(e)}")
        return jsonify({"success": False, "message": f"删除失败: {str(e)}"}), 500

# ==================== 代理管理 API ====================

@app.route('/api/proxies', methods=['GET'])
def get_proxies():
    """获取所有代理"""
    try:
        proxies = proxy_manager.get_all_proxies()
        return jsonify({"success": True, "proxies": proxies})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

@app.route('/api/proxies', methods=['POST'])
def add_proxy():
    """添加代理"""
    try:
        data = request.json
        name = data.get('name')
        host = data.get('host')
        port = data.get('port')
        username = data.get('username')
        password = data.get('password')
        protocol = data.get('protocol', 'http')
        
        if not all([name, host, port]):
            return jsonify({"success": False, "message": "代理名称、主机和端口为必填项"}), 400
        
        try:
            port = int(port)
        except ValueError:
            return jsonify({"success": False, "message": "端口必须是数字"}), 400
        
        success, result = proxy_manager.add_proxy(name, host, port, username, password, protocol)
        
        if success:
            return jsonify({"success": True, "message": "代理添加成功", "proxy_id": result})
        else:
            return jsonify({"success": False, "message": result}), 400
            
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

@app.route('/api/proxies/<int:proxy_id>', methods=['DELETE'])
def delete_proxy(proxy_id):
    """删除代理"""
    try:
        success, message = proxy_manager.delete_proxy(proxy_id)
        
        if success:
            return jsonify({"success": True, "message": message})
        else:
            return jsonify({"success": False, "message": message}), 400
            
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

@app.route('/api/proxies/<int:proxy_id>/test', methods=['POST'])
def test_proxy(proxy_id):
    """测试代理连接"""
    async def test_proxy_async():
        try:
            success, ip_info = await proxy_manager.check_proxy_status(proxy_id)
            return success, ip_info
        except Exception as e:
            return False, str(e)
    
    def run_test():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(test_proxy_async())
        finally:
            loop.close()
    
    try:
        success, result = run_test()
        
        if success:
            return jsonify({"success": True, "message": "代理连接正常", "ip_info": result})
        else:
            return jsonify({"success": False, "message": f"代理连接失败: {result}"})
            
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

@app.route('/api/proxy_mappings', methods=['GET'])
def get_proxy_mappings():
    """获取cookie-代理映射"""
    try:
        mappings = proxy_manager.get_cookie_proxy_mappings()
        return jsonify({"success": True, "mappings": mappings})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

# ==================== 浏览器指纹管理 API ====================

@app.route('/api/fingerprints', methods=['GET'])
def get_fingerprints():
    """获取所有浏览器指纹信息"""
    try:
        from utils.fingerprint_manager import fingerprint_manager
        fingerprints = fingerprint_manager.get_all_fingerprints()
        return jsonify({"success": True, "fingerprints": fingerprints})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

@app.route('/api/fingerprints/<cookie_name>', methods=['GET'])
def get_fingerprint_details(cookie_name):
    """获取指定Cookie的指纹详情"""
    try:
        from utils.fingerprint_manager import fingerprint_manager
        fingerprint = fingerprint_manager.get_or_create_fingerprint(cookie_name)
        
        # 检查指纹一致性
        is_consistent, issues = fingerprint_manager.check_fingerprint_consistency(cookie_name)
        
        # 添加一致性信息到响应
        response_data = {
            "success": True, 
            "fingerprint": fingerprint,
            "consistency": {
                "is_consistent": is_consistent,
                "issues": issues,
                "check_time": datetime.now().isoformat()
            }
        }
        
        return jsonify(response_data)
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

@app.route('/api/fingerprints/<cookie_name>/regenerate', methods=['POST'])
def regenerate_fingerprint(cookie_name):
    """重新生成指定Cookie的浏览器指纹"""
    try:
        from utils.fingerprint_manager import fingerprint_manager
        
        # 先删除现有指纹
        fingerprint_manager.delete_fingerprint(cookie_name)
        
        # 生成新指纹
        new_fingerprint = fingerprint_manager.get_or_create_fingerprint(cookie_name)
        
        return jsonify({
            "success": True, 
            "message": f"已为 {cookie_name} 重新生成浏览器指纹",
            "fingerprint": new_fingerprint
        })
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

@app.route('/api/fingerprints/<cookie_name>', methods=['DELETE'])
def delete_fingerprint(cookie_name):
    """删除指定Cookie的浏览器指纹"""
    try:
        from utils.fingerprint_manager import fingerprint_manager
        
        # 删除指纹
        fingerprint_manager.delete_fingerprint(cookie_name)
        
        return jsonify({
            "success": True, 
            "message": f"已删除 {cookie_name} 的浏览器指纹"
        })
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

@app.route('/api/fingerprints/regenerate_all', methods=['POST'])
def regenerate_all_fingerprints():
    """批量重新生成所有指纹（修复不一致问题）"""
    try:
        from utils.fingerprint_manager import fingerprint_manager
        
        success, message = fingerprint_manager.regenerate_all_fingerprints()
        
        if success:
            return jsonify({
                "success": True, 
                "message": message
            })
        else:
            return jsonify({
                "success": False, 
                "message": message
            }), 500
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

@app.route('/api/fingerprints/check_all', methods=['GET'])
def check_all_fingerprints():
    """检查所有指纹的一致性"""
    try:
        from utils.fingerprint_manager import fingerprint_manager
        
        fingerprints = fingerprint_manager.get_all_fingerprints()
        results = []
        
        for fp in fingerprints:
            cookie_name = fp['cookie_name']
            is_consistent, issues = fingerprint_manager.check_fingerprint_consistency(cookie_name)
            
            results.append({
                "cookie_name": cookie_name,
                "is_consistent": is_consistent,
                "issues": issues,
                "created_time": fp.get('created_time'),
                "last_used": fp.get('last_used')
            })
        
        # 统计信息
        total_count = len(results)
        consistent_count = sum(1 for r in results if r["is_consistent"])
        inconsistent_count = total_count - consistent_count
        
        return jsonify({
            "success": True,
            "results": results,
            "statistics": {
                "total": total_count,
                "consistent": consistent_count,
                "inconsistent": inconsistent_count
            }
        })
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

@app.route('/api/history', methods=['GET'])
def api_history():
    cookie = request.args.get('cookie')
    rows = get_history(cookie)
    success = sum(1 for r in rows if r[2] == 'success')
    fail = sum(1 for r in rows if r[2] == 'fail')
    
    # 只返回最近的10条记录，但保留总计数
    limited_rows = rows[:10] if len(rows) > 10 else rows
    
    return jsonify({
        "history": [dict(zip(['filename','upload_time','status','reason','url'], r)) for r in limited_rows],
        "success": success,
        "fail": fail,
        "total": len(rows)  # 添加总记录数
    })

@app.route('/api/upload', methods=['POST'])
def upload_videos():
    global is_uploading
    
    if is_uploading:
        return jsonify({"success": False, "message": "已有上传任务在进行中"}), 400
    
    data = request.json
    videos = data.get('videos', [])
    cookie = data.get('cookie', '')
    location = data.get('location', '杭州市')
    upload_interval = int(data.get('upload_interval', 5))
    publish_type = data.get('publish_type', 'now')
    # 风控阈值
    risk_limit = int(data.get('risk_limit', 5))
    # 风控检测
    count = get_upload_count_last_hour(cookie)
    if count >= risk_limit:
        return jsonify({"success": False, "message": f"上传过于频繁，已自动延迟（每小时最多{risk_limit}个）"}), 429
    # 内容合规检测（仅当v为dict且有title/desc时才检测）
    for v in videos:
        if isinstance(v, dict):
            ok, msg = check_content_compliance(v.get('title',''), v.get('desc',''))
            if not ok:
                return jsonify({"success": False, "message": msg}), 400
    
    # 记录上传参数到日志
    print(f"[DEBUG] 上传参数: 视频数量={len(videos)}, Cookie={cookie}, 位置={location}, 间隔={upload_interval}分钟")
    
    if not videos:
        return jsonify({"success": False, "message": "上传队列为空"}), 400
    
    if not cookie:
        return jsonify({"success": False, "message": "请选择cookie文件"}), 400
    
    # 处理发布时间
    publish_date = 0
    if publish_type == 'schedule':
        date_str = data.get('date')
        hour = data.get('hour', '00')
        minute = data.get('minute', '00')
        if not date_str:
            return jsonify({"success": False, "message": "请选择定时日期"}), 400
        try:
            publish_time = f"{date_str} {hour}:{minute}"
            publish_date = datetime.strptime(publish_time, "%Y-%m-%d %H:%M")
            if publish_date < datetime.now():
                return jsonify({"success": False, "message": "不能选择当前时间之前的日期和时间"}), 400
        except Exception:
            return jsonify({"success": False, "message": "定时发布时间格式错误"}), 400
    
    account_file = os.path.join("cookie", cookie)
    
    # 先进行基本的文件检查
    if not os.path.exists(account_file):
        return jsonify({"success": False, "message": "Cookie文件不存在"}), 400
    
    # 检查文件大小（空文件或过小的文件通常无效）
    try:
        file_size = os.path.getsize(account_file)
        if file_size < 100:  # 小于100字节的cookie文件通常是无效的
            douyin_logger.warning(f"Cookie文件过小可能无效: {file_size}字节")
    except Exception as e:
        douyin_logger.error(f"无法读取cookie文件大小: {str(e)}")
    
    # 先检查cookie有效性（带重试机制）
    def check_cookie_validity():
        max_retries = 2
        for attempt in range(max_retries):
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                from main import cookie_auth
                result = loop.run_until_complete(cookie_auth(account_file))
                douyin_logger.info(f"Cookie验证结果: {result} for {cookie} (尝试 {attempt + 1}/{max_retries})")
                return result
            except Exception as e:
                douyin_logger.error(f"检查cookie有效性失败 (尝试 {attempt + 1}/{max_retries}): {str(e)}")
                
                # 如果是明确的登录相关错误，直接返回失效
                if "登录" in str(e) or "手机号" in str(e) or "login" in str(e).lower():
                    return False
                
                # 如果是最后一次尝试失败，根据错误类型决定
                if attempt == max_retries - 1:
                    # 检查是否是已知的技术错误
                    technical_errors = ["warning", "attribute", "timeout", "network", "connection"]
                    if any(err in str(e).lower() for err in technical_errors):
                        douyin_logger.warning(f"Cookie验证遇到技术错误，假定有效: {str(e)}")
                        return True
                    else:
                        # 未知错误，保险起见认为失效
                        return False
                else:
                    # 还有重试机会，等待一下再试
                    import time
                    time.sleep(1)
            finally:
                loop.close()
        
        # 理论上不会到达这里
        return False
    
    if not check_cookie_validity():
        # Cookie失效，跳过上传任务
        douyin_logger.warning(f"Cookie {cookie} 已失效，跳过上传任务")
        
        return jsonify({
            "success": False, 
            "message": f"Cookie {cookie} 已失效，已跳过上传任务", 
            "cookie_expired": True,
            "cookie_file": cookie,
            "skip_upload": True  # 标记为跳过上传
        })
    
    # 启动批量上传线程
    thread = threading.Thread(
        target=batch_upload_thread,
        args=(videos, account_file, location, publish_date, upload_interval, risk_limit)
    )
    thread.start()
    
    return jsonify({"success": True, "message": "上传任务已开始"})

@app.route('/api/upload_status')
def upload_status():
    return jsonify({
        "is_uploading": is_uploading,
        "tasks": upload_tasks
    })

@app.route('/videos/<path:filename>')
def serve_video(filename):
    # 支持子文件夹结构的视频文件访问
    video_path = os.path.join('videos', filename)
    if os.path.exists(video_path):
        return send_from_directory('videos', filename)
    else:
        return "视频文件不存在", 404

# 提供downloads文件夹中视频文件的访问
@app.route('/videos/downloads/<folder_name>/<video_name>')
def serve_downloads_video(folder_name, video_name):
    downloads_path = os.path.join(os.getcwd(), 'downloads')
    return send_from_directory(os.path.join(downloads_path, folder_name), video_name)

# 删除本地视频文件夹
@app.route('/api/videos/delete_folder', methods=['POST'])
def delete_video_folder():
    """删除videos目录下的文件夹及其所有内容"""
    try:
        data = request.get_json()
        folder_path = data.get('folder_path')
        folder_name = data.get('folder_name')
        
        if not folder_path:
            return jsonify({
                "success": False,
                "message": "未提供文件夹路径"
            }), 400
        
        # 安全检查：确保路径在videos目录下
        full_path = os.path.join("videos", folder_path)
        videos_abs_path = os.path.abspath("videos")
        target_abs_path = os.path.abspath(full_path)
        
        if not target_abs_path.startswith(videos_abs_path):
            return jsonify({
                "success": False,
                "message": "无效的文件夹路径"
            }), 400
        
        if not os.path.exists(full_path):
            return jsonify({
                "success": False,
                "message": "文件夹不存在"
            }), 404
        
        if not os.path.isdir(full_path):
            return jsonify({
                "success": False,
                "message": "指定路径不是文件夹"
            }), 400
        
        # 统计删除的文件数量
        deleted_count = 0
        for root, dirs, files in os.walk(full_path):
            deleted_count += len(files)
        
        # 删除文件夹及其所有内容
        shutil.rmtree(full_path)
        
        return jsonify({
            "success": True,
            "message": f"文件夹 '{folder_name}' 删除成功",
            "deleted_count": deleted_count
        })
        
    except Exception as e:
        print(f"删除文件夹时发生错误: {str(e)}")
        return jsonify({
            "success": False,
            "message": f"删除文件夹失败: {str(e)}"
        }), 500

# 删除本地视频文件
@app.route('/api/videos/delete_file', methods=['POST'])
def delete_video_file():
    """删除videos目录下的单个文件"""
    try:
        data = request.get_json()
        file_path = data.get('file_path')
        file_name = data.get('file_name')
        
        if not file_path:
            return jsonify({
                "success": False,
                "message": "未提供文件路径"
            }), 400
        
        # 安全检查：确保路径在videos目录下
        full_path = os.path.join("videos", file_path)
        videos_abs_path = os.path.abspath("videos")
        target_abs_path = os.path.abspath(full_path)
        
        if not target_abs_path.startswith(videos_abs_path):
            return jsonify({
                "success": False,
                "message": "无效的文件路径"
            }), 400
        
        if not os.path.exists(full_path):
            return jsonify({
                "success": False,
                "message": "文件不存在"
            }), 404
        
        if not os.path.isfile(full_path):
            return jsonify({
                "success": False,
                "message": "指定路径不是文件"
            }), 400
        
        # 删除文件
        os.remove(full_path)
        
        # 同时删除可能存在的相关文件（txt描述文件、封面图片等）
        base_name = os.path.splitext(full_path)[0]
        related_files = []
        
        # 查找并删除txt文件
        txt_file = base_name + '.txt'
        if os.path.exists(txt_file):
            os.remove(txt_file)
            related_files.append('txt描述文件')
        
        # 查找并删除封面图片
        for ext in ['.jpg', '.jpeg', '.png', '.webp']:
            img_file = base_name + ext
            if os.path.exists(img_file):
                os.remove(img_file)
                related_files.append('封面图片')
                break
        
        message = f"文件 '{file_name}' 删除成功"
        if related_files:
            message += f"，同时删除了{', '.join(related_files)}"
        
        return jsonify({
            "success": True,
            "message": message
        })
        
    except Exception as e:
        print(f"删除文件时发生错误: {str(e)}")
        return jsonify({
            "success": False,
            "message": f"删除文件失败: {str(e)}"
        }), 500

def get_title_tags_from_txt(video_path):
    txt_path = os.path.splitext(video_path)[0] + ".txt"
    if os.path.exists(txt_path):
        with open(txt_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
            if lines:
                title = lines[0].strip()
                tags = [tag.lstrip('#').strip() for tag in " ".join(lines[1:]).split() if tag.startswith("#")]
                return title, tags
    return os.path.splitext(os.path.basename(video_path))[0], []

def batch_upload_thread(videos, account_file, location, publish_date, upload_interval=5, risk_limit=5):
    global is_uploading, upload_tasks
    
    # 确保upload_interval是一个合法的整数
    try:
        upload_interval = int(upload_interval)
        if upload_interval < 1:
            upload_interval = 1
    except:
        upload_interval = 5
        
    # 确保risk_limit是一个合法的整数
    try:
        risk_limit = int(risk_limit)
        if risk_limit < 1:
            risk_limit = 1
    except:
        risk_limit = 5
    
    is_uploading = True
    
    # 创建视频列表的副本，避免重复上传
    videos_to_upload = list(videos)  # 创建副本
    upload_tasks = [{"path": v, "name": os.path.basename(v), "status": "等待中"} for v in videos_to_upload]
    
    # 记录实际使用的上传间隔
    print(f"[DEBUG] 批量上传开始: 视频数量={len(videos_to_upload)}, 上传间隔={upload_interval}分钟")
    
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        # 使用while循环而不是for循环，确保可以动态移除已上传的视频
        while videos_to_upload:
            print(f"[DEBUG] 当前要上传的视频列表: {[os.path.basename(v) for v in videos_to_upload]}")
            # 风控检测
            cookie_name = os.path.basename(account_file)
            count = get_upload_count_last_hour(cookie_name)
            if count >= risk_limit:
                # 更新所有任务状态为等待风控
                wait_message = f"风控限制：每小时最多{risk_limit}个，已上传{count}个，等待中..."
                douyin_logger.warning(f"账号 {cookie_name} 上传过于频繁，已自动延迟（每小时最多{risk_limit}个，已上传{count}个）")
                for task in upload_tasks:
                    if task["status"] == "等待中" or task["status"] == "上传中":
                        task["status"] = wait_message
                # 等待一小时后再继续
                time.sleep(60 * 60)  # 等待1小时
                # 恢复等待状态
                for task in upload_tasks:
                    if task["status"] == wait_message:
                        task["status"] = "等待中"
                continue
            
            # 取出第一个视频进行上传
            video_path = videos_to_upload[0]
            
            # 更新状态
            for task in upload_tasks:
                if task["path"] == video_path:
                    task["status"] = "上传中"
                    break
            
            video_name = os.path.basename(video_path)
            title, tags = get_title_tags_from_txt(os.path.join("videos", video_path))
            
            try:
                # 创建状态更新回调函数
                def update_status_callback(status_message):
                    for task in upload_tasks:
                        if task["path"] == video_path:
                            task["status"] = status_message
                            break
                
                upload_result = loop.run_until_complete(async_upload(video_path, account_file, title, tags, location, publish_date, update_status_callback))
                
                # 根据上传结果更新状态
                if upload_result:
                    # 更新状态为完成
                    for task in upload_tasks:
                        if task["path"] == video_path:
                            task["status"] = "上传成功"
                            break
                    douyin_logger.info(f"[+] 视频 {video_name} 上传成功")
                    # 写入历史（成功）
                    log_upload_history(
                        cookie_name=os.path.basename(account_file),
                        filename=os.path.basename(video_path),
                        status="success",
                        reason="上传成功"
                    )
                else:
                    # 检查是否是因为重复导致的失败
                    from utils.md5_manager import md5_manager
                    full_path = os.path.join("videos", video_path)
                    if os.path.exists(full_path) and md5_manager.is_duplicate(full_path):
                        # 更新状态为重复
                        for task in upload_tasks:
                            if task["path"] == video_path:
                                task["status"] = "视频重复"
                                break
                        douyin_logger.warning(f"视频 {video_name} 重复，已跳过")
                        log_upload_history(
                            cookie_name=os.path.basename(account_file),
                            filename=os.path.basename(video_path),
                            status="skipped",
                            reason="视频重复"
                        )
                    else:
                        # 更新状态为失败
                        for task in upload_tasks:
                            if task["path"] == video_path:
                                task["status"] = "上传失败"
                                break
                        douyin_logger.error(f"视频 {video_name} 上传失败")
                        log_upload_history(
                            cookie_name=os.path.basename(account_file),
                            filename=os.path.basename(video_path),
                            status="failed",
                            reason="上传失败"
                        )
                
                # 从待上传列表中移除已处理的视频
                videos_to_upload.pop(0)
                
                # 如果还有视频要上传，并且上一个视频成功上传了（不是被跳过的），才等待间隔时间
                if videos_to_upload and upload_result is not False:  # False表示视频被跳过或上传失败
                    douyin_logger.info(f"[+] 等待上传间隔 {upload_interval} 分钟后继续上传下一个视频")
                    time.sleep(upload_interval * 60)
                elif videos_to_upload:
                    douyin_logger.info(f"[+] 跳过等待间隔，立即处理下一个视频")
                
            except Exception as e:
                douyin_logger.error(f"上传视频 {video_path} 时发生错误: {str(e)}")
                # 更新状态为失败
                for task in upload_tasks:
                    if task["path"] == video_path:
                        task["status"] = f"上传失败: {str(e)}"
                        break
                log_upload_history(
                    cookie_name=os.path.basename(account_file),
                    filename=os.path.basename(video_path),
                    status="failed",
                    reason=str(e)
                )
                # 从待上传列表中移除失败的视频
                videos_to_upload.pop(0)
                
                # 如果还有视频要上传，等待指定的间隔时间
                if videos_to_upload:
                    douyin_logger.info(f"[+] 等待上传间隔 {upload_interval} 分钟后继续上传下一个视频")
                    time.sleep(upload_interval * 60)
        
    except Exception as e:
        douyin_logger.error(f"批量上传任务失败: {str(e)}")
        # 更新所有未完成任务的状态为失败
        for task in upload_tasks:
            if task["status"] not in ["上传成功", "上传失败"]:
                task["status"] = f"任务失败: {str(e)}"
    finally:
        is_uploading = False
        if loop and not loop.is_closed():
            loop.close()

async def async_upload(file_path, account_file, title, tags, location, publish_date, status_callback=None):
    full_path = os.path.join("videos", file_path)
    
    if status_callback:
        status_callback("检查视频MD5...")
    
    # 导入MD5管理器并检查视频是否重复
    from utils.md5_manager import md5_manager
    if md5_manager.is_duplicate(full_path):
        if status_callback:
            status_callback("视频重复，跳过上传")
        douyin_logger.warning(f"检测到重复视频，跳过上传: {os.path.basename(full_path)}")
        return False  # 视频重复，返回上传失败
    
    if status_callback:
        status_callback("验证登录中...")
    
    try:
        ok = await douyin_setup(account_file, handle=True, use_websocket=True, websocket_callback=douyin_cookie_gen_with_screenshots)
        if not ok:
            raise Exception("cookie文件无效或登录失败")
            
        async with asyncio.Semaphore(1):
            from playwright.async_api import async_playwright
            async with async_playwright() as playwright:
                if status_callback:
                    status_callback("准备上传中...")
                
                video = DouYinVideo(
                    title=title, 
                    file_path=full_path, 
                    tags=tags, 
                    publish_date=publish_date, 
                    account_file=account_file, 
                    thumbnail_path=None
                )
                
                class StatusHandler:
                    @staticmethod
                    async def handle_event(event, message):
                        if status_callback:
                            if event == "upload_start":
                                status_callback("开始上传视频...")
                            elif event == "upload_progress":
                                status_callback(f"上传中: {message}")
                            elif event == "upload_complete":
                                status_callback("视频上传完成")
                            elif event == "upload_failed":
                                status_callback(f"上传失败: {message}")
                            elif event == "duplicate_detected":  # 新增事件处理
                                status_callback(f"视频重复: {message}")
                            elif event == "publish_start":
                                status_callback("开始发布...")
                            elif event == "publish_complete":
                                status_callback("发布完成")
                            else:
                                status_callback(message)
                
                # 添加状态处理器
                video.status_handler = StatusHandler()
                upload_result = await video.main()  # 使用改进后的main方法，会自动记录MD5
                
                # 如果是由于视频重复导致的跳过，会返回False
                if upload_result is False:
                    if status_callback:
                        status_callback("视频已存在，已跳过上传")
                    return False
                
                return upload_result  # 返回上传结果
    except Exception as e:
        douyin_logger.error(f"上传过程中发生错误: {str(e)}")
        if status_callback:
            status_callback(f"上传失败: {str(e)[:50]}")
        return False  # 返回上传失败

def check_content_compliance(title, desc):
    sensitive_words = ['违规','违法','敏感']
    for w in sensitive_words:
        if w in (title or '') or w in (desc or ''):
            return False, f'内容含敏感词：{w}'
    return True, ''

def notify_cookie_expired(account_file, session_id):
    """通知前端cookie失效"""
    try:
        socketio.emit('cookie_expired', {
            'session_id': session_id,
            'cookie_file': os.path.basename(account_file),
            'message': f'Cookie文件 {os.path.basename(account_file)} 已失效，请重新登录'
        })
        douyin_logger.info(f"已发送cookie失效通知到前端: {os.path.basename(account_file)}")
    except Exception as e:
        douyin_logger.error(f"发送cookie失效通知失败: {str(e)}")

async def douyin_cookie_gen_with_screenshots(account_file, session_id, proxy_id=None):
    """带截图功能的Cookie生成函数"""
    from utils.proxy_manager import proxy_manager
    from utils.base_social_media import set_init_script
    from utils.fingerprint_manager import fingerprint_manager
    from playwright.async_api import async_playwright
    
    from main import get_browser_launch_options
    
    cookie_filename = os.path.basename(account_file)
    
    # 获取代理配置
    if proxy_id:
        # 使用指定的代理
        proxy_config = proxy_manager.get_proxy_for_playwright_by_id(proxy_id)
        douyin_logger.info(f"使用指定代理 {proxy_id} 生成Cookie")
    else:
        # 使用默认逻辑（根据cookie文件名获取代理）
        proxy_config = proxy_manager.get_proxy_for_playwright(cookie_filename)
        
    # 获取浏览器指纹配置
    fingerprint_config = fingerprint_manager.get_playwright_config(cookie_filename)
    
    # 检测是否在Docker容器中，如果是则强制使用headless模式
    is_in_docker = os.path.exists('/.dockerenv') or os.environ.get('DOCKER_ENV') == 'true'
    headless_mode = True if is_in_docker else False
    
    if is_in_docker:
        print(f"🐳 检测到Docker环境，使用headless模式进行截图")
        douyin_logger.info(f"Docker环境检测：使用headless模式 for session {session_id}")
    else:
        print(f"💻 本地环境，使用非headless模式")
        douyin_logger.info(f"本地环境检测：使用非headless模式 for session {session_id}")
    
    options = get_browser_launch_options(headless=headless_mode, proxy_config=proxy_config)
    
    # 检查是否是因为cookie失效而重新生成
    is_cookie_regeneration = session_id.startswith('cookie_regen_')
    if is_cookie_regeneration:
        # 通知前端cookie失效，需要重新登录
        notify_cookie_expired(account_file, session_id)

    async with async_playwright() as playwright:
        try:
            print(f"🚀 启动浏览器: headless={headless_mode}, session_id={session_id}")
            douyin_logger.info(f"启动浏览器配置: {options}")
            browser = await playwright.chromium.launch(**options)
            print(f"✅ 浏览器启动成功")
        except Exception as e:
            error_msg = f"浏览器启动失败: {str(e)}"
            print(f"❌ {error_msg}")
            douyin_logger.error(error_msg)
            socketio.emit('browser_status', {
                'session_id': session_id,
                'status': 'error',
                'message': error_msg
            })
            return
        
        # 使用指纹配置创建上下文
        context_options = {
            **fingerprint_config
        }
        
        # 添加代理配置
        if proxy_config:
            context_options["proxy"] = proxy_config
            
        context = await browser.new_context(**context_options)
        context = await set_init_script(context, cookie_filename)
        page = await context.new_page()
        
        # 线程安全地标记会话为活跃状态
        with browser_data_lock:
            active_browser_sessions[session_id] = True
            browser_pages[session_id] = page  # 存储页面对象用于点击操作
            browser_click_queue[session_id] = []  # 初始化点击队列
        
        # 启动截图和点击处理任务（降低截图频率提升性能）
        screenshot_task = asyncio.create_task(capture_screenshots(page, session_id, interval=0.5))
        click_task = asyncio.create_task(handle_click_events(page, session_id))
        
        try:
            print(f"🌐 开始加载抖音页面...")
            await page.goto("https://creator.douyin.com/", timeout=30000)
            print(f"✅ 抖音页面加载成功")
            
            # 通知前端浏览器已启动
            socketio.emit('browser_status', {
                'session_id': session_id,
                'status': 'browser_opened',
                'message': '浏览器已启动，页面加载完成，开始截图传输'
            })
            
            # 等待会话关闭（不再使用page.pause()，而是监听会话状态）
            while active_browser_sessions.get(session_id, False):
                await asyncio.sleep(1)
            
            # 会话关闭时自动保存cookie
            try:
                await context.storage_state(path=account_file)
                douyin_logger.info(f"浏览器关闭，已自动保存Cookie到: {account_file}")
                
                # 通知前端Cookie生成完成
                socketio.emit('browser_status', {
                    'session_id': session_id,
                    'status': 'cookie_saved',
                    'message': 'Cookie已保存成功'
                })
            except Exception as e:
                douyin_logger.error(f"保存Cookie失败: {str(e)}")
                socketio.emit('browser_status', {
                    'session_id': session_id,
                    'status': 'error',
                    'message': f'保存Cookie失败: {str(e)}'
                })
            
        except Exception as e:
            douyin_logger.error(f"Cookie生成过程出错: {str(e)}")
            socketio.emit('browser_status', {
                'session_id': session_id,
                'status': 'error',
                'message': f'生成过程出错: {str(e)}'
            })
        finally:
            # 线程安全地停止截图和点击处理
            with browser_data_lock:
                active_browser_sessions[session_id] = False
                
                # 清理会话数据
                try:
                    if session_id in browser_pages:
                        del browser_pages[session_id]
                    if session_id in browser_click_queue:
                        del browser_click_queue[session_id]
                    if session_id in browser_screenshot_data:
                        del browser_screenshot_data[session_id]
                except KeyError:
                    pass  # 资源已经被清理
            
            screenshot_task.cancel()
            click_task.cancel()
            
            try:
                await browser.close()
                douyin_logger.info(f"浏览器已关闭: {session_id}")
            except Exception as e:
                douyin_logger.error(f"关闭浏览器时出错: {str(e)}")

async def capture_screenshots(page, session_id, interval=0.5):
    """捕获页面截图并通过WebSocket发送"""
    last_screenshot_hash = None
    try:
        while True:
            # 线程安全检查会话状态
            with browser_data_lock:
                if not active_browser_sessions.get(session_id, False):
                    break
                    
            try:
                # 截图（完整页面显示）
                screenshot = await safe_screenshot(
                    page,
                    full_page=True,  # 获取完整页面截图
                    type='png'
                    # 移除clip限制，让用户在前端通过缩放查看需要的区域
                )
                
                # 计算截图hash，避免重复发送相同截图
                import hashlib
                screenshot_hash = hashlib.md5(screenshot).hexdigest()
                
                if screenshot_hash != last_screenshot_hash:
                    # 转换为base64
                    screenshot_b64 = base64.b64encode(screenshot).decode('utf-8')
                    screenshot_data = {
                        'data': f"data:image/png;base64,{screenshot_b64}",
                        'timestamp': time.time()
                    }
                    
                    # 线程安全存储到全局变量
                    with browser_data_lock:
                        browser_screenshot_data[session_id] = screenshot_data
                    
                    # 发送到所有连接的客户端
                    print(f"📸 发送新截图到客户端: session_id={session_id}, 数据大小={len(screenshot)} bytes")
                    socketio.emit('browser_screenshot', {
                        'session_id': session_id,
                        'screenshot': screenshot_data['data'],
                        'timestamp': screenshot_data['timestamp']
                    })
                    
                    last_screenshot_hash = screenshot_hash
                else:
                    print(f"⏭️ 跳过重复截图: session_id={session_id}")
                
                await asyncio.sleep(interval)
                
            except Exception as e:
                # 特殊处理PNG质量参数错误，减少日志噪音
                if "quality is unsupported for the png screenshots" in str(e):
                    douyin_logger.debug(f"PNG截图质量参数警告: {str(e)}")
                else:
                    douyin_logger.error(f"截图失败: {str(e)}")
                await asyncio.sleep(interval)
                
    except asyncio.CancelledError:
        douyin_logger.info(f"截图任务已取消: {session_id}")
    finally:
        # 清理截图数据
        with browser_data_lock:
            if session_id in browser_screenshot_data:
                del browser_screenshot_data[session_id]

async def handle_click_events(page, session_id, interval=0.1):
    """处理前端发送的点击和输入事件"""
    try:
        while True:
            # 线程安全检查会话状态和事件队列
            event = None
            with browser_data_lock:
                if not active_browser_sessions.get(session_id, False):
                    break
                # 检查是否有待处理的事件
                if session_id in browser_click_queue and browser_click_queue[session_id]:
                    event = browser_click_queue[session_id].pop(0)
            
            if event:
                try:
                    if event['type'] == 'click':
                        # 处理点击事件
                        x = event['x']
                        y = event['y']
                        
                        await page.mouse.click(x, y)
                        douyin_logger.info(f"执行点击操作: ({x}, {y}) for session {session_id}")
                        
                        socketio.emit('click_executed', {
                            'session_id': session_id,
                            'x': x,
                            'y': y,
                            'message': f'已点击位置: ({x}, {y})'
                        })
                        
                    elif event['type'] == 'input':
                        # 处理输入事件
                        action = event['action']
                        text = event['text']
                        key = event['key']
                        
                        if action == 'type' and text:
                            # 输入文本
                            await page.keyboard.type(text)
                            douyin_logger.info(f"输入文本: '{text}' for session {session_id}")
                            
                            socketio.emit('input_executed', {
                                'session_id': session_id,
                                'action': action,
                                'text': text,
                                'message': f'已输入: {text}'
                            })
                            
                        elif action == 'press' and key:
                            # 按键操作
                            await page.keyboard.press(key)
                            douyin_logger.info(f"按键操作: '{key}' for session {session_id}")
                            
                            socketio.emit('input_executed', {
                                'session_id': session_id,
                                'action': action,
                                'key': key,
                                'message': f'已按键: {key}'
                            })
                            
                        elif action == 'clear':
                            # 清空输入框 (Ctrl+A + Delete)
                            await page.keyboard.press('Control+a')
                            await page.keyboard.press('Delete')
                            douyin_logger.info(f"清空输入框 for session {session_id}")
                            
                            socketio.emit('input_executed', {
                                'session_id': session_id,
                                'action': action,
                                'message': '已清空输入框'
                            })
                except Exception as e:
                    douyin_logger.error(f"执行操作失败: {str(e)}")
            
            await asyncio.sleep(interval)
                
    except asyncio.CancelledError:
        douyin_logger.info(f"事件处理任务已取消: {session_id}")

@app.route('/api/cookies/<cookie_name>/validate', methods=['POST'])
def validate_cookie(cookie_name):
    """验证指定Cookie的有效性"""
    try:
        account_file = os.path.join("cookie", cookie_name)
        
        # 基本文件检查
        if not os.path.exists(account_file):
            return jsonify({
                "success": False, 
                "valid": False,
                "message": "Cookie文件不存在"
            })
        
        file_size = os.path.getsize(account_file)
        if file_size < 100:
            return jsonify({
                "success": False, 
                "valid": False,
                "message": f"Cookie文件过小: {file_size}字节"
            })
        
        # 异步验证cookie
        def check_cookie():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                from main import cookie_auth
                result = loop.run_until_complete(cookie_auth(account_file))
                return result, None
            except Exception as e:
                return False, str(e)
            finally:
                loop.close()
        
        is_valid, error = check_cookie()
        
        response_data = {
            "success": True,
            "valid": is_valid,
            "file_size": file_size,
            "file_path": account_file
        }
        
        if error:
            response_data["error"] = error
            
        if is_valid:
            response_data["message"] = "Cookie有效"
        else:
            response_data["message"] = "Cookie已失效"
            
        return jsonify(response_data)
        
    except Exception as e:
        return jsonify({
            "success": False, 
            "valid": False,
            "message": f"验证过程出错: {str(e)}"
        }), 500

@app.route('/api/multi_tasks', methods=['GET'])
def get_multi_tasks():
    """获取多账号任务列表"""
    # 添加调试日志
    for task in multi_account_tasks:
        douyin_logger.debug(f"任务状态 - ID: {task['id']}, Cookie: {task['cookie']}, Status: {task['status']}, Completed: {task['completed_videos']}/{task['total_videos']}")
    
    return jsonify({
        "success": True,
        "tasks": multi_account_tasks,
        "is_uploading": is_multi_uploading,
        "upload_mode": upload_mode,
        "current_task_index": current_task_index
    })

@app.route('/api/multi_tasks', methods=['POST'])
def add_multi_task():
    """添加账号任务"""
    try:
        data = request.json
        
        task = {
            "id": len(multi_account_tasks) + 1,
            "cookie": data.get('cookie'),
            "videos": data.get('videos', []),
            "location": data.get('location', '杭州市'),
            "upload_interval": int(data.get('upload_interval', 5)),
            "risk_limit": int(data.get('risk_limit', 5)),  # 添加风控阈值
            "publish_type": data.get('publish_type', 'now'),
            "publish_date": data.get('publish_date'),
            "publish_hour": data.get('publish_hour'),
            "publish_minute": data.get('publish_minute'),
            "status": "waiting",  # waiting, uploading, completed, failed
            "completed_videos": 0,
            "total_videos": len(data.get('videos', [])),
            "current_video": None,
            "created_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        
        multi_account_tasks.append(task)
        save_multi_tasks_to_file()  # 保存到文件
        
        return jsonify({
            "success": True,
            "message": "任务添加成功",
            "task_id": task["id"]
        })
        
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

@app.route('/api/multi_tasks/<int:task_id>', methods=['DELETE'])
def delete_multi_task(task_id):
    """删除账号任务"""
    global multi_account_tasks
    
    # 如果正在上传，不允许删除
    if is_multi_uploading:
        return jsonify({"success": False, "message": "上传进行中，无法删除任务"}), 400
    
    # 查找并删除任务
    task_index = None
    for i, task in enumerate(multi_account_tasks):
        if task["id"] == task_id:
            task_index = i
            break
    
    if task_index is not None:
        removed_task = multi_account_tasks.pop(task_index)
        save_multi_tasks_to_file()  # 保存到文件
        return jsonify({
            "success": True,
            "message": f"已删除账号 {removed_task['cookie']} 的任务"
        })
    else:
        return jsonify({"success": False, "message": "任务不存在"}), 404

@app.route('/api/multi_tasks/clear', methods=['POST'])
def clear_multi_tasks():
    """清空所有任务"""
    global multi_account_tasks
    
    if is_multi_uploading:
        return jsonify({"success": False, "message": "上传进行中，无法清空任务"}), 400
    
    multi_account_tasks.clear()
    save_multi_tasks_to_file()  # 保存到文件
    return jsonify({"success": True, "message": "已清空所有任务"})

@app.route('/api/multi_upload', methods=['POST'])
def start_multi_upload():
    """开始多账号上传"""
    global is_multi_uploading, upload_mode, current_task_index
    
    if is_multi_uploading:
        return jsonify({"success": False, "message": "多账号上传已在进行中"}), 400
    
    if not multi_account_tasks:
        return jsonify({"success": False, "message": "没有配置任何上传任务"}), 400
    
    data = request.json
    upload_mode = data.get('mode', 'sequential')  # sequential 或 concurrent
    
    # 处理任务状态（支持续传）
    for task in multi_account_tasks:
        # 如果任务是stopped状态，保留已完成的视频数量，实现续传
        if task["status"] == "stopped":
            douyin_logger.info(f"检测到已停止的任务: {task['cookie']}，已完成 {task['completed_videos']}/{len(task['videos'])} 个视频，将从断点继续")
            update_task_status(task, "waiting", f"准备从第 {task['completed_videos']+1} 个视频继续上传", save_to_file=False)
        else:
            # 其他状态重置计数
            task["completed_videos"] = 0
            update_task_status(task, "waiting", None, save_to_file=False)
    save_multi_tasks_to_file()  # 批量保存
    
    current_task_index = 0
    is_multi_uploading = True
    
    # 启动上传线程
    if upload_mode == "concurrent":
        # 并发模式：为每个账号启动独立线程
        for task in multi_account_tasks:
            thread = threading.Thread(
                target=multi_account_upload_thread,
                args=(task,)
            )
            thread.start()
    else:
        # 轮询模式：启动单个协调线程
        thread = threading.Thread(target=sequential_upload_coordinator)
        thread.start()
    
    return jsonify({
        "success": True,
        "message": f"多账号上传已开始（{upload_mode}模式）",
        "mode": upload_mode
    })

@app.route('/api/multi_upload/stop', methods=['POST'])
def stop_multi_upload():
    """停止多账号上传"""
    global is_multi_uploading
    
    is_multi_uploading = False
    
    # 更新所有任务状态为已停止（不仅仅是正在上传的）
    for task in multi_account_tasks:
        if task["status"] in ["uploading", "waiting"]:
            update_task_status(task, "stopped", "已手动停止", save_to_file=False)
            douyin_logger.info(f"手动停止任务: {task['cookie']}, 状态从 {task['status']} 更改为 stopped")
    save_multi_tasks_to_file()  # 批量保存
    
    return jsonify({"success": True, "message": "多账号上传已停止"})

def multi_account_upload_thread(task):
    """单个账号的上传线程"""
    global is_multi_uploading
    
    try:
        # 检查任务是否已被停止
        if task["status"] == "stopped":
            douyin_logger.info(f"任务 {task['cookie']} 已被停止，跳过上传")
            return
            
        update_task_status(task, "uploading")
        account_file = os.path.join("cookie", task["cookie"])
        
        # 验证cookie有效性
        def check_task_cookie_validity():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                from main import cookie_auth
                result = loop.run_until_complete(cookie_auth(account_file))
                return result
            except Exception as e:
                douyin_logger.error(f"验证cookie失败: {str(e)}")
                return False
            finally:
                loop.close()
        
        if not check_task_cookie_validity():
            update_task_status(task, "failed", "Cookie已失效")
            douyin_logger.warning(f"任务 {task['cookie']} cookie失效，跳过上传")
            return
            
        # 风控检测
        risk_limit = task.get('risk_limit', 5)
        count = get_upload_count_last_hour(task['cookie'])
        if count >= risk_limit:
            update_task_status(task, "waiting", f"风控限制：每小时最多{risk_limit}个，已上传{count}个")
            douyin_logger.warning(f"账号 {task['cookie']} 上传过于频繁，已自动延迟（每小时最多{risk_limit}个，已上传{count}个）")
            # 等待一小时后再继续
            time.sleep(60 * 60)  # 等待1小时
        
        # 处理发布时间
        publish_date = 0
        if task["publish_type"] == 'schedule':
            try:
                publish_time = f"{task['publish_date']} {task['publish_hour']}:{task['publish_minute']}"
                publish_date = datetime.strptime(publish_time, "%Y-%m-%d %H:%M")
            except Exception:
                task["status"] = "failed"
                task["current_video"] = "定时发布时间格式错误"
                return
        
                        # 逐个上传视频
                # 如果是从停止状态恢复的任务，从已完成的视频数量开始继续上传
                start_index = task["completed_videos"] if task["completed_videos"] > 0 else 0
                
                for i, video_path in enumerate(task["videos"][start_index:], start=start_index):
                    if not is_multi_uploading:  # 检查是否被停止
                        update_task_status(task, "stopped", "已手动停止")
                        douyin_logger.info(f"任务 {task['cookie']} 检测到停止信号，中断上传")
                        break
                        
                    douyin_logger.info(f"任务 {task['cookie']} 上传第 {i+1}/{len(task['videos'])} 个视频")
                
            task["current_video"] = os.path.basename(video_path)
            
            try:
                # 上传单个视频
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                
                # 获取视频标题和标签
                title, tags = get_title_tags_from_txt(os.path.join("videos", video_path))
                
                def update_status_callback(status_message):
                    task["current_video"] = f"{os.path.basename(video_path)} - {status_message}"
                
                success = loop.run_until_complete(async_upload(
                    video_path, account_file, title, tags, 
                    task["location"], publish_date, update_status_callback
                ))
                
                if success:
                    task["completed_videos"] += 1
                    douyin_logger.info(f"账号 {task['cookie']} 成功上传视频: {video_path}")
                    douyin_logger.info(f"DEBUG: 任务 {task['cookie']} 完成视频计数更新为: {task['completed_videos']}/{len(task['videos'])}")
                    
                    # 记录上传历史
                    log_upload_history(
                        cookie_name=task["cookie"],
                        filename=os.path.basename(video_path),
                        status="success",
                        reason="上传成功"
                    )
                    
                    # 立即检查是否所有视频都已完成
                    if task["completed_videos"] >= len(task["videos"]):
                        douyin_logger.info(f"DEBUG: 任务 {task['cookie']} 达到完成条件，准备设置为completed状态")
                        update_task_status(task, "completed", clear_video=True)
                        douyin_logger.info(f"任务 {task['cookie']} 已完成所有视频上传: {task['completed_videos']}/{len(task['videos'])}")
                        douyin_logger.info(f"DEBUG: 任务 {task['cookie']} 状态已更新为: {task['status']}")
                        # 已完成所有视频，后面的代码会处理后续逻辑
                    else:
                        # 如果还有视频要上传，保存当前进度
                        update_task_status(task, "uploading", f"已完成 {task['completed_videos']}/{len(task['videos'])}")
                        douyin_logger.info(f"DEBUG: 任务 {task['cookie']} 部分完成，状态保存为uploading")
                else:
                    douyin_logger.error(f"账号 {task['cookie']} 上传视频失败: {video_path}")
                    log_upload_history(
                        cookie_name=task["cookie"],
                        filename=os.path.basename(video_path),
                        status="failed",
                        reason="上传失败"
                    )
                
                loop.close()
                
                # 账号内视频上传间隔（并发模式）
                # 只有在视频成功上传(而非跳过)的情况下才等待间隔时间
                if i < len(task["videos"]) - 1 and is_multi_uploading and success is not False:
                    douyin_logger.info(f"账号 {task['cookie']} 视频间隔等待 {task['upload_interval']} 分钟")
                    # 更新状态为等待中
                    update_task_status(task, "waiting", f"等待 {task['upload_interval']} 分钟后上传下一个视频")
                    time.sleep(task["upload_interval"] * 60)
                elif i < len(task["videos"]) - 1 and is_multi_uploading:
                    douyin_logger.info(f"账号 {task['cookie']} 视频已跳过，立即处理下一个视频")
                    update_task_status(task, "waiting", f"视频已跳过，立即处理下一个视频")
                    
            except Exception as e:
                douyin_logger.error(f"上传视频 {video_path} 时发生错误: {str(e)}")
                log_upload_history(
                    cookie_name=task["cookie"],
                    filename=os.path.basename(video_path),
                    status="failed",
                    reason=str(e)
                )
        
        # 完成状态（如果还没有设置为completed）
        if task["status"] != "completed":
            if task["completed_videos"] >= len(task["videos"]):
                update_task_status(task, "completed", clear_video=True)
            elif task["status"] != "stopped":
                # 如果有部分完成，显示进度
                if task["completed_videos"] > 0:
                    update_task_status(task, "waiting", f"已完成 {task['completed_videos']}/{len(task['videos'])}")
                else:
                    update_task_status(task, "failed", "上传失败")
        
        # 检查是否所有任务都完成了（并发模式下）
        if upload_mode == "concurrent":
            all_completed = all(t["status"] in ["completed", "failed", "stopped"] for t in multi_account_tasks if t["videos"])
            if all_completed:
                is_multi_uploading = False
                douyin_logger.info("所有并发任务已完成，停止多账号上传")
        
    except Exception as e:
        update_task_status(task, "failed", f"错误: {str(e)}")
        douyin_logger.error(f"账号 {task['cookie']} 上传任务失败: {str(e)}")

def sequential_upload_coordinator():
    """轮询上传协调器 - 账号之间轮询上传"""
    global is_multi_uploading, current_task_index
    
    try:
        # 过滤出有视频的任务
        valid_tasks = [task for task in multi_account_tasks if task["videos"]]
        
        if not valid_tasks:
            is_multi_uploading = False
            return
        
        # 轮询逻辑：A账号上传1个视频 -> 等待间隔 -> B账号上传1个视频 -> 等待间隔 -> C账号上传1个视频...
        # 直到所有账号的所有视频都上传完成
        
        # 为每个任务维护当前上传索引
        for task in valid_tasks:
            # 如果是从停止状态恢复的任务，从已完成的视频数量开始继续上传
            if task["status"] == "waiting" and task["completed_videos"] > 0:
                task["current_upload_index"] = task["completed_videos"]
                douyin_logger.info(f"任务 {task['cookie']} 从断点继续上传: 已完成 {task['completed_videos']}/{len(task['videos'])} 个视频")
            else:
                task["current_upload_index"] = 0
            
            # 确保任务状态正确
            if task["status"] not in ["uploading", "waiting"]:
                update_task_status(task, "waiting", None, save_to_file=False)
        
        # 持续轮询直到所有任务完成
        while is_multi_uploading and any(task["current_upload_index"] < len(task["videos"]) for task in valid_tasks):
            
            for task in valid_tasks:
                if not is_multi_uploading:
                    douyin_logger.info(f"检测到停止信号，中断轮询上传")
                    break
                
                # 如果任务已被手动停止，跳过该任务
                if task["status"] == "stopped":
                    douyin_logger.info(f"跳过已停止的任务: {task['cookie']}")
                    continue
                    
                # 如果该账号还有视频要上传
                if task["current_upload_index"] < len(task["videos"]):
                    current_task_index = task["id"]
                    
                    # 执行单个视频上传
                    video_index = task["current_upload_index"]
                    success = upload_single_video_for_task(task, video_index)
                    
                    # 更新上传索引
                    task["current_upload_index"] += 1
                    
                    # 账号间隔等待（轮询模式的核心）
                    # 只有在上传成功（而非跳过视频）且还有其他账号需要上传时才等待
                    if is_multi_uploading and any(t["current_upload_index"] < len(t["videos"]) for t in valid_tasks) and success is not False:
                        douyin_logger.info(f"账号 {task['cookie']} 上传完成，等待 {task['upload_interval']} 分钟后轮询下一个账号")
                        time.sleep(task["upload_interval"] * 60)
                    elif is_multi_uploading and any(t["current_upload_index"] < len(t["videos"]) for t in valid_tasks):
                        douyin_logger.info(f"账号 {task['cookie']} 视频已跳过，立即轮询下一个账号")
        
        # 清理临时索引
        for task in valid_tasks:
            if "current_upload_index" in task:
                del task["current_upload_index"]
        
        # 检查所有任务完成状态
        for task in valid_tasks:
            if task["completed_videos"] >= len(task["videos"]):
                update_task_status(task, "completed", clear_video=True, save_to_file=False)
            elif task["status"] not in ["stopped", "completed"]:
                # 如果有部分完成，显示进度
                if task["completed_videos"] > 0:
                    update_task_status(task, "waiting", f"已完成 {task['completed_videos']}/{len(task['videos'])}", save_to_file=False)
                else:
                    update_task_status(task, "failed", "上传失败", save_to_file=False)
        
        # 批量保存状态
        save_multi_tasks_to_file()
        is_multi_uploading = False
        
    except Exception as e:
        douyin_logger.error(f"轮询上传协调器错误: {str(e)}")
        is_multi_uploading = False

def upload_single_video_for_task(task, video_index):
    """为指定任务上传单个视频"""
    try:
        task["status"] = "uploading"
        video_path = task["videos"][video_index]
        task["current_video"] = os.path.basename(video_path)
        
        account_file = os.path.join("cookie", task["cookie"])
        
        # 验证cookie有效性
        def check_task_cookie_validity():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                from main import cookie_auth
                result = loop.run_until_complete(cookie_auth(account_file))
                return result
            except Exception as e:
                return False
            finally:
                loop.close()
        
        if not check_task_cookie_validity():
            task["status"] = "failed"
            task["current_video"] = "Cookie已失效"
            return False
        
        # 处理发布时间
        publish_date = 0
        if task["publish_type"] == 'schedule':
            try:
                publish_time = f"{task['publish_date']} {task['publish_hour']}:{task['publish_minute']}"
                publish_date = datetime.strptime(publish_time, "%Y-%m-%d %H:%M")
            except Exception:
                task["status"] = "failed"
                task["current_video"] = "定时发布时间格式错误"
                return False
        
        # 上传视频
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        title, tags = get_title_tags_from_txt(os.path.join("videos", video_path))
        
        def update_status_callback(status_message):
            task["current_video"] = f"{os.path.basename(video_path)} - {status_message}"
        
        success = loop.run_until_complete(async_upload(
            video_path, account_file, title, tags, 
            task["location"], publish_date, update_status_callback
        ))
        
        if success:
            task["completed_videos"] += 1
            log_upload_history(
                cookie_name=task["cookie"],
                filename=os.path.basename(video_path),
                status="success",
                reason="上传成功"
            )
            
            # 检查是否所有视频都已完成
            if task["completed_videos"] >= len(task["videos"]):
                update_task_status(task, "completed", clear_video=True)
                douyin_logger.info(f"任务 {task['cookie']} 已完成所有视频上传: {task['completed_videos']}/{len(task['videos'])}")
            else:
                update_task_status(task, "waiting", f"已完成 {task['completed_videos']}/{len(task['videos'])}")
                douyin_logger.info(f"任务 {task['cookie']} 部分完成: {task['completed_videos']}/{len(task['videos'])}")
        else:
            # 检查是否是因为视频重复导致的
            from utils.md5_manager import md5_manager
            full_path = os.path.join("videos", video_path)
            if os.path.exists(full_path) and md5_manager.is_duplicate(full_path):
                # 更新任务状态为跳过（视频重复）
                log_upload_history(
                    cookie_name=task["cookie"],
                    filename=os.path.basename(video_path),
                    status="skipped",
                    reason="视频重复"
                )
                # 虽然跳过了，但也算处理完成，所以增加计数
                task["completed_videos"] += 1
                update_task_status(task, task["status"], f"视频重复，已跳过: {os.path.basename(video_path)}")
                douyin_logger.warning(f"视频 {os.path.basename(video_path)} 重复，已跳过")
                # 返回特殊值False表示视频被跳过，以便上层函数可以区分是否需要等待间隔
                return False
            else:
                # 真正的上传失败
                log_upload_history(
                    cookie_name=task["cookie"],
                    filename=os.path.basename(video_path),
                    status="failed",
                    reason="上传失败"
                )
                # 上传失败但不设置整个任务为失败，继续下一个视频
                update_task_status(task, task["status"], f"上传失败: {os.path.basename(video_path)}")
        
        loop.close()
        return success
        
    except Exception as e:
        task["status"] = "failed"
        task["current_video"] = f"错误: {str(e)}"
        log_upload_history(
            cookie_name=task["cookie"],
            filename=os.path.basename(video_path),
            status="failed",
            reason=str(e)
        )
        return False
  

# 视频权限设置相关API
@app.route('/api/videos/set_permissions', methods=['POST'])
def set_video_permissions():
    """批量设置视频权限"""
    try:
        data = request.get_json()
        account_file = data.get('account_file')
        permission_value = data.get('permission_value')  # "0"=公开, "1"=仅自己可见, "2"=好友可见
        max_count = data.get('max_count')  # 最大设置数量，None表示设置所有
        video_titles = data.get('video_titles', [])  # 指定要设置的视频标题列表
        
        if not account_file:
            return jsonify({
                "success": False,
                "message": "请选择账号文件"
            }), 400
        
        if not permission_value:
            return jsonify({
                "success": False,
                "message": "请选择权限类型"
            }), 400
        
        if permission_value not in ["0", "1", "2"]:
            return jsonify({
                "success": False,
                "message": "无效的权限值"
            }), 400
        
        cookie_path = os.path.join("cookie", account_file)
        if not os.path.exists(cookie_path):
            return jsonify({
                "success": False,
                "message": "Cookie文件不存在"
            }), 400
        
        # 启动权限设置任务
        def permission_thread():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                from utils.douyin_video_deleter import set_douyin_video_permissions
                
                # 状态回调函数，通过WebSocket发送状态
                async def status_callback(status_message):
                    socketio.emit('permission_status_update', {
                        'status': status_message,
                        'account': account_file
                    })
                
                result = loop.run_until_complete(
                    set_douyin_video_permissions(
                        cookie_path, 
                        permission_value, 
                        max_count, 
                        video_titles if video_titles else None, 
                        status_callback
                    )
                )
                
                # 发送完成状态
                socketio.emit('permission_completed', {
                    'result': result,
                    'account': account_file
                })
                
            except Exception as e:
                douyin_logger.error(f"设置视频权限过程中出错: {str(e)}")
                socketio.emit('permission_error', {
                    'error': str(e),
                    'account': account_file
                })
            finally:
                loop.close()
        
        # 在后台线程中运行权限设置任务
        thread = threading.Thread(target=permission_thread)
        thread.daemon = True
        thread.start()
        
        permission_names = {"0": "公开", "1": "仅自己可见", "2": "好友可见"}
        permission_name = permission_names.get(permission_value, "未知")
        
        return jsonify({
            "success": True,
            "message": f"权限设置任务已启动，正在将视频设置为 {permission_name}"
        })
        
    except Exception as e:
        douyin_logger.error(f"启动权限设置任务失败: {str(e)}")
        return jsonify({
            "success": False,
            "message": f"启动权限设置任务失败: {str(e)}"
        }), 500


@app.route('/api/videos/list_remote', methods=['POST'])
def list_remote_videos():
    """获取远程抖音创作者中心的视频列表（删除管理用）"""
    try:
        data = request.get_json()
        account_file = data.get('account_file')
        
        if not account_file:
            return jsonify({
                "success": False,
                "message": "请选择账号文件"
            }), 400
        
        cookie_path = os.path.join("cookie", account_file)
        if not os.path.exists(cookie_path):
            return jsonify({
                "success": False,
                "message": "Cookie文件不存在"
            }), 400
        
        # 启动获取视频列表任务
        def get_videos_thread():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                from utils.douyin_video_deleter import DouyinVideoDeleter
                
                # 创建删除器实例用于获取视频列表
                deleter = DouyinVideoDeleter(cookie_path)
                # 设置操作类型为删除管理
                deleter.operation_type = "删除管理"
                
                # 临时修改删除器来获取视频信息而不删除
                async def get_video_info_only():
                    """只获取视频信息不删除"""
                    from utils.fingerprint_manager import fingerprint_manager
                    from utils.proxy_manager import proxy_manager
                    from main import get_browser_launch_options
                    from utils.base_social_media import set_init_script
                    from playwright.async_api import async_playwright
                    
                    proxy_config = proxy_manager.get_proxy_for_playwright(deleter.cookie_filename)
                    
                    # Docker环境检测
                    is_in_docker = os.path.exists('/.dockerenv') or os.environ.get('DOCKER_ENV') == 'true'
                    headless_mode = True if is_in_docker else False
                    
                    launch_options = get_browser_launch_options(headless=headless_mode, proxy_config=proxy_config)
                    fingerprint_config = fingerprint_manager.get_playwright_config(deleter.cookie_filename)
                    
                    browser = None
                    context = None
                    
                    try:
                        async with async_playwright() as playwright:
                            browser = await playwright.chromium.launch(**launch_options)
                            
                            context_options = {
                                "storage_state": deleter.account_file,
                                **fingerprint_config
                            }
                            
                            if proxy_config:
                                context_options["proxy"] = proxy_config
                            
                            context = await browser.new_context(**context_options)
                            context = await set_init_script(context, deleter.cookie_filename)
                            
                            page = await context.new_page()
                            
                            # 访问视频管理页面
                            await page.goto("https://creator.douyin.com/creator-micro/content/manage")
                            await page.wait_for_timeout(5000)
                            
                            # 检查登录状态
                            if await page.locator('text=手机号登录').count() > 0:
                                return {
                                    "success": False,
                                    "message": "Cookie已失效，需要重新登录",
                                    "videos": []
                                }
                            
                            # 设置进度回调函数
                            async def progress_callback(status_message):
                                socketio.emit('video_list_progress', {
                                    'status': status_message,
                                    'account': account_file
                                })
                            
                            deleter.status_callback = progress_callback
                            
                            # 获取视频详细信息，包括权限状态
                            video_details = await deleter.get_video_details(page)
                            videos = []
                            
                            for i, video_detail in enumerate(video_details):
                                try:
                                    title = video_detail.get('title', f"视频 {i + 1}")
                                    publish_time = video_detail.get('publish_time', "未知时间")
                                    video_status = video_detail.get('status', "未知状态")
                                    metrics = video_detail.get('metrics', {})
                                    
                                    # 确定状态颜色
                                    if video_status == "仅自己可见":
                                        status_color = "private"
                                    elif video_status == "公开":
                                        status_color = "published"
                                    elif video_status == "好友可见":
                                        status_color = "friends"
                                    elif video_status == "已发布":
                                        status_color = "published"
                                    else:
                                        status_color = "unknown"
                                    
                                    videos.append({
                                        "index": video_detail.get('index', i),
                                        "title": title.strip(),
                                        "publish_time": publish_time.strip(),
                                        "status": video_status,
                                        "status_color": status_color,
                                        "metrics": metrics,
                                        "can_delete": True,  # 暂时设为True，实际应从card_element检查
                                        "is_disabled": False,  # 暂时设为False，实际应从card_element检查
                                        "is_private": video_status == "仅自己可见",
                                        "play_count": metrics.get("播放", "0")  # 保持向后兼容
                                    })
                                    
                                except Exception as e:
                                    videos.append({
                                        "index": i,
                                        "title": f"视频 {i + 1}",
                                        "publish_time": "获取失败",
                                        "status": "获取失败",
                                        "status_color": "error",
                                        "metrics": {},
                                        "can_delete": False,
                                        "is_disabled": False,
                                        "is_private": False,
                                        "play_count": "0",
                                        "error": str(e)
                                    })
                            
                            return {
                                "success": True,
                                "message": f"成功获取 {len(videos)} 个视频信息",
                                "videos": videos
                            }
                    
                    finally:
                        if context:
                            try:
                                await context.close()
                            except:
                                pass
                        if browser:
                            try:
                                await browser.close()
                            except:
                                pass
                
                result = loop.run_until_complete(get_video_info_only())
                
                # 发送结果
                socketio.emit('video_list_result', {
                    'result': result,
                    'account': account_file
                })
                
            except Exception as e:
                douyin_logger.error(f"获取视频列表过程中出错: {str(e)}")
                socketio.emit('video_list_error', {
                    'error': str(e),
                    'account': account_file
                })
            finally:
                loop.close()
        
        # 在后台线程中运行任务
        thread = threading.Thread(target=get_videos_thread)
        thread.daemon = True
        thread.start()
        
        return jsonify({
            "success": True,
            "message": "正在获取视频列表，请稍候..."
        })
        
    except Exception as e:
        douyin_logger.error(f"启动获取视频列表任务失败: {str(e)}")
        return jsonify({
            "success": False,
            "message": f"启动获取视频列表任务失败: {str(e)}"
        }), 500


@app.route('/api/videos/list_remote_permissions', methods=['POST'])
def list_remote_videos_for_permissions():
    """获取远程抖音创作者中心的视频列表（权限设置用）"""
    try:
        data = request.get_json()
        account_file = data.get('account_file')
        
        if not account_file:
            return jsonify({
                "success": False,
                "message": "请选择账号文件"
            }), 400
        
        cookie_path = os.path.join("cookie", account_file)
        if not os.path.exists(cookie_path):
            return jsonify({
                "success": False,
                "message": "Cookie文件不存在"
            }), 400
        
        # 启动获取视频列表任务
        def get_videos_thread():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                from utils.douyin_video_deleter import DouyinVideoDeleter
                
                # 创建删除器实例用于获取视频列表
                deleter = DouyinVideoDeleter(cookie_path)
                # 设置操作类型为权限设置
                deleter.operation_type = "权限设置"
                
                # 临时修改删除器来获取视频信息而不删除
                async def get_video_info_only():
                    """只获取视频信息不删除"""
                    from utils.fingerprint_manager import fingerprint_manager
                    from utils.proxy_manager import proxy_manager
                    from main import get_browser_launch_options
                    from utils.base_social_media import set_init_script
                    from playwright.async_api import async_playwright
                    
                    # 设置进度回调函数
                    async def progress_callback(status_message):
                        socketio.emit('permission_video_list_progress', {
                            'status': status_message,
                            'account': account_file
                        })
                    
                    deleter.status_callback = progress_callback
                    
                    proxy_config = proxy_manager.get_proxy_for_playwright(deleter.cookie_filename)
                    
                    # Docker环境检测
                    is_in_docker = os.path.exists('/.dockerenv') or os.environ.get('DOCKER_ENV') == 'true'
                    headless_mode = True if is_in_docker else False
                    
                    launch_options = get_browser_launch_options(headless=headless_mode, proxy_config=proxy_config)
                    fingerprint_config = fingerprint_manager.get_playwright_config(deleter.cookie_filename)
                    
                    browser = None
                    context = None
                    
                    try:
                        async with async_playwright() as playwright:
                            browser = await playwright.chromium.launch(**launch_options)
                            
                            context_options = {
                                "storage_state": deleter.account_file,
                                **fingerprint_config
                            }
                            
                            if proxy_config:
                                context_options["proxy"] = proxy_config
                            
                            context = await browser.new_context(**context_options)
                            context = await set_init_script(context, deleter.cookie_filename)
                            
                            page = await context.new_page()
                            
                            # 访问视频管理页面
                            await page.goto("https://creator.douyin.com/creator-micro/content/manage")
                            await page.wait_for_timeout(5000)
                            
                            # 检查登录状态
                            if await page.locator('text=手机号登录').count() > 0:
                                return {
                                    "success": False,
                                    "message": "Cookie已失效，需要重新登录",
                                    "videos": []
                                }
                            
                            # 获取视频详细信息，包括权限状态
                            video_details = await deleter.get_video_details(page)
                            videos = []
                            
                            for i, video_detail in enumerate(video_details):
                                try:
                                    title = video_detail.get('title', f"视频 {i + 1}")
                                    publish_time = video_detail.get('publish_time', "未知时间")
                                    video_status = video_detail.get('status', "未知状态")
                                    metrics = video_detail.get('metrics', {})
                                    
                                    # 确定状态颜色
                                    if video_status == "仅自己可见":
                                        status_color = "private"
                                    elif video_status == "公开":
                                        status_color = "published"
                                    elif video_status == "好友可见":
                                        status_color = "friends"
                                    elif video_status == "已发布":
                                        status_color = "published"
                                    else:
                                        status_color = "unknown"
                                    
                                    videos.append({
                                        "index": video_detail.get('index', i),
                                        "title": title.strip(),
                                        "publish_time": publish_time.strip(),
                                        "status": video_status,
                                        "status_color": status_color,
                                        "metrics": metrics,
                                        "can_delete": True,  # 暂时设为True，实际应从card_element检查
                                        "is_disabled": False,  # 暂时设为False，实际应从card_element检查
                                        "is_private": video_status == "仅自己可见",
                                        "play_count": metrics.get("播放", "0")  # 保持向后兼容
                                    })
                                    
                                except Exception as e:
                                    videos.append({
                                        "index": i,
                                        "title": f"视频 {i + 1}",
                                        "publish_time": "获取失败",
                                        "status": "获取失败",
                                        "status_color": "error",
                                        "metrics": {},
                                        "can_delete": False,
                                        "is_disabled": False,
                                        "is_private": False,
                                        "play_count": "0",
                                        "error": str(e)
                                    })
                            
                            return {
                                "success": True,
                                "message": f"成功获取 {len(videos)} 个视频信息",
                                "videos": videos
                            }
                    
                    finally:
                        if context:
                            try:
                                await context.close()
                            except:
                                pass
                        if browser:
                            try:
                                await browser.close()
                            except:
                                pass
                
                result = loop.run_until_complete(get_video_info_only())
                
                # 发送结果 - 使用不同的事件名
                socketio.emit('permission_video_list_result', {
                    'result': result,
                    'account': account_file
                })
                
            except Exception as e:
                douyin_logger.error(f"获取权限设置视频列表过程中出错: {str(e)}")
                socketio.emit('permission_video_list_error', {
                    'error': str(e),
                    'account': account_file
                })
            finally:
                loop.close()
        
        # 在后台线程中运行任务
        thread = threading.Thread(target=get_videos_thread)
        thread.daemon = True
        thread.start()
        
        return jsonify({
            "success": True,
            "message": "正在获取视频列表，请稍候..."
        })
        
    except Exception as e:
        douyin_logger.error(f"启动获取权限设置视频列表任务失败: {str(e)}")
        return jsonify({
            "success": False,
            "message": f"启动获取权限设置视频列表任务失败: {str(e)}"
        }), 500

@app.route('/api/videos/delete', methods=['POST'])
def delete_videos():
    """删除抖音视频"""
    try:
        data = request.get_json()
        account_file = data.get('account_file')
        delete_type = data.get('delete_type')  # 'selected' 或 'all'
        video_titles = data.get('video_titles', [])  # 要删除的视频标题列表
        max_count = data.get('max_count')  # 最大删除数量
        
        douyin_logger.info(f"删除视频请求参数: account_file={account_file}, delete_type={delete_type}, video_titles={video_titles}, max_count={max_count}")
        
        if not account_file:
            return jsonify({
                "success": False,
                "message": "请选择账号文件"
            }), 400
        
        cookie_path = os.path.join("cookie", account_file)
        if not os.path.exists(cookie_path):
            return jsonify({
                "success": False,
                "message": "Cookie文件不存在"
            }), 400
        
        # 启动删除任务
        def delete_thread():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                from utils.douyin_video_deleter import delete_douyin_videos, delete_specific_douyin_videos
                
                # 状态回调函数
                async def status_callback(status_message):
                    socketio.emit('delete_status_update', {
                        'status': status_message,
                        'account': account_file
                    })
                
                if delete_type == 'selected' and video_titles:
                    # 删除指定视频
                    result = loop.run_until_complete(
                        delete_specific_douyin_videos(cookie_path, video_titles, status_callback)
                    )
                elif delete_type == 'all':
                    # 删除所有视频
                    result = loop.run_until_complete(
                        delete_douyin_videos(cookie_path, max_count, status_callback)
                    )
                else:
                    result = {
                        "success": False,
                        "message": "请指定删除类型和目标视频"
                    }
                
                # 发送删除完成事件
                socketio.emit('delete_completed', {
                    'result': result,
                    'account': account_file
                })
                
            except Exception as e:
                douyin_logger.error(f"删除视频过程中出错: {str(e)}")
                socketio.emit('delete_error', {
                    'error': str(e),
                    'account': account_file
                })
            finally:
                loop.close()
        
        # 在后台线程中运行删除任务
        thread = threading.Thread(target=delete_thread)
        thread.daemon = True
        thread.start()
        
        return jsonify({
            "success": True,
            "message": "删除任务已启动，正在处理..."
        })
        
    except Exception as e:
        douyin_logger.error(f"启动删除任务失败: {str(e)}")
        return jsonify({
            "success": False,
            "message": f"启动删除任务失败: {str(e)}"
        }), 500

@app.route('/api/upload_archive', methods=['POST'])
def upload_archive():
    """处理压缩包上传"""
    try:
        if 'archive' not in request.files:
            return jsonify({"success": False, "message": "没有选择文件"}), 400
        
        file = request.files['archive']
        if file.filename == '':
            return jsonify({"success": False, "message": "没有选择文件"}), 400
        
        # 检查文件类型
        filename = file.filename.lower()
        if not (filename.endswith('.zip') or filename.endswith('.rar') or filename.endswith('.7z')):
            return jsonify({"success": False, "message": "仅支持 .zip、.rar、.7z 格式"}), 400
        
        # 检查相应的解压库是否可用
        if filename.endswith('.rar') and not RARFILE_AVAILABLE:
            return jsonify({"success": False, "message": "服务器未安装 rarfile 库，无法解压 .rar 文件"}), 400
        
        if filename.endswith('.7z') and not PY7ZR_AVAILABLE:
            return jsonify({"success": False, "message": "服务器未安装 py7zr 库，无法解压 .7z 文件"}), 400
        
        # 生成任务ID
        task_id = str(uuid.uuid4())
        
        # 创建临时目录
        temp_dir = tempfile.mkdtemp(prefix=f"archive_extract_{task_id}_")
        
        # 保存上传的文件
        archive_path = os.path.join(temp_dir, file.filename)
        file.save(archive_path)
        
        # 初始化任务状态
        archive_extraction_tasks[task_id] = {
            'status': 'processing',
            'message': '开始解压...',
            'extracted_count': 0,
            'temp_dir': temp_dir,
            'archive_path': archive_path
        }
        
        # 启动解压线程
        extract_thread = threading.Thread(
            target=extract_archive_thread,
            args=(task_id, archive_path, temp_dir, filename)
        )
        extract_thread.start()
        
        return jsonify({"success": True, "message": "上传成功，开始解压", "task_id": task_id})
        
    except Exception as e:
        douyin_logger.error(f"压缩包上传失败: {str(e)}")
        return jsonify({"success": False, "message": f"上传失败: {str(e)}"}), 500

@app.route('/api/extract_status/<task_id>')
def get_extract_status(task_id):
    """获取解压任务状态"""
    if task_id not in archive_extraction_tasks:
        return jsonify({"status": "not_found", "message": "任务不存在"})
    
    task = archive_extraction_tasks[task_id]
    return jsonify({
        "status": task['status'],
        "message": task.get('message', ''),
        "extracted_count": task.get('extracted_count', 0)
    })

def extract_archive_thread(task_id, archive_path, temp_dir, filename):
    """解压压缩包的线程函数"""
    try:
        # 更新状态
        archive_extraction_tasks[task_id]['message'] = '正在解压压缩包...'
        
        # 创建解压目标目录
        extract_dir = os.path.join(temp_dir, 'extracted')
        os.makedirs(extract_dir, exist_ok=True)
        
        # 根据文件类型选择解压方式
        if filename.endswith('.zip'):
            extract_zip(archive_path, extract_dir, task_id)
        elif filename.endswith('.rar') and RARFILE_AVAILABLE:
            extract_rar(archive_path, extract_dir, task_id)
        elif filename.endswith('.7z') and PY7ZR_AVAILABLE:
            extract_7z(archive_path, extract_dir, task_id)
        else:
            raise Exception(f"不支持的文件格式: {filename}")
        
        # 查找并移动视频文件
        video_count = move_video_files(extract_dir, task_id)
        
        # 清理临时文件
        shutil.rmtree(temp_dir, ignore_errors=True)
        
        # 更新最终状态
        archive_extraction_tasks[task_id] = {
            'status': 'completed',
            'message': f'解压完成，共提取 {video_count} 个视频文件',
            'extracted_count': video_count
        }
        
        douyin_logger.info(f"压缩包解压完成: {filename}, 提取视频: {video_count} 个")
        
    except Exception as e:
        error_msg = f"解压失败: {str(e)}"
        douyin_logger.error(f"压缩包解压失败: {error_msg}")
        
        # 清理临时文件
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir, ignore_errors=True)
        
        archive_extraction_tasks[task_id] = {
            'status': 'error',
            'error': error_msg,
            'extracted_count': 0
        }

def extract_zip(archive_path, extract_dir, task_id):
    """解压ZIP文件"""
    with zipfile.ZipFile(archive_path, 'r') as zip_ref:
        zip_ref.extractall(extract_dir)

def extract_rar(archive_path, extract_dir, task_id):
    """解压RAR文件"""
    with rarfile.RarFile(archive_path) as rar_ref:
        rar_ref.extractall(extract_dir)

def extract_7z(archive_path, extract_dir, task_id):
    """解压7Z文件"""
    with py7zr.SevenZipFile(archive_path, mode='r') as z:
        z.extractall(extract_dir)

def move_video_files(extract_dir, task_id):
    """查找并移动视频文件到videos目录，保持文件夹结构"""
    video_count = 0
    
    # 确保videos目录存在
    os.makedirs("videos", exist_ok=True)
    
    # 支持的视频格式
    video_extensions = ('.mp4', '.mov', '.avi', '.mkv', '.flv', '.webm', '.wmv', '.3gp', '.m4v')
    
    # 递归查找所有视频文件
    for root, dirs, files in os.walk(extract_dir):
        for file in files:
            if file.lower().endswith(video_extensions):
                source_path = os.path.join(root, file)
                
                # 计算相对路径，保持文件夹结构
                relative_path = os.path.relpath(root, extract_dir)
                
                # 如果是在根目录下的文件，直接放到videos目录
                if relative_path == '.':
                    target_dir = "videos"
                else:
                    # 保持原有的文件夹结构
                    target_dir = os.path.join("videos", relative_path)
                
                # 确保目标目录存在
                os.makedirs(target_dir, exist_ok=True)
                
                # 生成目标文件名，避免重名
                base_name = os.path.splitext(file)[0]
                extension = os.path.splitext(file)[1]
                target_name = file
                counter = 1
                
                while os.path.exists(os.path.join(target_dir, target_name)):
                    target_name = f"{base_name}_{counter}{extension}"
                    counter += 1
                
                target_path = os.path.join(target_dir, target_name)
                
                try:
                    # 移动文件
                    shutil.move(source_path, target_path)
                    video_count += 1
                    
                    # 更新进度
                    archive_extraction_tasks[task_id]['extracted_count'] = video_count
                    archive_extraction_tasks[task_id]['message'] = f'已提取 {video_count} 个视频文件'
                    
                    # 构建显示路径
                    display_path = os.path.join(relative_path, target_name) if relative_path != '.' else target_name
                    douyin_logger.info(f"移动视频文件: {file} -> {display_path}")
                    
                    # 尝试查找对应的txt文件（标题和标签）
                    txt_source = os.path.join(root, base_name + '.txt')
                    if os.path.exists(txt_source):
                        txt_target = os.path.join(target_dir, os.path.splitext(target_name)[0] + '.txt')
                        try:
                            shutil.move(txt_source, txt_target)
                            txt_display_path = os.path.join(relative_path, os.path.splitext(target_name)[0] + '.txt') if relative_path != '.' else os.path.splitext(target_name)[0] + '.txt'
                            douyin_logger.info(f"移动描述文件: {base_name}.txt -> {txt_display_path}")
                        except Exception as e:
                            douyin_logger.warning(f"移动描述文件失败: {str(e)}")
                    
                    # 尝试查找对应的图片文件（封面）
                    for img_ext in ['.jpg', '.jpeg', '.png', '.bmp', '.gif']:
                        img_source = os.path.join(root, base_name + img_ext)
                        if os.path.exists(img_source):
                            img_target = os.path.join(target_dir, os.path.splitext(target_name)[0] + img_ext)
                            try:
                                shutil.move(img_source, img_target)
                                img_display_path = os.path.join(relative_path, os.path.splitext(target_name)[0] + img_ext) if relative_path != '.' else os.path.splitext(target_name)[0] + img_ext
                                douyin_logger.info(f"移动封面文件: {base_name}{img_ext} -> {img_display_path}")
                                break  # 只移动第一个找到的图片
                            except Exception as e:
                                douyin_logger.warning(f"移动封面文件失败: {str(e)}")
                    
                except Exception as e:
                    douyin_logger.error(f"移动视频文件失败: {file}, 错误: {str(e)}")
    
    return video_count

# 抖音采集相关的全局变量
def init_app_services():
    """初始化应用服务"""
    global current_download_thread
    
    # 初始化MD5管理器
    try:
        from utils.md5_manager import md5_manager
        douyin_logger.info("✅ MD5管理器初始化成功")
    except Exception as e:
        douyin_logger.warning(f"⚠️ MD5管理器初始化失败: {str(e)}")
    
    # 如果正在下载，跳过服务检查，避免干扰下载进程
    if current_download_thread and current_download_thread.is_alive():
        douyin_logger.info("🔄 正在下载中，跳过Downloader服务状态检查")
        return True
    
    # 首先检查服务是否已在运行
    if check_downloader_status():
        douyin_logger.info("✅ Downloader服务已连接")
        return True
    
    # 如果没有运行，尝试自动启动
    douyin_logger.info("🔄 Downloader服务未运行，正在自动启动...")
    
    if start_downloader_service():
        douyin_logger.info("✅ Downloader服务自动启动成功")
        return True
    else:
        douyin_logger.error("❌ Downloader服务自动启动失败")
        print("\n⚠️  自动启动失败，请手动启动Downloader服务:")
        print("   1. 打开新的终端窗口")
        print("   2. cd Downloader")
        print("   3. python main.py")
        print("   4. 选择选项 7 (Web API 模式)")
        return False

@app.route('/api/douyin/search/video', methods=['POST'])
def douyin_search_video():
    """抖音视频搜索接口 - 通过HTTP调用Downloader API"""
    if not check_downloader_status():
        return jsonify({'success': False, 'message': 'Downloader服务未运行，请先启动 Downloader Web API 模式'}), 400
    
    try:
        data = request.get_json()
        keyword = data.get('keyword', '')
        pages = data.get('pages', 5)
        cookie = data.get('cookie', '')
        proxy = data.get('proxy', '')
        
        if not keyword:
            return jsonify({'success': False, 'message': '关键词不能为空'}), 400
        
        def search_task():
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                
                async def async_search():
                    # 读取Cookie文件内容
                    cookie_content = ""
                    if cookie:
                        cookie_path = f"cookie/{cookie}"
                        if os.path.exists(cookie_path):
                            with open(cookie_path, 'r', encoding='utf-8') as f:
                                cookie_data = json.load(f)
                                # 处理不同的Cookie文件格式
                                cookies_list = []
                                if isinstance(cookie_data, dict) and "cookies" in cookie_data:
                                    # 新格式: {"cookies": [...]}
                                    cookies_list = cookie_data["cookies"]
                                elif isinstance(cookie_data, list):
                                    # 旧格式: [...]
                                    cookies_list = cookie_data
                                
                                if len(cookies_list) > 0:
                                    cookie_content = "; ".join([f"{item['name']}={item['value']}" for item in cookies_list])
                                    douyin_logger.info(f"视频搜索 - 成功转换Cookie，共 {len(cookies_list)} 个cookie项")
                    
                    # 准备API请求数据
                    api_data = {
                        "keyword": keyword,
                        "pages": pages,
                        "cookie": cookie_content,
                        "proxy": proxy,
                        "source": False
                    }
                    
                    # 调用Downloader API
                    result = await call_downloader_api("/douyin/search/video", api_data)
                    
                    douyin_logger.info(f"视频搜索API返回数据类型: {type(result)}")
                    douyin_logger.info(f"视频搜索API返回数据keys: {result.keys() if isinstance(result, dict) else 'not dict'}")
                    
                    if "error" in result:
                        return {'success': False, 'message': result["message"]}
                    
                    # 检查返回数据格式并提取视频列表
                    if "data" in result:
                        video_data = result["data"]
                        video_count = len(video_data) if isinstance(video_data, list) else 0
                        douyin_logger.info(f"提取到视频数据，数量: {video_count}")
                        add_log("SUCCESS", f"视频搜索成功，共获取 {video_count} 个视频")
                        return {'success': True, 'data': video_data}
                    else:
                        douyin_logger.warning(f"API返回数据格式异常，未找到data字段: {result}")
                        # 如果直接是列表数据
                        if isinstance(result, list):
                            add_log("SUCCESS", f"视频搜索成功，共获取 {len(result)} 个视频")
                            return {'success': True, 'data': result}
                        else:
                            add_log("ERROR", "视频搜索返回数据格式异常")
                            return {'success': False, 'message': '搜索返回数据格式异常'}
                
                return loop.run_until_complete(async_search())
            except Exception as e:
                douyin_logger.error(f"视频搜索失败: {str(e)}")
                return {'success': False, 'message': f'搜索失败: {str(e)}'}
        
        # 在新线程中执行搜索任务
        import threading
        result_container = {}
        
        def run_search():
            result_container['result'] = search_task()
        
        thread = threading.Thread(target=run_search)
        thread.start()
        thread.join(timeout=30)  # 30秒超时
        
        if 'result' in result_container:
            result = result_container['result']
            return jsonify(result)
        else:
            return jsonify({'success': False, 'message': '搜索超时'}), 408
            
    except Exception as e:
        douyin_logger.error(f"搜索接口错误: {str(e)}")
        return jsonify({'success': False, 'message': f'接口错误: {str(e)}'}), 500

@app.route('/api/douyin/detail', methods=['POST'])
def douyin_get_detail():
    """获取抖音视频详情接口 - 通过HTTP调用Downloader API"""
    if not check_downloader_status():
        return jsonify({'success': False, 'message': 'Downloader服务未运行，请先启动 Downloader Web API 模式'}), 400
    
    try:
        data = request.get_json()
        detail_id = data.get('detail_id', '')
        cookie = data.get('cookie', '')
        proxy = data.get('proxy', '')
        
        if not detail_id:
            return jsonify({'success': False, 'message': '视频ID不能为空'}), 400
        
        def detail_task():
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                
                async def async_detail():
                    # 读取Cookie文件内容
                    cookie_content = ""
                    if cookie:
                        cookie_path = f"cookie/{cookie}"
                        if os.path.exists(cookie_path):
                            with open(cookie_path, 'r', encoding='utf-8') as f:
                                cookie_data = json.load(f)
                                # 处理不同的Cookie文件格式
                                cookies_list = []
                                if isinstance(cookie_data, dict) and "cookies" in cookie_data:
                                    # 新格式: {"cookies": [...]}
                                    cookies_list = cookie_data["cookies"]
                                elif isinstance(cookie_data, list):
                                    # 旧格式: [...]
                                    cookies_list = cookie_data
                                
                                if len(cookies_list) > 0:
                                    cookie_content = "; ".join([f"{item['name']}={item['value']}" for item in cookies_list])
                                    douyin_logger.info(f"视频详情 - 成功转换Cookie，共 {len(cookies_list)} 个cookie项")
                    
                    # 准备API请求数据
                    api_data = {
                        "detail_id": detail_id,
                        "cookie": cookie_content,
                        "proxy": proxy
                    }
                    
                    # 调用Downloader API
                    result = await call_downloader_api("/douyin/detail", api_data)
                    
                    douyin_logger.info(f"视频详情API返回数据类型: {type(result)}")
                    
                    if "error" in result:
                        return {'success': False, 'message': result["message"]}
                    
                    # 检查返回数据格式
                    if "data" in result and result["data"]:
                        detail_data = result["data"]
                        add_log("SUCCESS", "视频详情获取成功")
                        return {'success': True, 'data': detail_data}
                    elif isinstance(result, dict) and any(key in result for key in ['aweme_id', 'desc', 'video']):
                        # 如果直接是详情数据
                        add_log("SUCCESS", "视频详情获取成功")
                        return {'success': True, 'data': result}
                    else:
                        add_log("ERROR", "视频详情返回数据格式异常")
                        return {'success': False, 'message': '详情返回数据格式异常'}
                
                return loop.run_until_complete(async_detail())
            except Exception as e:
                douyin_logger.error(f"获取视频详情失败: {str(e)}")
                return {'success': False, 'message': f'获取详情失败: {str(e)}'}
        
        # 在新线程中执行详情获取任务
        import threading
        result_container = {}
        
        def run_detail():
            result_container['result'] = detail_task()
        
        thread = threading.Thread(target=run_detail)
        thread.start()
        thread.join(timeout=15)  # 15秒超时
        
        if 'result' in result_container:
            result = result_container['result']
            return jsonify(result)
        else:
            return jsonify({'success': False, 'message': '获取详情超时'}), 408
            
    except Exception as e:
        douyin_logger.error(f"详情接口错误: {str(e)}")
        return jsonify({'success': False, 'message': f'接口错误: {str(e)}'}), 500

@app.route('/api/douyin/account', methods=['POST'])
def douyin_get_account():
    """获取抖音用户作品接口 - 通过HTTP调用Downloader API"""
    if not check_downloader_status():
        return jsonify({'success': False, 'message': 'Downloader服务未运行，请先启动 Downloader Web API 模式'}), 400
    
    try:
        data = request.get_json()
        account_url = data.get('account_url', '')
        cookie = data.get('cookie', '')
        proxy = data.get('proxy', '')
        tab = data.get('tab', 'post')  # post, like, collection
        pages = data.get('pages', 5)
        
        if not account_url:
            return jsonify({'success': False, 'message': '账号链接不能为空'}), 400
        
        def account_task():
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                
                async def async_account():
                    # 读取Cookie文件内容
                    cookie_content = ""
                    if cookie:
                        cookie_path = f"cookie/{cookie}"
                        if os.path.exists(cookie_path):
                            with open(cookie_path, 'r', encoding='utf-8') as f:
                                cookie_data = json.load(f)
                                # 处理不同的Cookie文件格式
                                cookies_list = []
                                if isinstance(cookie_data, dict) and "cookies" in cookie_data:
                                    # 新格式: {"cookies": [...]}
                                    cookies_list = cookie_data["cookies"]
                                elif isinstance(cookie_data, list):
                                    # 旧格式: [...]
                                    cookies_list = cookie_data
                                
                                if len(cookies_list) > 0:
                                    cookie_content = "; ".join([f"{item['name']}={item['value']}" for item in cookies_list])
                                    douyin_logger.info(f"用户作品 - 成功转换Cookie，共 {len(cookies_list)} 个cookie项")
                    
                    # 直接从账号链接中提取用户ID，不需要通过API解析
                    douyin_logger.info(f"开始从链接中提取用户ID: {account_url}")
                    
                    import re
                    # 匹配抖音用户URL中的sec_user_id
                    # 支持格式: https://www.douyin.com/user/MS4wLjABAAAA...
                    match = re.search(r'/user/([A-Za-z0-9_=-]+)', account_url)
                    
                    if match:
                        sec_user_id = match.group(1)
                        douyin_logger.info(f"成功从链接中提取用户ID: {sec_user_id}")
                        add_log("SUCCESS", f"成功解析用户ID: {sec_user_id[:20]}...")
                    else:
                        douyin_logger.error(f"无法从链接中提取用户ID: {account_url}")
                        add_log("ERROR", "链接格式不正确，无法提取用户ID")
                        return {'success': False, 'message': '链接格式不正确，请输入有效的抖音用户主页链接'}
                    
                    # 第二步：使用解析出的用户ID获取作品
                    api_data = {
                        "sec_user_id": sec_user_id,
                        "tab": tab,
                        "pages": pages,
                        "cookie": cookie_content,
                        "proxy": proxy,
                        "source": False
                    }
                    
                    # 调用Downloader API
                    result = await call_downloader_api("/douyin/account", api_data)
                    
                    douyin_logger.info(f"用户作品API返回数据类型: {type(result)}")
                    
                    if "error" in result:
                        return {'success': False, 'message': result["message"]}
                    
                    # 检查返回数据格式并提取作品列表
                    if "data" in result:
                        account_data = result["data"]
                        video_count = len(account_data) if isinstance(account_data, list) else 0
                        add_log("SUCCESS", f"用户作品获取成功，共 {video_count} 个作品")
                        return {'success': True, 'data': account_data}
                    elif isinstance(result, list):
                        add_log("SUCCESS", f"用户作品获取成功，共 {len(result)} 个作品")
                        return {'success': True, 'data': result}
                    else:
                        add_log("ERROR", "用户作品返回数据格式异常")
                        return {'success': False, 'message': '用户作品返回数据格式异常'}
                
                return loop.run_until_complete(async_account())
            except Exception as e:
                douyin_logger.error(f"获取用户作品失败: {str(e)}")
                return {'success': False, 'message': f'获取用户作品失败: {str(e)}'}
        
        # 在新线程中执行账号作品获取任务
        import threading
        result_container = {}
        
        def run_account():
            result_container['result'] = account_task()
        
        thread = threading.Thread(target=run_account)
        thread.start()
        thread.join(timeout=60)  # 60秒超时
        
        if 'result' in result_container:
            result = result_container['result']
            return jsonify(result)
        else:
            return jsonify({'success': False, 'message': '获取用户作品超时'}), 408
            
    except Exception as e:
        douyin_logger.error(f"账号接口错误: {str(e)}")
        return jsonify({'success': False, 'message': f'接口错误: {str(e)}'}), 500



@app.route('/api/douyin/hot', methods=['GET'])
def douyin_get_hot():
    """获取抖音热榜数据接口 - 通过HTTP调用Downloader API"""
    if not check_downloader_status():
        return jsonify({'success': False, 'message': 'Downloader服务未运行，请先启动 Downloader Web API 模式'}), 400
    
    try:
        cookie = request.args.get('cookie', '')
        proxy = request.args.get('proxy', '')
        
        def hot_task():
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                
                async def async_hot():
                    # 读取Cookie文件内容
                    cookie_content = ""
                    if cookie:
                        cookie_path = f"cookie/{cookie}"
                        if os.path.exists(cookie_path):
                            with open(cookie_path, 'r', encoding='utf-8') as f:
                                cookie_data = json.load(f)
                                # 处理不同的Cookie文件格式
                                cookies_list = []
                                if isinstance(cookie_data, dict) and "cookies" in cookie_data:
                                    # 新格式: {"cookies": [...]}
                                    cookies_list = cookie_data["cookies"]
                                elif isinstance(cookie_data, list):
                                    # 旧格式: [...]
                                    cookies_list = cookie_data
                                
                                if len(cookies_list) > 0:
                                    cookie_content = "; ".join([f"{item['name']}={item['value']}" for item in cookies_list])
                                    douyin_logger.info(f"热榜数据 - 成功转换Cookie，共 {len(cookies_list)} 个cookie项")
                    
                    # 由于Downloader API文档中没有专门的热榜接口，
                    # 我们使用搜索接口来获取热门内容作为替代
                    # 注意：这里会搜索多个热门关键词来汇总热榜数据，是正常行为
                    hot_keywords = ["热门"]  # 简化为只搜索一个主要关键词，减少请求
                    results = []
                    
                    add_log("INFO", "开始获取热榜数据，将搜索热门关键词...")
                    
                    for keyword in hot_keywords:
                        api_data = {
                            "keyword": keyword,
                            "pages": 2,  # 增加页数获取更多内容
                            "cookie": cookie_content,
                            "proxy": proxy,
                            "source": False
                        }
                        
                        add_log("INFO", f"正在搜索关键词: {keyword}")
                        result = await call_downloader_api("/douyin/search/video", api_data)
                        
                        if "error" not in result and "data" in result:
                            video_count = len(result["data"]) if isinstance(result["data"], list) else 0
                            douyin_logger.info(f"关键词 '{keyword}' 获取到 {video_count} 个视频")
                            add_log("SUCCESS", f"关键词 '{keyword}' 获取到 {video_count} 个视频")
                            results.append({
                                "keyword": keyword,
                                "videos": result["data"]
                            })
                        else:
                            error_msg = result.get("message", "未知错误") if isinstance(result, dict) else str(result)
                            douyin_logger.warning(f"关键词 '{keyword}' 搜索失败: {error_msg}")
                            add_log("WARNING", f"关键词 '{keyword}' 搜索失败: {error_msg}")
                    
                    if results:
                        # 整合所有结果为一个数组，保持与其他接口一致的格式
                        all_videos = []
                        for topic in results:
                            if "videos" in topic and topic["videos"]:
                                for video in topic["videos"]:
                                    video["hot_keyword"] = topic["keyword"]  # 添加热门关键词标记
                                    all_videos.append(video)
                        
                        douyin_logger.info(f"热榜数据整合完成，总计 {len(all_videos)} 个视频")
                        add_log("SUCCESS", f"热榜数据获取成功，共 {len(all_videos)} 个视频")
                        
                        return {
                            'success': True, 
                            'data': all_videos,
                            'message': f'热门内容获取成功，共 {len(all_videos)} 条'
                        }
                    else:
                        add_log("ERROR", "所有热门关键词搜索均失败")
                        return {'success': False, 'message': '暂时无法获取热门内容，请稍后重试'}
                
                return loop.run_until_complete(async_hot())
            except Exception as e:
                douyin_logger.error(f"获取热榜失败: {str(e)}")
                return {'success': False, 'message': f'获取热榜失败: {str(e)}'}
        
        # 在新线程中执行热榜获取任务
        import threading
        result_container = {}
        
        def run_hot():
            result_container['result'] = hot_task()
        
        thread = threading.Thread(target=run_hot)
        thread.start()
        thread.join(timeout=30)  # 30秒超时
        
        if 'result' in result_container:
            result = result_container['result']
            return jsonify(result)
        else:
            return jsonify({'success': False, 'message': '获取热榜超时'}), 408
            
    except Exception as e:
        douyin_logger.error(f"热榜接口错误: {str(e)}")
        return jsonify({'success': False, 'message': f'接口错误: {str(e)}'}), 500

@app.route('/api/downloader/status', methods=['GET'])
def get_downloader_status():
    """获取Downloader服务状态"""
    is_running = check_downloader_status()
    return jsonify({
        'running': is_running,
        'message': 'Downloader服务运行中' if is_running else 'Downloader服务未运行'
    })

@app.route('/api/downloader/start', methods=['POST'])
def start_downloader():
    """手动启动Downloader服务"""
    if check_downloader_status():
        return jsonify({'success': True, 'message': 'Downloader服务已在运行'})
    
    if start_downloader_service():
        return jsonify({'success': True, 'message': 'Downloader服务启动成功'})
    else:
        return jsonify({'success': False, 'message': 'Downloader服务启动失败'})

@app.route('/api/downloader/stop', methods=['POST'])
def stop_downloader():
    """手动停止Downloader服务"""
    stop_downloader_service()
    return jsonify({'success': True, 'message': 'Downloader服务停止指令已发送'})

@app.route('/api/downloader/logs', methods=['GET'])
def get_downloader_logs():
    """获取Downloader服务日志"""
    global downloader_logs
    return jsonify({
        'logs': downloader_logs,
        'count': len(downloader_logs)
    })

@app.route('/api/downloader/logs/clear', methods=['POST'])
def clear_downloader_logs():
    """清空Downloader服务日志"""
    global downloader_logs
    downloader_logs.clear()
    return jsonify({'success': True, 'message': '日志已清空'})

@app.route('/api/douyin/download', methods=['POST'])
def douyin_download_videos():
    """批量下载抖音视频接口"""
    if not check_downloader_status():
        return jsonify({'success': False, 'message': 'Downloader服务未运行，请先启动 Downloader Web API 模式'}), 400
    
    try:
        data = request.get_json()
        videos = data.get('videos', [])
        cookie = data.get('cookie', '')
        proxy = data.get('proxy', '')
        
        if not videos:
            return jsonify({'success': False, 'message': '没有提供要下载的视频'}), 400
        
        def download_task():
            try:
                # 设置全局下载控制变量
                global download_stop_flag, current_download_thread
                download_stop_flag = False
                current_download_thread = threading.current_thread()
                
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                
                async def async_download():
                    # 读取Cookie文件内容
                    cookie_content = ""
                    if cookie:
                        cookie_path = os.path.join("cookie", f"{cookie}.json")
                        if os.path.exists(cookie_path):
                            try:
                                with open(cookie_path, 'r', encoding='utf-8') as f:
                                    cookie_data = json.load(f)
                                    if isinstance(cookie_data, dict) and "cookie" in cookie_data:
                                        cookie_content = cookie_data["cookie"]
                            except Exception as e:
                                douyin_logger.warning(f"读取Cookie文件失败: {str(e)}")
                    
                    total_videos = len(videos)
                    success_count = 0
                    failed_videos = []
                    download_results = []
                    
                    # 发送下载开始状态
                    try:
                        socketio.emit('download_progress', {
                            'current': 0,
                            'total': total_videos,
                            'status': 'started',
                            'message': f'开始下载 {total_videos} 个视频...',
                            'success_count': 0,
                            'failed_count': 0
                        })
                    except Exception as emit_error:
                        douyin_logger.warning(f"WebSocket推送失败: {emit_error}")
                    
                    # 逐个下载视频
                    for i, video in enumerate(videos):
                        # 检查是否需要停止下载
                        global download_stop_flag
                        if download_stop_flag:
                            douyin_logger.info("⏹️ 检测到停止信号，中断下载...")
                            try:
                                socketio.emit('download_progress', {
                                    'current': i,
                                    'total': total_videos,
                                    'status': 'stopped',
                                    'message': f'下载已停止。已成功下载 {success_count} 个，失败 {len(failed_videos)} 个',
                                    'success_count': success_count,
                                    'failed_count': len(failed_videos)
                                })
                            except Exception as emit_error:
                                douyin_logger.warning(f"WebSocket推送失败: {emit_error}")
                            break
                        
                        download_url = None  # 为每个视频初始化download_url
                        try:
                            # 发送下载进度更新
                            try:
                                socketio.emit('download_progress', {
                                    'current': i + 1,
                                    'total': total_videos,
                                    'status': 'downloading',
                                    'message': f'正在下载第 {i+1} 个视频，共 {total_videos} 个',
                                    'success_count': success_count,
                                    'failed_count': len(failed_videos)
                                })
                            except Exception as emit_error:
                                douyin_logger.warning(f"WebSocket推送失败: {emit_error}")
                            
                            douyin_logger.info(f"处理第 {i+1} 个视频: {video}")
                            # 打印视频数据的键名，帮助调试
                            douyin_logger.info(f"视频数据键名: {list(video.keys()) if isinstance(video, dict) else '非字典类型'}")
                            aweme_id = video.get('aweme_id') or video.get('id')
                            title = video.get('desc') or video.get('title') or f"视频_{aweme_id}"
                            download_url = None  # 初始化download_url变量
                            
                            if not aweme_id:
                                failed_videos.append({'video': title, 'reason': '缺少视频ID'})
                                continue
                            
                            # 首先尝试使用搜索结果中已有的下载链接
                            if video.get('downloads'):
                                download_url = video.get('downloads')
                                douyin_logger.info(f"使用搜索结果中的下载URL: {download_url}")
                            elif video.get('download_addr'):
                                download_url = video.get('download_addr')
                                douyin_logger.info(f"使用搜索结果中的download_addr: {download_url}")
                            else:
                                # 如果没有现成的下载链接，调用详情API获取
                                detail_data = {
                                    "cookie": cookie_content,
                                    "proxy": proxy,
                                    "detail_id": aweme_id,
                                    "source": False
                                }
                            
                                detail_result = await call_downloader_api("/douyin/detail", detail_data)
                                
                                douyin_logger.info(f"详情API返回: {detail_result}")
                                
                                if "error" in detail_result or not detail_result.get("data"):
                                    failed_videos.append({'video': title, 'reason': '获取视频详情失败'})
                                    continue
                                
                                video_data = detail_result["data"][0] if isinstance(detail_result["data"], list) else detail_result["data"]
                                douyin_logger.info(f"视频数据: {video_data}")
                                
                                # 从详情API响应中获取下载URL
                                if isinstance(video_data, dict) and video_data.get("downloads"):
                                    download_url = video_data.get("downloads")
                                
                                # 如果没有downloads字段，尝试从video结构中获取
                                elif isinstance(video_data, dict):
                                    video_info = video_data.get("video")
                                    if isinstance(video_info, dict):
                                        # 尝试play_addr.url_list
                                        play_addr = video_info.get("play_addr")
                                        if isinstance(play_addr, dict):
                                            url_list = play_addr.get("url_list", [])
                                            if url_list and isinstance(url_list, list):
                                                download_url = url_list[0]
                                        
                                        # 如果没有找到，尝试其他可能的字段
                                        if not download_url:
                                            download_url = video_info.get("playAddr") or video_info.get("download_addr")
                                
                                douyin_logger.info(f"从详情API提取的下载URL: {download_url}")
                            
                            if not download_url:
                                failed_videos.append({'video': title, 'reason': '无法获取下载链接'})
                                continue
                            
                            # 如果是列表，取第一个链接
                            if isinstance(download_url, list):
                                download_url = download_url[0] if download_url else ""
                            
                            if not download_url:
                                failed_videos.append({'video': title, 'reason': '下载链接为空'})
                                continue
                            
                            # 提取作者信息用于创建文件夹
                            author_nickname = None
                            author_info = video.get('author')
                            if isinstance(author_info, dict):
                                author_nickname = author_info.get('nickname') or author_info.get('unique_id')
                            elif video.get('nickname'):
                                author_nickname = video.get('nickname')
                            elif video.get('author_nickname'):
                                author_nickname = video.get('author_nickname')
                            
                            # 如果有作者信息，按用户名创建文件夹，否则使用默认文件夹
                            if author_nickname:
                                # 清理用户名，生成安全的文件夹名
                                safe_author = "".join(c for c in author_nickname if c.isalnum() or c in (' ', '-', '_')).rstrip()
                                if len(safe_author) > 30:
                                    safe_author = safe_author[:30]
                                downloads_dir = os.path.join("downloads", safe_author)
                                douyin_logger.info(f"按用户文件夹下载: {safe_author}")
                            else:
                                downloads_dir = os.path.join("downloads", "未知用户")
                                douyin_logger.info("未找到作者信息，使用默认文件夹")
                            
                            os.makedirs(downloads_dir, exist_ok=True)
                            
                            # 生成安全的文件名
                            safe_title = "".join(c for c in title if c.isalnum() or c in (' ', '-', '_')).rstrip()
                            if len(safe_title) > 50:
                                safe_title = safe_title[:50]
                            filename = f"{safe_title}.mp4"
                            filepath = os.path.join(downloads_dir, filename)
                            
                            # 如果文件已存在，添加数字后缀
                            counter = 1
                            while os.path.exists(filepath):
                                base_name = safe_title
                                if len(base_name) > 45:  # 为数字后缀预留空间
                                    base_name = base_name[:45]
                                filename = f"{base_name}_{counter}.mp4"
                                filepath = os.path.join(downloads_dir, filename)
                                counter += 1
                            
                            # 准备请求头，包含Cookie
                            headers = {
                                'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 14_2 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.0.1 Mobile/15E148 Safari/604.1',
                                'Referer': 'https://www.douyin.com/',
                                'Accept': '*/*',
                                'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
                                'Accept-Encoding': 'gzip, deflate, br',
                                'Connection': 'keep-alive',
                                'Sec-Fetch-Dest': 'video',
                                'Sec-Fetch-Mode': 'no-cors',
                                'Sec-Fetch-Site': 'cross-site'
                            }
                            
                            # 如果有Cookie，添加到请求头
                            if cookie_content:
                                headers['Cookie'] = cookie_content
                            
                            # 下载视频文件
                            async with httpx.AsyncClient(timeout=60.0, headers=headers, follow_redirects=True) as client:
                                try:
                                    response = await client.get(download_url)
                                    if response.status_code == 200:
                                        with open(filepath, 'wb') as f:
                                            f.write(response.content)
                                        
                                        # 创建对应的.txt标签文件
                                        video_desc = video.get('desc') or video.get('title', '')
                                        create_video_txt_file(filepath, title, video_desc)
                                        
                                        success_count += 1
                                        download_results.append({
                                            'title': title,
                                            'aweme_id': aweme_id,
                                            'filename': filename,
                                            'filepath': filepath,
                                            'status': 'success'
                                        })
                                        add_log("SUCCESS", f"视频下载成功: {title}")
                                        douyin_logger.info(f"视频下载成功: {title} -> {filename}")
                                        
                                        # 发送下载成功的进度更新
                                        try:
                                            socketio.emit('download_progress', {
                                                'current': i + 1,
                                                'total': total_videos,
                                                'status': 'success',
                                                'message': f'第 {i+1} 个视频下载成功: {title}',
                                                'success_count': success_count,
                                                'failed_count': len(failed_videos),
                                                'video_title': title
                                            })
                                        except Exception as emit_error:
                                            douyin_logger.warning(f"WebSocket推送失败: {emit_error}")
                                    else:
                                        failed_videos.append({'video': title, 'reason': f'下载失败，状态码: {response.status_code}'})
                                        douyin_logger.warning(f"下载失败，状态码: {response.status_code}, URL: {download_url if 'download_url' in locals() else 'unknown'}")
                                        
                                        # 发送下载失败的进度更新
                                        try:
                                            socketio.emit('download_progress', {
                                                'current': i + 1,
                                                'total': total_videos,
                                                'status': 'failed',
                                                'message': f'第 {i+1} 个视频下载失败: {title}',
                                                'success_count': success_count,
                                                'failed_count': len(failed_videos),
                                                'video_title': title,
                                                'error': f'状态码: {response.status_code}'
                                            })
                                        except Exception as emit_error:
                                            douyin_logger.warning(f"WebSocket推送失败: {emit_error}")
                                except Exception as download_error:
                                    failed_videos.append({'video': title, 'reason': f'下载异常: {str(download_error)}'})
                                    douyin_logger.error(f"下载异常: {str(download_error)}")
                                    
                                    # 发送下载异常的进度更新
                                    try:
                                        socketio.emit('download_progress', {
                                            'current': i + 1,
                                            'total': total_videos,
                                            'status': 'failed',
                                            'message': f'第 {i+1} 个视频下载异常: {title}',
                                            'success_count': success_count,
                                            'failed_count': len(failed_videos),
                                            'video_title': title,
                                            'error': str(download_error)
                                        })
                                    except Exception as emit_error:
                                        douyin_logger.warning(f"WebSocket推送失败: {emit_error}")
                        
                        except Exception as e:
                            video_title = title if 'title' in locals() else f'视频_{i+1}'
                            failed_videos.append({'video': video_title, 'reason': str(e)})
                            douyin_logger.error(f"处理视频失败: {str(e)}")
                            douyin_logger.error(f"错误详情 - 视频: {video}, 变量状态: download_url={'已定义' if 'download_url' in locals() else '未定义'}")
                            
                            # 发送处理失败的进度更新
                            try:
                                socketio.emit('download_progress', {
                                    'current': i + 1,
                                    'total': total_videos,
                                    'status': 'failed',
                                    'message': f'第 {i+1} 个视频处理失败: {video_title}',
                                    'success_count': success_count,
                                    'failed_count': len(failed_videos),
                                    'video_title': video_title,
                                    'error': str(e)
                                })
                            except Exception as emit_error:
                                douyin_logger.warning(f"WebSocket推送失败: {emit_error}")
                    
                    # 返回下载结果
                    result_message = f"下载完成！成功: {success_count}/{total_videos}"
                    if failed_videos:
                        result_message += f"，失败: {len(failed_videos)} 个"
                    
                    add_log("INFO", result_message)
                    douyin_logger.info(result_message)
                    
                    # 发送最终完成状态
                    try:
                        socketio.emit('download_progress', {
                            'current': total_videos,
                            'total': total_videos,
                            'status': 'completed',
                            'message': result_message,
                            'success_count': success_count,
                            'failed_count': len(failed_videos),
                            'failed_videos': failed_videos
                        })
                    except Exception as emit_error:
                        douyin_logger.warning(f"WebSocket推送失败: {emit_error}")
                    
                    return {
                        'success': True,
                        'message': result_message,
                        'data': {
                            'total': total_videos,
                            'success_count': success_count,
                            'failed_count': len(failed_videos),
                            'download_results': download_results,
                            'failed_videos': failed_videos
                        }
                    }
                
                return loop.run_until_complete(async_download())
            except Exception as e:
                douyin_logger.error(f"批量下载视频失败: {str(e)}")
                return {'success': False, 'message': f'下载失败: {str(e)}'}
            finally:
                # 清理全局线程引用
                current_download_thread = None
        
        # 立即返回响应，避免HTTP超时
        # 在新线程中执行下载任务，不等待完成
        import threading
        thread = threading.Thread(target=download_task)
        thread.daemon = True  # 设为守护线程
        thread.start()
        
        # 立即返回成功响应
        return jsonify({
            'success': True, 
            'message': f'下载任务已启动，正在后台下载 {len(videos)} 个视频，请通过进度条查看实时进度'
        })
            
    except Exception as e:
        douyin_logger.error(f"下载接口错误: {str(e)}")
        return jsonify({'success': False, 'message': f'接口错误: {str(e)}'}), 500

@app.route('/api/douyin/download/stop', methods=['POST'])
def stop_download():
    """停止当前下载任务"""
    try:
        global download_stop_flag, current_download_thread
        
        if current_download_thread is None:
            return jsonify({'success': False, 'message': '当前没有进行中的下载任务'})
        
        # 设置停止标志
        download_stop_flag = True
        douyin_logger.info("⏹️ 收到停止下载请求")
        
        # 发送停止状态到前端
        socketio.emit('download_progress', {
            'current': 0,
            'total': 0,
            'status': 'stopping',
            'message': '正在停止下载...',
            'success_count': 0,
            'failed_count': 0
        })
        
        return jsonify({'success': True, 'message': '停止信号已发送，下载将在当前视频完成后停止'})
        
    except Exception as e:
        douyin_logger.error(f"停止下载失败: {str(e)}")
        return jsonify({'success': False, 'message': f'停止下载失败: {str(e)}'}), 500

@app.route('/api/douyin/download/status', methods=['GET'])
def get_download_status():
    """获取下载状态"""
    try:
        global current_download_thread, download_stop_flag
        
        is_downloading = current_download_thread is not None and current_download_thread.is_alive()
        
        return jsonify({
            'success': True,
            'data': {
                'is_downloading': is_downloading,
                'stop_requested': download_stop_flag
            }
        })
        
    except Exception as e:
        douyin_logger.error(f"获取下载状态失败: {str(e)}")
        return jsonify({'success': False, 'message': f'获取状态失败: {str(e)}'}), 500

def create_video_txt_file(video_filepath, title, desc=""):
    """为视频创建对应的.txt标签文件"""
    try:
        # 获取视频文件的完整路径，并替换扩展名为.txt
        txt_path = os.path.splitext(video_filepath)[0] + ".txt"
        
        # 从描述中提取标签
        tags = []
        if desc:
            # 查找所有以#开头的标签
            import re
            hashtags = re.findall(r'#([^#\s]+)', desc)
            tags = [f"#{tag}" for tag in hashtags if tag]
        
        # 清理标题，移除其中的hashtags
        clean_title = title
        if desc:
            import re
            clean_title = re.sub(r'#[^#\s]*\s*', '', title).strip()
            if not clean_title:
                clean_title = title.strip()
        
        # 创建.txt文件内容 - 按照demo.txt的格式
        content_lines = [clean_title]  # 第一行是纯净的标题
        if tags:
            # 第二行是所有标签用空格连接
            content_lines.append(' '.join(tags))
        
        # 写入文件
        with open(txt_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(content_lines))
        
        douyin_logger.info(f"已创建标签文件: {txt_path}")
        return True
        
    except Exception as e:
        douyin_logger.error(f"创建标签文件失败: {str(e)}")
        return False

@app.route('/api/douyin/link_parse', methods=['POST'])
def douyin_parse_link():
    """解析抖音分享链接接口 - 通过HTTP调用Downloader API"""
    if not check_downloader_status():
        return jsonify({'success': False, 'message': 'Downloader服务未运行，请先启动 Downloader Web API 模式'}), 400
    
    try:
        data = request.get_json()
        text = data.get('text', '')
        proxy = data.get('proxy', '')
        
        if not text:
            return jsonify({'success': False, 'message': '分享链接不能为空'}), 400
        
        def parse_task():
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                
                async def async_parse():
                    # 准备API请求数据
                    api_data = {
                        "text": text,
                        "proxy": proxy
                    }
                    
                    # 调用Downloader API
                    result = await call_downloader_api("/douyin/share", api_data)
                    
                    douyin_logger.info(f"链接解析API返回数据: {result}")
                    douyin_logger.info(f"链接解析API返回数据类型: {type(result)}")
                    
                    if "error" in result:
                        return {'success': False, 'message': result["message"]}
                    
                    # 检查返回数据格式
                    if "url" in result:
                        # 重新构造适合前端的数据格式
                        parsed_urls = [{
                            "url": result["url"],
                            "original": text,
                            "type": "douyin_user" if "/user/" in result["url"] else "douyin_content"
                        }]
                        douyin_logger.info(f"构造的前端数据: {parsed_urls}")
                        add_log("SUCCESS", f"链接解析成功: {result['url']}")
                        return {'success': True, 'data': {'urls': parsed_urls}}
                    else:
                        douyin_logger.warning(f"未预期的返回数据格式，完整数据: {result}")
                        add_log("ERROR", "链接解析返回数据格式异常")
                        return {'success': False, 'message': '链接解析返回数据格式异常'}
                
                return loop.run_until_complete(async_parse())
            except Exception as e:
                douyin_logger.error(f"解析链接失败: {str(e)}")
                return {'success': False, 'message': f'解析失败: {str(e)}'}
        
        # 在新线程中执行解析任务
        import threading
        result_container = {}
        
        def run_parse():
            result_container['result'] = parse_task()
        
        thread = threading.Thread(target=run_parse)
        thread.start()
        thread.join(timeout=15)  # 15秒超时
        
        if 'result' in result_container:
            result = result_container['result']
            return jsonify(result)
        else:
            return jsonify({'success': False, 'message': '解析超时'}), 408
            
    except Exception as e:
        douyin_logger.error(f"解析接口错误: {str(e)}")
        return jsonify({'success': False, 'message': f'接口错误: {str(e)}'}), 500

# 在应用启动时初始化服务
def init_app():
    """应用初始化"""
    # 加载多账号任务数据
    load_multi_tasks_from_file()
    # 启动内存清理线程
    start_cleanup_thread()
    # 检查Downloader服务状态
    init_app_services()

# 在Flask 2.2+中使用 before_request 替代 before_first_request
@app.before_request
def before_first_request():
    if not hasattr(app, 'initialized'):
        init_app()
        app.initialized = True

# 设置Flask密钥
app.secret_key = os.urandom(24)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        if verify_login(username, password):
            session['logged_in'] = True
            return redirect(url_for('index'))
        else:
            return render_template('login.html', error='用户名或密码错误')
    
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('logged_in', None)
    return redirect(url_for('login'))

@app.route('/admin')
@login_required
def admin():
    auth_config = load_auth_config()
    return render_template('admin.html', username=auth_config['username'])

@app.route('/api/update_auth', methods=['POST'])
@login_required
def update_auth():
    new_username = request.form.get('username')
    new_password = request.form.get('password')
    
    if not new_username or not new_password:
        return jsonify({'success': False, 'message': '用户名和密码不能为空'})
    
    auth_config = load_auth_config()
    auth_config['username'] = new_username
    auth_config['password'] = new_password
    save_auth_config(auth_config)
    
    return jsonify({'success': True, 'message': '账号信息更新成功'})

# 为所有需要登录的路由添加验证
@app.before_request
def check_login():
    # 不需要登录的路由
    public_routes = ['login', 'static']
    
    # 检查当前路由是否需要登录
    if (request.endpoint not in public_routes and 
        'logged_in' not in session and 
        not request.path.startswith('/static/')):
        return redirect(url_for('login'))

# MD5管理相关API
@app.route('/api/md5/list', methods=['GET'])
def list_md5_records():
    """获取所有视频MD5记录"""
    try:
        from utils.md5_manager import md5_manager
        
        page = request.args.get('page', 1, type=int)
        limit = request.args.get('limit', 50, type=int)
        offset = (page - 1) * limit
        
        records = md5_manager.get_all_records(limit=limit, offset=offset)
        return jsonify({
            "success": True,
            "data": records
        })
    except Exception as e:
        douyin_logger.error(f"获取MD5记录失败: {str(e)}")
        return jsonify({
            "success": False,
            "message": f"获取MD5记录失败: {str(e)}"
        }), 500

@app.route('/api/md5/check', methods=['POST'])
def check_md5_duplicate():
    """检查视频是否重复"""
    try:
        from utils.md5_manager import md5_manager
        
        data = request.get_json()
        file_path = data.get('file_path', '')
        
        if not file_path:
            return jsonify({
                "success": False,
                "message": "未提供视频路径"
            }), 400
        
        full_path = os.path.join("videos", file_path)
        if not os.path.exists(full_path):
            return jsonify({
                "success": False,
                "message": "视频文件不存在"
            }), 404
        
        is_duplicate = md5_manager.is_duplicate(full_path)
        md5_value = md5_manager.calculate_md5(full_path)
        
        return jsonify({
            "success": True,
            "is_duplicate": is_duplicate,
            "md5": md5_value,
            "message": "视频已存在" if is_duplicate else "视频未重复"
        })
    except Exception as e:
        douyin_logger.error(f"检查MD5失败: {str(e)}")
        return jsonify({
            "success": False,
            "message": f"检查MD5失败: {str(e)}"
        }), 500

@app.route('/api/md5/add', methods=['POST'])
def add_video_md5():
    """手动添加视频MD5记录"""
    try:
        from utils.md5_manager import md5_manager
        
        data = request.get_json()
        file_path = data.get('file_path', '')
        cookie_name = data.get('cookie_name', '')
        title = data.get('title', '')
        tags = data.get('tags', [])
        
        if not file_path:
            return jsonify({
                "success": False,
                "message": "未提供视频路径"
            }), 400
        
        full_path = os.path.join("videos", file_path)
        if not os.path.exists(full_path):
            return jsonify({
                "success": False,
                "message": "视频文件不存在"
            }), 404
        
        success = md5_manager.record_md5(
            full_path,
            cookie_name=cookie_name,
            title=title,
            tags=tags
        )
        
        if success:
            return jsonify({
                "success": True,
                "message": "添加MD5记录成功"
            })
        else:
            return jsonify({
                "success": False,
                "message": "MD5记录已存在或添加失败"
            }), 400
    except Exception as e:
        douyin_logger.error(f"添加MD5记录失败: {str(e)}")
        return jsonify({
            "success": False,
            "message": f"添加MD5记录失败: {str(e)}"
        }), 500

@app.route('/api/stop_upload', methods=['POST'])
def stop_upload():
    """中止上传任务"""
    global is_uploading, is_multi_uploading
    
    # 标记上传状态为已中止
    is_uploading = False
    is_multi_uploading = False
    
    # 更新所有等待中的任务状态为已中止
    for task in upload_tasks:
        if task["status"] in ["等待中", "上传中"]:
            task["status"] = "已中止"
    
    # 更新多账号任务状态，保存进度以便续传
    for task in multi_account_tasks:
        if task["status"] in ["waiting", "uploading"]:
            # 记录已完成的视频数量，以便下次续传
            progress_msg = f"已中止上传（已完成{task['completed_videos']}/{len(task['videos'])}个视频）"
            update_task_status(task, "stopped", progress_msg)
            douyin_logger.info(f"保存任务 {task['cookie']} 的上传进度: {task['completed_videos']}/{len(task['videos'])}，以便下次续传")
    
    # 保存多账号任务状态
    save_multi_tasks_to_file()
    
    return jsonify({
        "success": True,
        "message": "已中止所有上传任务，下次可从断点继续"
    })

@app.route('/api/clear_tasks', methods=['POST'])
def clear_tasks():
    """清空已中止的任务列表"""
    global upload_tasks
    
    # 只有在没有正在上传的情况下才能清空
    if is_uploading:
        return jsonify({
            "success": False,
            "message": "无法清空正在进行中的任务"
        }), 400
    
    # 清空任务列表
    upload_tasks = []
    
    return jsonify({
        "success": True,
        "message": "已清空任务列表"
    })

if __name__ == '__main__':
    print("📱 抖音自动化上传工具启动")
    print("🌐 Web界面地址: http://0.0.0.0:5000")
    print("🛡️  增强反检测系统已激活:")
    print("   • 13层基础反检测机制")
    print("   • 高级浏览器指纹伪装")
    print("   • 人类行为模拟系统") 
    print("   • 音频/Canvas/WebGL指纹混淆")
    print("   • 时间/地理位置伪装")
    print("📦 压缩包批量上传功能:")
    print("   • 支持 .zip/.rar/.7z 格式")
    print("   • 自动提取视频文件到videos目录")
    print("   • 保持原有文件夹结构，便于分类管理")
    print("   • 同时移动对应的.txt描述文件和封面图片")
    print("📋 使用说明:")
    print("  1. 访问Web界面管理账号和视频")
    print("  2. 配置代理和上传设置") 
    print("  3. 使用压缩包批量上传或单个选择视频")
    print("  4. 开始批量上传视频")
    print("  5. 使用视频权限设置功能管理已发布视频")
    
    # 检查压缩包解压库
    if not RARFILE_AVAILABLE:
        print("⚠️  警告: 未检测到 rarfile 库，无法解压 .rar 文件")
        print("   安装命令: pip install rarfile")
    
    if not PY7ZR_AVAILABLE:
        print("⚠️  警告: 未检测到 py7zr 库，无法解压 .7z 文件")
        print("   安装命令: pip install py7zr")
    
    print("-" * 50)
    
    socketio.run(app, debug=True, host='0.0.0.0', port=5000, use_reloader=False, allow_unsafe_werkzeug=True) 