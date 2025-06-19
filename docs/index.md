# 抖音上传工具 - 文档中心

欢迎来到抖音上传工具的文档中心！这里汇集了项目的所有文档和说明文件。

## 📚 文档列表

### 核心文档
- **[../README.md](../README.md)** - 项目主要说明文档（根目录）
  - 项目介绍和快速开始
  - 主要功能概览
  - 技术栈说明

### 安装和配置指南
- **[../INSTALLATION_GUIDE.md](../INSTALLATION_GUIDE.md)** - 详细安装指南
  - 环境要求和依赖安装
  - 详细的安装步骤
  - 常见问题解决

- **[../PROXY_COOKIE_GUIDE.md](../PROXY_COOKIE_GUIDE.md)** - 代理和Cookie配置指南
  - 代理服务器配置
  - Cookie管理和使用
  - 网络配置优化

- **[../FINGERPRINT_GUIDE.md](../FINGERPRINT_GUIDE.md)** - 浏览器指纹配置指南
  - 浏览器指纹原理
  - 反检测技术说明
  - 指纹管理和配置

### 技术文档
- **[database.md](database.md)** - 数据库文件说明
  - 数据库文件用途和结构
  - 各个数据库的生成者和管理模块
  - 数据库迁移和备份说明

### 配置文件
- **[../requirements.txt](../requirements.txt)** - Python依赖包列表
  - 项目所需的所有Python包及版本
  - 安装命令：`pip install -r requirements.txt`

## 📁 项目文档结构

```
douyin_up/
├── README.md                    # 项目主文档
├── INSTALLATION_GUIDE.md        # 安装指南
├── PROXY_COOKIE_GUIDE.md        # 代理Cookie指南
├── FINGERPRINT_GUIDE.md         # 浏览器指纹指南
├── requirements.txt             # 依赖包列表
├── docs/
│   ├── index.md                # 本文档索引文件
│   └── database.md             # 数据库说明文档
├── database/                   # 数据库文件夹
│   ├── upload_history.db       # 上传历史数据库
│   ├── fingerprint_manager.db  # 浏览器指纹数据库
│   └── proxy_manager.db        # 代理管理数据库
└── ...                        # 其他项目文件
```

## 🔍 最新功能更新

### 文件夹批量选择功能
- ✅ 右键点击文件夹可选择该文件夹所有视频
- ✅ 支持递归选择子文件夹中的视频
- ✅ 批量操作按钮（全选/清空选择）
- ✅ 智能去重和操作反馈

### 状态管理优化
- ✅ 修复上传完成后状态显示问题
- ✅ 改进前端状态同步机制
- ✅ 添加调试工具页面 `/test_status`

### 数据库组织优化
- ✅ 所有数据库文件移动到 `database/` 文件夹
- ✅ 自动创建数据库文件夹
- ✅ 更新所有代码中的数据库路径引用

## 🚀 快速导航

- 想快速开始使用？→ [../README.md](../README.md)
- 想详细安装配置？→ [../INSTALLATION_GUIDE.md](../INSTALLATION_GUIDE.md)
- 想了解数据库结构？→ [database.md](database.md)
- 想配置代理和Cookie？→ [../PROXY_COOKIE_GUIDE.md](../PROXY_COOKIE_GUIDE.md)
- 想了解浏览器指纹？→ [../FINGERPRINT_GUIDE.md](../FINGERPRINT_GUIDE.md)

## 📝 文档维护说明

1. **文档位置**: 主要文档在根目录，技术文档在 `docs/` 文件夹
2. **命名规范**: 使用大写字母和下划线（如 `INSTALLATION_GUIDE.md`）或小写连字符（如 `database.md`）
3. **更新规则**: 修改文档后请同时更新本索引文件
4. **格式要求**: 使用Markdown格式编写文档 