import os
import hashlib
import sqlite3
from datetime import datetime
from utils.log import douyin_logger

class MD5Manager:
    def __init__(self, db_path='database/video_md5.db'):
        """初始化MD5管理器"""
        self.db_path = db_path
        self.init_db()
        
    def init_db(self):
        """初始化视频MD5数据库"""
        # 确保数据库目录存在
        db_dir = os.path.dirname(self.db_path)
        if db_dir and not os.path.exists(db_dir):
            os.makedirs(db_dir, exist_ok=True)
        
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        
        # 创建视频MD5记录表
        c.execute('''CREATE TABLE IF NOT EXISTS video_md5 (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            filename TEXT NOT NULL,
            filepath TEXT NOT NULL,
            md5 TEXT NOT NULL UNIQUE,
            filesize INTEGER NOT NULL,
            cookie_name TEXT,
            upload_time TEXT DEFAULT CURRENT_TIMESTAMP,
            title TEXT,
            tags TEXT
        )''')
        
        conn.commit()
        conn.close()
    
    def calculate_md5(self, file_path):
        """计算文件的MD5值"""
        if not os.path.exists(file_path):
            douyin_logger.error(f"文件不存在: {file_path}")
            return None
            
        try:
            md5_hash = hashlib.md5()
            with open(file_path, "rb") as f:
                # 对于大文件，分块读取
                for chunk in iter(lambda: f.read(4096), b""):
                    md5_hash.update(chunk)
            return md5_hash.hexdigest()
        except Exception as e:
            douyin_logger.error(f"计算MD5时出错: {str(e)}")
            return None
    
    def is_duplicate(self, file_path):
        """检查视频是否已经上传过（根据MD5值）"""
        md5_value = self.calculate_md5(file_path)
        if not md5_value:
            return False
            
        try:
            conn = sqlite3.connect(self.db_path)
            c = conn.cursor()
            
            c.execute('SELECT filename, upload_time, cookie_name, title FROM video_md5 WHERE md5 = ?', (md5_value,))
            result = c.fetchone()
            conn.close()
            
            if result:
                douyin_logger.warning(f"检测到重复视频: {os.path.basename(file_path)}")
                douyin_logger.warning(f"该视频已于 {result[1]} 使用账号 {result[2] or '未知'} 上传，标题为: {result[3] or '未知'}")
                return True
            return False
            
        except Exception as e:
            douyin_logger.error(f"检查重复视频时出错: {str(e)}")
            return False
    
    def record_md5(self, file_path, cookie_name=None, title=None, tags=None):
        """记录视频MD5到数据库"""
        md5_value = self.calculate_md5(file_path)
        if not md5_value:
            return False
            
        try:
            conn = sqlite3.connect(self.db_path)
            c = conn.cursor()
            
            filename = os.path.basename(file_path)
            filesize = os.path.getsize(file_path)
            
            # 尝试插入记录
            try:
                c.execute('''INSERT INTO video_md5 
                          (filename, filepath, md5, filesize, cookie_name, upload_time, title, tags)
                          VALUES (?, ?, ?, ?, ?, ?, ?, ?)''',
                         (filename, file_path, md5_value, filesize, cookie_name, 
                          datetime.now().strftime('%Y-%m-%d %H:%M:%S'), title, 
                          ','.join(tags) if tags else None))
                          
                conn.commit()
                douyin_logger.success(f"视频MD5记录成功: {filename} -> {md5_value}")
                success = True
            except sqlite3.IntegrityError:
                # MD5已存在
                douyin_logger.warning(f"视频MD5已存在: {filename} -> {md5_value}")
                conn.rollback()
                success = False
            
            conn.close()
            return success
            
        except Exception as e:
            douyin_logger.error(f"记录视频MD5时出错: {str(e)}")
            return False
    
    def get_md5_record(self, md5_value):
        """根据MD5值获取视频记录"""
        try:
            conn = sqlite3.connect(self.db_path)
            c = conn.cursor()
            
            c.execute('''SELECT id, filename, filepath, md5, filesize, cookie_name, upload_time, title, tags 
                         FROM video_md5 WHERE md5 = ?''', (md5_value,))
            result = c.fetchone()
            conn.close()
            
            if result:
                return {
                    'id': result[0],
                    'filename': result[1],
                    'filepath': result[2],
                    'md5': result[3],
                    'filesize': result[4],
                    'cookie_name': result[5],
                    'upload_time': result[6],
                    'title': result[7],
                    'tags': result[8].split(',') if result[8] else []
                }
            return None
            
        except Exception as e:
            douyin_logger.error(f"获取MD5记录时出错: {str(e)}")
            return None
    
    def get_all_records(self, limit=100, offset=0):
        """获取所有视频MD5记录"""
        try:
            conn = sqlite3.connect(self.db_path)
            c = conn.cursor()
            
            c.execute('''SELECT id, filename, md5, filesize, cookie_name, upload_time, title
                         FROM video_md5 ORDER BY upload_time DESC LIMIT ? OFFSET ?''', (limit, offset))
            records = []
            for row in c.fetchall():
                records.append({
                    'id': row[0],
                    'filename': row[1],
                    'md5': row[2],
                    'filesize': row[3],
                    'cookie_name': row[4],
                    'upload_time': row[5],
                    'title': row[6]
                })
            
            conn.close()
            return records
            
        except Exception as e:
            douyin_logger.error(f"获取MD5记录列表时出错: {str(e)}")
            return []
            
# 创建单例实例
md5_manager = MD5Manager() 