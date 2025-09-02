# OpenStack运维管理平台 v2.0

一个基于Flask的运维集群统一管理平台，提供Web界面进行实例、卷、网络、快照等资源的集中管理。

## ✨ 主要特性

- 🌐 **多集群管理** - 统一管理多个OpenStack环境
- 👥 **用户权限** - 基于角色的访问控制(RBAC)
- 🔐 **安全加固** - 凭据加密存储，操作审计
- 📊 **资源监控** - 实时状态监控和资源统计
- 🔄 **批量操作** - 支持批量操作和导出功能
- 📱 **响应式UI** - 现代化Web界面，支持移动端

## 🚀 快速开始

### 环境要求

- Python 3.8+
- sqllite

### 1. 克隆项目

```bash
git clone <repository-url>
cd ops_sys
```

### 2. 后端设置

```bash
cd backend

# 创建虚拟环境
python -m venv venv

# 激活虚拟环境
# Windows
venv\\Scripts\\activate
# Linux/Mac
source venv/bin/activate

# 安装依赖
pip install -r requirements.txt
```

### 3. 配置环境

```bash
# 复制环境变量模板
cp .env.example .env


### 4. 初始化数据库

```bash
# 初始化数据库
python migrations/init_db.py

# 或者使用管理脚本
python manage.py init-db
```

### 5. 启动应用

```bash
# 开发环境
python app.py
```

访问 http://localhost:5001

### 6. 默认账户

- **管理员**: admin / admin123
- **操作员**: operator / operator123  
- **查看者**: viewer / viewer123

## 📁 项目结构

```
ops_sys/
├── backend/                    # 后端代码
│   ├── app/
│   │   ├── models/            # 数据模型
│   │   ├── api/               # API接口
│   │   ├── auth/              # 认证模块
│   │   ├── admin/             # 管理模块
│   │   ├── services/          # 业务服务
│   │   └── utils/             # 工具函数
│   ├── migrations/            # 数据库迁移
│   ├── config.py              # 配置文件
│   ├── requirements.txt       # Python依赖
│   └── run.py                 # 启动文件
├── frontend/                   # 前端代码
│   ├── static/                # 静态资源
│   └── templates/             # 页面模板
├── docs/                       # 文档
├── 功能需求文档.md             # 功能需求
└── 开发实施计划.md             # 开发计划
```

## 🛠️ 管理命令

使用管理脚本进行日常管理：

```bash
# 用户管理
python manage.py create-user        # 创建用户
python manage.py list-users         # 列出用户
python manage.py delete-user        # 删除用户

# 集群管理
python manage.py add-cluster        # 添加集群
python manage.py list-clusters      # 列出集群
python manage.py test-cluster       # 测试连接

# 数据库管理
python manage.py init-db            # 初始化数据库
python manage.py clear-logs         # 清除日志
```

## 🔧 开发指南

### 代码结构

- **模型层** (`app/models/`): 数据库模型定义
- **服务层** (`app/services/`): 业务逻辑实现  
- **API层** (`app/api/`): REST API接口
- **认证层** (`app/auth/`): 用户认证和权限
- **工具层** (`app/utils/`): 通用工具函数

### 添加新功能

1. 在 `models/` 中定义数据模型
2. 在 `services/` 中实现业务逻辑
3. 在 `api/` 中添加API接口
4. 在 `templates/` 中创建页面模板
5. 添加相应的测试用例

### 权限控制

使用装饰器进行权限控制：

```python
from app.auth.decorators import role_required

@role_required('admin')
def admin_only_function():
    pass

@role_required('operator')  
def operator_function():
    pass
```

## 📊 功能模块

- ✅ **用户管理** - 用户注册、认证、权限控制
- ✅ **集群管理** - OpenStack环境配置和连接管理
- ✅ **实例管理** - 虚拟机实例的创建、操作、监控
- ✅ **卷管理** - 存储卷的管理和快照功能
- 🚧 **网络管理** - 网络、子网、安全组管理
- 🚧 **快照管理** - 实例和卷快照管理
- 🚧 **SSH管理** - 服务器连接和在线终端
- 🚧 **监控仪表盘** - 资源监控和统计图表

## 🔒 安全特性

- **凭据加密**: OpenStack凭据使用对称加密存储
- **权限控制**: 基于角色的多级权限管理
- **操作审计**: 完整的操作日志记录
- **会话管理**: 安全的用户会话和超时控制
- **输入验证**: 严格的用户输入验证和清理

## 📈 性能优化

- **数据缓存**: Redis缓存OpenStack API响应
- **连接池**: 数据库连接池优化
- **分页加载**: 大数据集分页显示
- **异步操作**: 长时间操作异步处理

## 🐛 故障排除

### 常见问题

1. **数据库连接失败**
   - 检查MySQL服务状态
   - 确认数据库配置正确

2. **OpenStack连接失败**
   - 验证集群配置信息
   - 检查网络连接和防火墙

3. **权限错误**
   - 确认用户角色设置
   - 检查权限装饰器配置

### 日志查看

```bash
# 应用日志
tail -f logs/ops_sys.log

# 开发模式错误
# 查看控制台输出
```

## 🤝 贡献指南

1. Fork 项目
2. 创建功能分支 (`git checkout -b feature/AmazingFeature`)
3. 提交更改 (`git commit -m 'Add some AmazingFeature'`)
4. 推送到分支 (`git push origin feature/AmazingFeature`)
5. 打开 Pull Request

## 📄 许可证

本项目采用 MIT 许可证 - 查看 [LICENSE](LICENSE) 文件了解详情

## 📞 支持

- 📧 邮箱: support@example.com
- 📝 文档: [在线文档](https://docs.example.com)
- 🐛 问题反馈: [Issues](https://github.com/your-repo/issues)

---

🎉 感谢使用OpenStack运维管理平台！