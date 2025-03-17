# OpenStack 管理系统

这是一个基于Flask的OpenStack管理Web应用，提供了对OpenStack实例、卷、快照等资源的可视化管理和操作。

## 功能特性

- **实例管理**
  - 查看实例列表
  - 查看实例详情
  - 启动/停止实例
  - 删除实例

- **卷管理**
  - 查看卷列表
  - 创建/删除卷
  - 卷快照管理
  - 卷导出功能（支持Excel和CSV格式）

- **快照管理**
  - 创建/删除快照
  - 查看快照状态

- **安全管理**
  - 删除操作密码验证
  - JWT token验证
  - 操作日志记录

- **其他功能**
  - 多OpenStack环境支持
  - 数据缓存优化
  - 性能监控
  - 分页和排序功能

## 技术栈

- **后端**
  - Python 3.x
  - Flask
  - OpenStack SDK
  - JWT

- **前端**
  - Bootstrap 3
  - Font Awesome
  - jQuery

- **数据库**
  - SQLite（用于SSH连接管理）

## 项目结构
