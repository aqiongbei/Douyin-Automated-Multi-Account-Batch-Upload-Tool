import sqlite3
import json
import random
import asyncio
import aiohttp
from datetime import datetime, timedelta
from utils.log import douyin_logger

class ProxyManager:
    def __init__(self, db_path='database/proxy_manager.db'):
        self.db_path = db_path
        self.init_db()
    
    def init_db(self):
        """初始化代理数据库"""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        
        # 代理表
        c.execute('''CREATE TABLE IF NOT EXISTS proxies (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            host TEXT NOT NULL,
            port INTEGER NOT NULL,
            username TEXT,
            password TEXT,
            protocol TEXT DEFAULT 'http',
            status TEXT DEFAULT 'active',
            last_check TEXT,
            speed_ms INTEGER DEFAULT 0,
            success_rate REAL DEFAULT 0.0,
            created_time TEXT DEFAULT CURRENT_TIMESTAMP
        )''')
        
        # Cookie-代理映射表
        c.execute('''CREATE TABLE IF NOT EXISTS cookie_proxy_mapping (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cookie_name TEXT UNIQUE NOT NULL,
            proxy_id INTEGER,
            assigned_time TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (proxy_id) REFERENCES proxies (id)
        )''')
        
        conn.commit()
        conn.close()
    
    def add_proxy(self, name, host, port, username=None, password=None, protocol='http'):
        """添加代理"""
        try:
            conn = sqlite3.connect(self.db_path)
            c = conn.cursor()
            
            c.execute('''INSERT INTO proxies 
                        (name, host, port, username, password, protocol) 
                        VALUES (?, ?, ?, ?, ?, ?)''',
                     (name, host, port, username, password, protocol))
            
            conn.commit()
            proxy_id = c.lastrowid
            conn.close()
            
            douyin_logger.info(f"添加代理成功: {name} ({host}:{port})")
            return True, proxy_id
            
        except sqlite3.IntegrityError:
            return False, "代理名称已存在"
        except Exception as e:
            douyin_logger.error(f"添加代理失败: {str(e)}")
            return False, str(e)
    
    def get_all_proxies(self):
        """获取所有代理"""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        
        c.execute('''SELECT id, name, host, port, username, password, protocol, 
                           status, last_check, speed_ms, success_rate, created_time 
                    FROM proxies ORDER BY created_time DESC''')
        
        proxies = []
        for row in c.fetchall():
            proxies.append({
                'id': row[0],
                'name': row[1],
                'host': row[2],
                'port': row[3],
                'username': row[4],
                'password': row[5],
                'protocol': row[6],
                'status': row[7],
                'last_check': row[8],
                'speed_ms': row[9],
                'success_rate': row[10],
                'created_time': row[11]
            })
        
        conn.close()
        return proxies
    
    def delete_proxy(self, proxy_id):
        """删除代理"""
        try:
            conn = sqlite3.connect(self.db_path)
            c = conn.cursor()
            
            # 先删除映射关系
            c.execute('DELETE FROM cookie_proxy_mapping WHERE proxy_id = ?', (proxy_id,))
            
            # 删除代理
            c.execute('DELETE FROM proxies WHERE id = ?', (proxy_id,))
            
            conn.commit()
            conn.close()
            
            douyin_logger.info(f"删除代理成功: ID {proxy_id}")
            return True, "删除成功"
            
        except Exception as e:
            douyin_logger.error(f"删除代理失败: {str(e)}")
            return False, str(e)
    
    async def test_proxy(self, proxy_info):
        """测试代理连接"""
        try:
            proxy_url = self._build_proxy_url(proxy_info)
            
            start_time = datetime.now()
            
            timeout = aiohttp.ClientTimeout(total=10)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(
                    'http://httpbin.org/ip', 
                    proxy=proxy_url
                ) as response:
                    if response.status == 200:
                        end_time = datetime.now()
                        speed_ms = int((end_time - start_time).total_seconds() * 1000)
                        
                        result = await response.json()
                        return True, speed_ms, result.get('origin', 'Unknown')
                    else:
                        return False, 0, f"HTTP {response.status}"
                        
        except Exception as e:
            return False, 0, str(e)
    
    def _build_proxy_url(self, proxy_info):
        """构建代理URL"""
        protocol = proxy_info.get('protocol', 'http')
        host = proxy_info['host']
        port = proxy_info['port']
        username = proxy_info.get('username')
        password = proxy_info.get('password')
        
        if username and password:
            return f"{protocol}://{username}:{password}@{host}:{port}"
        else:
            return f"{protocol}://{host}:{port}"
    
    async def check_proxy_status(self, proxy_id):
        """检查单个代理状态"""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        
        c.execute('SELECT * FROM proxies WHERE id = ?', (proxy_id,))
        row = c.fetchone()
        
        if not row:
            conn.close()
            return False, "代理不存在"
        
        proxy_info = {
            'host': row[2],
            'port': row[3], 
            'username': row[4],
            'password': row[5],
            'protocol': row[6]
        }
        
        success, speed_ms, ip_info = await self.test_proxy(proxy_info)
        
        # 更新状态
        status = 'active' if success else 'inactive'
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        c.execute('''UPDATE proxies 
                    SET status = ?, last_check = ?, speed_ms = ?
                    WHERE id = ?''',
                 (status, now, speed_ms, proxy_id))
        
        conn.commit()
        conn.close()
        
        return success, ip_info if success else "连接失败"
    
    def assign_proxy_to_cookie(self, cookie_name, proxy_id=None):
        """为cookie分配代理"""
        try:
            conn = sqlite3.connect(self.db_path)
            c = conn.cursor()
            
            if proxy_id is None:
                # 自动分配：选择活跃且负载最少的代理
                c.execute('''SELECT p.id, COUNT(cpm.cookie_name) as usage_count
                           FROM proxies p
                           LEFT JOIN cookie_proxy_mapping cpm ON p.id = cpm.proxy_id
                           WHERE p.status = 'active'
                           GROUP BY p.id
                           ORDER BY usage_count ASC, p.speed_ms ASC
                           LIMIT 1''')
                
                result = c.fetchone()
                if not result:
                    conn.close()
                    return False, "没有可用的活跃代理"
                
                proxy_id = result[0]
            
            # 检查代理是否存在且活跃
            c.execute('SELECT status FROM proxies WHERE id = ?', (proxy_id,))
            proxy_status = c.fetchone()
            
            if not proxy_status:
                conn.close()
                return False, "代理不存在"
            
            if proxy_status[0] != 'active':
                conn.close()
                return False, "代理不可用"
            
            # 更新或插入映射
            c.execute('''INSERT OR REPLACE INTO cookie_proxy_mapping 
                        (cookie_name, proxy_id, assigned_time)
                        VALUES (?, ?, ?)''',
                     (cookie_name, proxy_id, datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
            
            conn.commit()
            conn.close()
            
            douyin_logger.info(f"为Cookie {cookie_name} 分配代理 ID:{proxy_id}")
            return True, "分配成功"
            
        except Exception as e:
            douyin_logger.error(f"分配代理失败: {str(e)}")
            return False, str(e)
    
    def get_cookie_proxy(self, cookie_name):
        """获取cookie对应的代理"""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        
        c.execute('''SELECT p.* FROM proxies p
                    JOIN cookie_proxy_mapping cpm ON p.id = cpm.proxy_id
                    WHERE cpm.cookie_name = ? AND p.status = 'active' ''',
                 (cookie_name,))
        
        row = c.fetchone()
        conn.close()
        
        if not row:
            return None
        
        return {
            'id': row[0],
            'name': row[1],
            'host': row[2],
            'port': row[3],
            'username': row[4],
            'password': row[5],
            'protocol': row[6]
        }
    
    def get_proxy_for_playwright(self, cookie_name):
        """获取适用于playwright的代理配置"""
        proxy_info = self.get_cookie_proxy(cookie_name)
        
        if not proxy_info:
            return None
        
        config = {
            'server': f"{proxy_info['protocol']}://{proxy_info['host']}:{proxy_info['port']}"
        }
        
        if proxy_info['username'] and proxy_info['password']:
            config['username'] = proxy_info['username']
            config['password'] = proxy_info['password']
        
        return config
    
    def get_proxy_by_id(self, proxy_id):
        """根据代理ID获取代理信息"""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        
        c.execute('SELECT * FROM proxies WHERE id = ?', (proxy_id,))
        row = c.fetchone()
        conn.close()
        
        if not row:
            return None
        
        return {
            'id': row[0],
            'name': row[1],
            'host': row[2],
            'port': row[3],
            'username': row[4],
            'password': row[5],
            'protocol': row[6],
            'status': row[7]
        }
    
    def get_proxy_for_playwright_by_id(self, proxy_id):
        """根据代理ID获取适用于playwright的代理配置"""
        proxy_info = self.get_proxy_by_id(proxy_id)
        
        if not proxy_info:
            return None
        
        config = {
            'server': f"{proxy_info['protocol']}://{proxy_info['host']}:{proxy_info['port']}"
        }
        
        if proxy_info['username'] and proxy_info['password']:
            config['username'] = proxy_info['username']
            config['password'] = proxy_info['password']
        
        return config
    
    def get_cookie_proxy_mappings(self):
        """获取所有cookie-代理映射"""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        
        c.execute('''SELECT cpm.cookie_name, p.name as proxy_name, p.host, p.port, 
                           p.status, cpm.assigned_time
                    FROM cookie_proxy_mapping cpm
                    LEFT JOIN proxies p ON cpm.proxy_id = p.id
                    ORDER BY cpm.assigned_time DESC''')
        
        mappings = []
        for row in c.fetchall():
            mappings.append({
                'cookie_name': row[0],
                'proxy_name': row[1],
                'proxy_host': row[2],
                'proxy_port': row[3],
                'proxy_status': row[4],
                'assigned_time': row[5]
            })
        
        conn.close()
        return mappings
    
    def remove_cookie_proxy(self, cookie_name):
        """移除cookie的代理分配"""
        try:
            conn = sqlite3.connect(self.db_path)
            c = conn.cursor()
            
            c.execute('DELETE FROM cookie_proxy_mapping WHERE cookie_name = ?', (cookie_name,))
            
            conn.commit()
            conn.close()
            
            douyin_logger.info(f"移除Cookie {cookie_name} 的代理分配")
            return True, "移除成功"
            
        except Exception as e:
            douyin_logger.error(f"移除代理分配失败: {str(e)}")
            return False, str(e)

# 全局代理管理器实例
proxy_manager = ProxyManager() 