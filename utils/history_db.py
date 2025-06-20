import sqlite3
import os
from datetime import datetime, timedelta

def init_db():
    # 确保数据库目录存在
    db_path = 'database/upload_history.db'
    db_dir = os.path.dirname(db_path)
    if db_dir and not os.path.exists(db_dir):
        os.makedirs(db_dir, exist_ok=True)
    
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS upload_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        cookie_name TEXT,
        filename TEXT,
        upload_time TEXT,
        status TEXT,
        reason TEXT,
        url TEXT
    )''')
    conn.commit()
    conn.close()

def log_upload_history(cookie_name, filename, status, reason=None, url=None):
    # 确保数据库目录存在
    db_path = 'database/upload_history.db'
    db_dir = os.path.dirname(db_path)
    if db_dir and not os.path.exists(db_dir):
        os.makedirs(db_dir, exist_ok=True)
    
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    c.execute('''INSERT INTO upload_history (cookie_name, filename, upload_time, status, reason, url)
                 VALUES (?, ?, ?, ?, ?, ?)''',
              (cookie_name, filename, datetime.now().strftime('%Y-%m-%d %H:%M:%S'), status, reason, url))
    conn.commit()
    conn.close()

def get_history(cookie=None):
    # 确保数据库目录存在
    db_path = 'database/upload_history.db'
    db_dir = os.path.dirname(db_path)
    if db_dir and not os.path.exists(db_dir):
        os.makedirs(db_dir, exist_ok=True)
    
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    if cookie:
        c.execute('SELECT filename, upload_time, status, reason, url FROM upload_history WHERE cookie_name=? ORDER BY upload_time DESC', (cookie,))
    else:
        c.execute('SELECT filename, upload_time, status, reason, url, cookie_name FROM upload_history ORDER BY upload_time DESC')
    rows = c.fetchall()
    conn.close()
    return rows

def get_upload_count_last_hour(cookie_name):
    # 确保数据库目录存在
    db_path = 'database/upload_history.db'
    db_dir = os.path.dirname(db_path)
    if db_dir and not os.path.exists(db_dir):
        os.makedirs(db_dir, exist_ok=True)
    
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    now = datetime.now()
    one_hour_ago = (now - timedelta(hours=1)).strftime('%Y-%m-%d %H:%M:%S')
    c.execute('SELECT COUNT(*) FROM upload_history WHERE cookie_name=? AND upload_time>?', (cookie_name, one_hour_ago))
    count = c.fetchone()[0]
    conn.close()
    return count 