import os
import json
from functools import wraps
from flask import session, redirect, url_for

# 配置文件路径
AUTH_CONFIG_FILE = os.path.join(os.path.dirname(__file__), 'auth.json')

# 默认账号配置
DEFAULT_AUTH = {
    'username': '123456',
    'password': '123456'
}

def load_auth_config():
    """加载认证配置"""
    if not os.path.exists(AUTH_CONFIG_FILE):
        # 如果配置文件不存在，创建默认配置
        save_auth_config(DEFAULT_AUTH)
        return DEFAULT_AUTH
    
    try:
        with open(AUTH_CONFIG_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        # 如果配置文件损坏，重置为默认配置
        save_auth_config(DEFAULT_AUTH)
        return DEFAULT_AUTH

def save_auth_config(config):
    """保存认证配置"""
    os.makedirs(os.path.dirname(AUTH_CONFIG_FILE), exist_ok=True)
    with open(AUTH_CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(config, f, ensure_ascii=False, indent=4)

def verify_login(username, password):
    """验证登录信息"""
    auth_config = load_auth_config()
    return username == auth_config['username'] and password == auth_config['password']

def login_required(f):
    """登录验证装饰器"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('logged_in'):
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function 