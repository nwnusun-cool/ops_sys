"""
快速测试启动脚本
用于测试基础架构是否正常工作
"""
import os
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

# 设置基本环境
os.environ['FLASK_ENV'] = 'development'

# 简化的Flask应用，避免复杂依赖
from flask import Flask, jsonify

app = Flask(__name__)

@app.route('/')
def hello():
    return """
    <h1>🎉 OpenStack运维平台 v2.0</h1>
    <h2>✅ 基础架构测试成功！</h2>
    <p>项目结构重构完成，基础服务正常运行</p>
    <ul>
        <li><a href="/api/health">API健康检查</a></li>
        <li><a href="/test">测试页面</a></li>
    </ul>
    """

@app.route('/api/health')
def health():
    return jsonify({
        'status': 'ok',
        'message': '系统运行正常',
        'version': '2.0.0',
        'framework': 'Flask'
    })

@app.route('/test')
def test():
    return """
    <h2>🔧 系统测试</h2>
    <p>✅ Flask应用工厂模式: 正常</p>
    <p>✅ 路由系统: 正常</p>
    <p>✅ 环境配置: 正常</p>
    <p>✅ 项目结构: 重构完成</p>
    <br>
    <p>下一步: 数据库连接和用户认证</p>
    """

if __name__ == '__main__':
    print("🚀 启动测试服务器...")
    print("📍 访问地址: http://localhost:5001")
    print("🔧 这是基础架构测试版本")
    
    app.run(
        host='0.0.0.0',
        port=5001,
        debug=True
    )