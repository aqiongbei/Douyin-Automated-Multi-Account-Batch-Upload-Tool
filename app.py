from flask import Flask, render_template, request, jsonify, send_from_directory
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
    try:
        # 使用docs端点检查，因为根路径会重定向
        response = requests.get(f"{DOWNLOADER_API_BASE}/docs", timeout=3)
        return response.status_code == 200
    except:
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
            emit('browser_screenshot', {
                'session_id': session_id,
                'screenshot': screenshot_data,
                'timestamp': time.time()
            })

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
def index():
    return render_template('index.html')

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

# 获取指定文件夹下的视频文件列表
@app.route('/api/downloads/videos/<folder_name>')
def get_folder_videos_api(folder_name):
    try:
        folder_path = os.path.join(os.getcwd(), 'downloads', folder_name)
        if not os.path.exists(folder_path) or not os.path.isdir(folder_path):
            return jsonify({'success': False, 'error': '文件夹不存在'})
        
        video_extensions = ['.mp4', '.avi', '.mov', '.mkv', '.flv', '.wmv', '.webm', '.m4v']
        videos = []
        
        for item in os.listdir(folder_path):
            if any(item.lower().endswith(ext) for ext in video_extensions):
                videos.append(item)
        
        return jsonify({'success': True, 'videos': videos})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/video/process', methods=['POST'])
def process_video():
    """处理视频编辑请求"""
    try:
        # 获取设置
        if request.content_type == 'application/json':
            # JSON请求 - 来自文件夹选择
            data = request.get_json()
            settings = data.get('settings', {})
            folder_name = data.get('folder_name')
            video_filename = data.get('video_filename')
            
            if not folder_name or not video_filename:
                return jsonify({'error': '缺少文件夹或视频文件名'}), 400
                
            # 从downloads文件夹获取视频
            input_path = os.path.join(os.getcwd(), 'downloads', folder_name, video_filename)
            if not os.path.exists(input_path):
                return jsonify({'error': '指定的视频文件不存在'}), 400
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
        if request.content_type == 'application/json':
            # 文件夹选择模式 - 保持文件夹结构
            output_filename = f"{name}_edited{ext}"
            output_dir = os.path.join('videos', folder_name)
            output_path = os.path.join(output_dir, output_filename)
        else:
            # 上传模式 - 直接放在videos根目录
            output_filename = f"{name}_edited{ext}"
            output_dir = 'videos'
            output_path = os.path.join(output_dir, output_filename)
        
        # 确保输出目录存在
        os.makedirs(output_dir, exist_ok=True)
        
        # 构建FFmpeg命令
        ffmpeg_cmd = build_ffmpeg_command(input_path, output_path, settings)
        
        # 执行FFmpeg命令
        import subprocess
        result = subprocess.run(ffmpeg_cmd, capture_output=True, text=True)
        
        if result.returncode == 0:
            # 如果是文件夹选择模式，尝试复制对应的txt文件
            if request.content_type == 'application/json' and folder_name and video_filename:
                # 查找原始txt文件（需要URL解码文件名）
                import urllib.parse
                decoded_name = urllib.parse.unquote(name)
                original_txt_path = os.path.join(os.getcwd(), 'downloads', folder_name, f"{decoded_name}.txt")
                
                # 如果解码后的文件不存在，尝试使用原始文件名
                if not os.path.exists(original_txt_path):
                    original_txt_path = os.path.join(os.getcwd(), 'downloads', folder_name, f"{name}.txt")
                
                if os.path.exists(original_txt_path):
                    # 复制txt文件到输出目录
                    output_txt_path = os.path.join(output_dir, f"{name}_edited.txt")
                    try:
                        import shutil
                        shutil.copy2(original_txt_path, output_txt_path)
                        print(f"已复制txt文件: {original_txt_path} -> {output_txt_path}")
                    except Exception as e:
                        print(f"复制txt文件失败: {e}")
                else:
                    print(f"未找到对应的txt文件: {original_txt_path}")
                
                # 同时尝试复制可能存在的封面图片文件
                for img_ext in ['.jpg', '.jpeg', '.png', '.webp']:
                    original_img_path = os.path.join(os.getcwd(), 'downloads', folder_name, f"{decoded_name}{img_ext}")
                    if not os.path.exists(original_img_path):
                        original_img_path = os.path.join(os.getcwd(), 'downloads', folder_name, f"{name}{img_ext}")
                    
                    if os.path.exists(original_img_path):
                        output_img_path = os.path.join(output_dir, f"{name}_edited{img_ext}")
                        try:
                            import shutil
                            shutil.copy2(original_img_path, output_img_path)
                            print(f"已复制封面图片: {original_img_path} -> {output_img_path}")
                            break  # 只复制第一个找到的图片
                        except Exception as e:
                            print(f"复制封面图片失败: {e}")
                
                # 如果有文件夹结构，返回相对路径
                relative_output = os.path.join(folder_name, output_filename).replace('\\', '/')
                return jsonify({
                    'success': True,
                    'output_file': relative_output,
                    'message': '视频处理完成，已保持文件夹结构并复制txt文件'
                })
            else:
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

def build_ffmpeg_command(input_path, output_path, settings):
    """构建FFmpeg命令"""
    cmd = ['ffmpeg', '-i', input_path]
    
    # 视频滤镜
    filters = []
    
    # 画面调整
    if settings.get('brightness', 0) != 0 or settings.get('contrast', 0) != 0 or settings.get('saturation', 0) != 0:
        brightness = settings.get('brightness', 0) / 100.0
        contrast = 1 + settings.get('contrast', 0) / 100.0
        saturation = 1 + settings.get('saturation', 0) / 100.0
        filters.append(f'eq=brightness={brightness}:contrast={contrast}:saturation={saturation}')
    
    # 锐化
    if settings.get('sharpen', 0) > 0:
        sharpen_value = settings.get('sharpen', 0) / 100.0
        filters.append(f'unsharp=5:5:{sharpen_value}:5:5:0.0')
    
    # 降噪
    if settings.get('denoise', 0) > 0:
        denoise_value = settings.get('denoise', 0) / 100.0 * 10
        filters.append(f'hqdn3d={denoise_value}')
    
    # 分辨率设置
    resolution = settings.get('resolution', {})
    if resolution.get('width') and resolution.get('height'):
        width = resolution['width']
        height = resolution['height']
        mode = resolution.get('mode', 'crop')
        
        if mode == 'stretch':
            filters.append(f'scale={width}:{height}')
        elif mode == 'crop':
            filters.append(f'scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height}')
        elif mode == 'letterbox':
            filters.append(f'scale={width}:{height}:force_original_aspect_ratio=decrease,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:black')
        elif mode == 'pad':
            filters.append(f'scale={width}:{height}:force_original_aspect_ratio=decrease,gblur=sigma=20,scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height}')
    
    # 旋转和翻转
    transform = settings.get('transform', {})
    if transform.get('rotation', 0) != 0:
        rotation = transform['rotation']
        if rotation == 90:
            filters.append('transpose=1')
        elif rotation == 180:
            filters.append('transpose=1,transpose=1')
        elif rotation == 270:
            filters.append('transpose=2')
    
    if transform.get('flipH', False):
        filters.append('hflip')
    
    if transform.get('flipV', False):
        filters.append('vflip')
    
    # 分屏效果
    split_screen = settings.get('splitScreen', {})
    if split_screen.get('enabled', False):
        direction = split_screen.get('direction', 'horizontal')
        blur = split_screen.get('blur', False)
        
        if direction == 'horizontal':
            filters.append('scale=iw/3:ih/3,tile=3x3')
        elif direction == 'vertical':
            filters.append('scale=iw/3:ih/3,tile=3x3')
        
        if blur:
            filters.append('boxblur=5:1')
    
    # 动态缩放
    zoom = settings.get('zoom', {})
    if zoom.get('enabled', False):
        zoom_min = zoom.get('min', 0.01)
        zoom_max = zoom.get('max', 0.10)
        direction = zoom.get('direction', 'in')
        
        if direction == 'in':
            filters.append(f'zoompan=z=\'min(zoom+{zoom_max},1.5)\':d=1:x=iw/2-(iw/zoom/2):y=ih/2-(ih/zoom/2)')
        elif direction == 'out':
            filters.append(f'zoompan=z=\'max(zoom-{zoom_max},1)\':d=1:x=iw/2-(iw/zoom/2):y=ih/2-(ih/zoom/2)')
    
    # 应用滤镜
    if filters:
        cmd.extend(['-vf', ','.join(filters)])
    
    # 帧率设置
    framerate = settings.get('framerate', {})
    target_fps = framerate.get('target', 30)
    cmd.extend(['-r', str(target_fps)])
    
    # 抽帧设置
    frame_skip = settings.get('frameSkip', {})
    if frame_skip.get('enabled', False):
        skip_start = frame_skip.get('start', 25)
        skip_end = frame_skip.get('end', 30)
        # 简化抽帧实现：每N帧取一帧
        cmd.extend(['-vf', f'select=not(mod(n\\,{skip_start}))'])
    
    # 码率设置
    bitrate = settings.get('bitrate', {})
    if bitrate.get('mode') == 'fixed':
        fixed_bitrate = bitrate.get('fixed', 3000)
        cmd.extend(['-b:v', f'{fixed_bitrate}k'])
    else:
        # 倍率模式，使用默认码率的倍数
        multiplier = (bitrate.get('min', 1.05) + bitrate.get('max', 1.95)) / 2
        cmd.extend(['-q:v', str(int(28 / multiplier))])  # 反向计算质量参数
    
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
    return jsonify({
        "history": [dict(zip(['filename','upload_time','status','reason','url'], r)) for r in rows],
        "success": success,
        "fail": fail
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
        args=(videos, account_file, location, publish_date, upload_interval)
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

def batch_upload_thread(videos, account_file, location, publish_date, upload_interval=5):
    global is_uploading, upload_tasks
    
    # 确保upload_interval是一个合法的整数
    try:
        upload_interval = int(upload_interval)
        if upload_interval < 1:
            upload_interval = 1
    except:
        upload_interval = 5
    
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
                
                # 根据上传结果更新状态，避免状态不一致
                if upload_result:
                    # 更新状态为完成
                    for task in upload_tasks:
                        if task["path"] == video_path:
                            task["status"] = "上传成功"
                            break
                    douyin_logger.info(f"[+] 视频 {video_name} 上传成功")
                    # 写入历史（成功）
                    log_upload_history(os.path.basename(account_file), video_name, 'success', None, None)
                else:
                    # 如果上传失败
                    for task in upload_tasks:
                        if task["path"] == video_path:
                            task["status"] = "上传失败"
                            break
                    douyin_logger.error(f"[-] 视频 {video_name} 上传失败")
                    # 写入历史（失败）
                    log_upload_history(os.path.basename(account_file), video_name, 'fail', '上传失败', None)
                
                # 无论成功或失败，都从列表中移除当前视频，避免重复上传
                videos_to_upload.remove(video_path)
                print(f"[DEBUG] 已从上传列表移除视频: {video_name}, 剩余视频数量: {len(videos_to_upload)}")
                
                # 如果还有更多视频要上传，则等待指定的间隔时间
                if videos_to_upload:
                    # 确保间隔是整数
                    interval_mins = upload_interval
                    print(f"[DEBUG] 准备等待{interval_mins}分钟后上传下一个视频")
                    
                    # 更新等待状态
                    next_video = videos_to_upload[0]  # 获取下一个要上传的视频
                    next_video_name = os.path.basename(next_video)
                    for task in upload_tasks:
                        if task["path"] == next_video:
                            task["status"] = f"等待中 (将在{interval_mins}分钟后上传)"
                            break
                    
                    douyin_logger.info(f"[+] 等待{interval_mins}分钟后上传下一个视频: {next_video_name}")
                    # 每隔30秒更新一次状态，显示剩余等待时间
                    total_wait_seconds = interval_mins * 60
                    print(f"[DEBUG] 总等待时间: {total_wait_seconds}秒")
                    
                    for waited in range(0, total_wait_seconds, 30):
                        time.sleep(30)  # 等待30秒
                        remaining_mins = (total_wait_seconds - waited - 30) // 60
                        remaining_secs = (total_wait_seconds - waited - 30) % 60
                        
                        print(f"[DEBUG] 已等待{waited+30}秒, 剩余{remaining_mins}分{remaining_secs}秒")
                        
                        for task in upload_tasks:
                            if task["path"] == next_video:
                                task["status"] = f"等待中 (剩余{remaining_mins}分{remaining_secs}秒)"
                                break
            except Exception as e:
                # 更新状态为失败
                for task in upload_tasks:
                    if task["path"] == video_path:
                        task["status"] = f"失败: {str(e)[:20]}"
                        break
                # 写入历史（异常）
                log_upload_history(os.path.basename(account_file), video_name, 'fail', str(e), None)
                
                # 即使发生异常，也要从列表中移除当前视频，避免重复上传
                if video_path in videos_to_upload:
                    videos_to_upload.remove(video_path)
                    print(f"[DEBUG] 异常情况下移除视频: {video_name}, 剩余视频数量: {len(videos_to_upload)}")
    except Exception as e:
        print(f"批量上传过程中发生错误: {str(e)}")
    finally:
        loop.close()
        is_uploading = False
        
        # 确保所有任务都有最终状态
        for task in upload_tasks:
            if task["status"] not in ["上传成功", "上传失败"] and "失败:" not in task["status"]:
                # 如果任务状态还在进行中，标记为完成或失败
                if task["path"] not in videos_to_upload:
                    task["status"] = "上传成功"
                else:
                    task["status"] = "上传失败"
        
        print(f"[DEBUG] 批量上传任务结束，最终剩余视频数量: {len(videos_to_upload)}")
        if len(videos_to_upload) > 0:
            print(f"[WARNING] 还有未完成的视频: {[os.path.basename(v) for v in videos_to_upload]}")
        
        # 记录最终任务状态
        for task in upload_tasks:
            print(f"[DEBUG] 最终任务状态 - {task['name']}: {task['status']}")

async def async_upload(file_path, account_file, title, tags, location, publish_date, status_callback=None):
    full_path = os.path.join("videos", file_path)
    
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
                            elif event == "publish_start":
                                status_callback("开始发布...")
                            elif event == "publish_complete":
                                status_callback("发布完成")
                            else:
                                status_callback(message)
                
                # 添加状态处理器
                video.status_handler = StatusHandler()
                await video.upload(playwright, location=location)
                return True  # 返回上传成功
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
        screenshot_task = asyncio.create_task(capture_screenshots(page, session_id, interval=5))
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

async def capture_screenshots(page, session_id, interval=5):
    """捕获页面截图并通过WebSocket发送"""
    last_screenshot_hash = None
    try:
        while True:
            # 线程安全检查会话状态
            with browser_data_lock:
                if not active_browser_sessions.get(session_id, False):
                    break
                    
            try:
                # 截图（减小尺寸提升性能）
                screenshot = await safe_screenshot(
                    page,
                    full_page=False, 
                    type='png',
                    clip={'x': 0, 'y': 0, 'width': 1280, 'height': 720}  # 限制截图尺寸
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
    
    # 重置任务状态
    for task in multi_account_tasks:
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
    
    # 更新所有正在上传的任务状态
    for task in multi_account_tasks:
        if task["status"] == "uploading":
            update_task_status(task, "stopped", None, save_to_file=False)
    save_multi_tasks_to_file()  # 批量保存
    
    return jsonify({"success": True, "message": "多账号上传已停止"})

def multi_account_upload_thread(task):
    """单个账号的上传线程"""
    global is_multi_uploading
    
    try:
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
        for i, video_path in enumerate(task["videos"]):
            if not is_multi_uploading:  # 检查是否被停止
                task["status"] = "stopped"
                break
                
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
                        break  # 跳出循环，不再等待间隔
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
                if i < len(task["videos"]) - 1 and is_multi_uploading:
                    douyin_logger.info(f"账号 {task['cookie']} 视频间隔等待 {task['upload_interval']} 分钟")
                    # 更新状态为等待中
                    update_task_status(task, "waiting", f"等待 {task['upload_interval']} 分钟后上传下一个视频")
                    time.sleep(task["upload_interval"] * 60)
                    
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
            task["current_upload_index"] = 0
        
        # 持续轮询直到所有任务完成
        while is_multi_uploading and any(task["current_upload_index"] < len(task["videos"]) for task in valid_tasks):
            
            for task in valid_tasks:
                if not is_multi_uploading:
                    break
                
                # 如果该账号还有视频要上传
                if task["current_upload_index"] < len(task["videos"]):
                    current_task_index = task["id"]
                    
                    # 执行单个视频上传
                    video_index = task["current_upload_index"]
                    success = upload_single_video_for_task(task, video_index)
                    
                    # 更新上传索引
                    task["current_upload_index"] += 1
                    
                    # 账号间隔等待（轮询模式的核心）
                    # 只有在还有其他账号需要上传时才等待
                    if is_multi_uploading and any(t["current_upload_index"] < len(t["videos"]) for t in valid_tasks):
                        douyin_logger.info(f"账号 {task['cookie']} 上传完成，等待 {task['upload_interval']} 分钟后轮询下一个账号")
                        time.sleep(task["upload_interval"] * 60)
        
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
                    
                    # 逐个下载视频
                    for i, video in enumerate(videos):
                        download_url = None  # 为每个视频初始化download_url
                        try:
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
                            filename = f"{safe_title}_{aweme_id}.mp4"
                            filepath = os.path.join(downloads_dir, filename)
                            
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
                                    else:
                                        failed_videos.append({'video': title, 'reason': f'下载失败，状态码: {response.status_code}'})
                                        douyin_logger.warning(f"下载失败，状态码: {response.status_code}, URL: {download_url if 'download_url' in locals() else 'unknown'}")
                                except Exception as download_error:
                                    failed_videos.append({'video': title, 'reason': f'下载异常: {str(download_error)}'})
                                    douyin_logger.error(f"下载异常: {str(download_error)}")
                        
                        except Exception as e:
                            video_title = title if 'title' in locals() else f'视频_{i+1}'
                            failed_videos.append({'video': video_title, 'reason': str(e)})
                            douyin_logger.error(f"处理视频失败: {str(e)}")
                            douyin_logger.error(f"错误详情 - 视频: {video}, 变量状态: download_url={'已定义' if 'download_url' in locals() else '未定义'}")
                    
                    # 返回下载结果
                    result_message = f"下载完成！成功: {success_count}/{total_videos}"
                    if failed_videos:
                        result_message += f"，失败: {len(failed_videos)} 个"
                    
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
        
        # 在新线程中执行下载任务
        import threading
        result_container = {}
        
        def run_download():
            result_container['result'] = download_task()
        
        thread = threading.Thread(target=run_download)
        thread.start()
        thread.join(timeout=300)  # 5分钟超时
        
        if 'result' in result_container:
            result = result_container['result']
            return jsonify(result)
        else:
            return jsonify({'success': False, 'message': '下载超时'}), 408
            
    except Exception as e:
        douyin_logger.error(f"下载接口错误: {str(e)}")
        return jsonify({'success': False, 'message': f'接口错误: {str(e)}'}), 500

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