from flask import Flask
from routes.instances import instances_bp
from routes.volumes import volumes_bp
from routes.ssh import ssh_bp
from routes.snapshots import snapshots_bp
from flask_cors import CORS
from flask import render_template 
from routes.cloud import index_bp

# 注册蓝图
app = Flask(__name__)
CORS(app)  # 添加CORS支持
app.register_blueprint(instances_bp, url_prefix='/api/instances')
app.register_blueprint(volumes_bp, url_prefix='/api/volumes')
app.register_blueprint(ssh_bp, url_prefix='/api/ssh')
app.register_blueprint(snapshots_bp, url_prefix='/api/snapshots')
# 假设 index_bp 未定义，需要先导入
app.register_blueprint(index_bp, url_prefix='/api/cloud')  # 可以根据实际情况设置 url_prefix
# 添加index路由
@app.route('/')
def index():
    return render_template('index.html')

if __name__ == '__main__':
    app.run(host="0.0.0.0", port=5000, debug=True)