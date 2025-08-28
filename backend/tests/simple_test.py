"""
最简化测试 - 直接硬编码SQLite
"""
import os

# 直接设置SQLite
os.environ['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///test.db'

from flask import Flask
from flask_sqlalchemy import SQLAlchemy

app = Flask(__name__)
app.config['SECRET_KEY'] = 'test-key'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///test.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

class TestUser(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50))

@app.route('/')
def home():
    return """
    <h1>✅ SQLite连接测试成功</h1>
    <p>数据库: SQLite</p>
    <p>配置: test.db</p>
    <a href="/test">测试数据库操作</a>
    """

@app.route('/test')
def test_db():
    try:
        # 创建表
        db.create_all()
        
        # 测试插入
        user = TestUser(name='test')
        db.session.add(user)
        db.session.commit()
        
        # 测试查询
        users = TestUser.query.all()
        
        return f"✅ 数据库操作成功！用户数量: {len(users)}"
    except Exception as e:
        return f"❌ 数据库操作失败: {e}"

if __name__ == '__main__':
    print("🧪 SQLite连接测试...")
    app.run(debug=True, port=5002)