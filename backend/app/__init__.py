"""
Flask应用工厂
"""
import os
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_login import LoginManager
from config import config

# 导入扩展实例
from app.models.base import db
migrate = Migrate()
login_manager = LoginManager()

def create_app(config_name=None):
    """应用工厂函数"""
    if config_name is None:
        config_name = os.environ.get('FLASK_ENV') or 'default'
    
    app = Flask(__name__, 
                template_folder='../../frontend/templates',
                static_folder='../../frontend/static')
    
    # 应用配置
    app.config.from_object(config[config_name])
    config[config_name].init_app(app)
    
    # 初始化扩展
    db.init_app(app)
    migrate.init_app(app, db)
    
    # 配置登录管理器
    login_manager.init_app(app)
    login_manager.login_view = 'auth.login'
    login_manager.login_message = '请先登录以访问此页面。'
    login_manager.login_message_category = 'info'
    
    # 注册蓝图
    register_blueprints(app)
    
    # 注册错误处理器
    register_error_handlers(app)
    
    # 注册上下文处理器
    register_context_processors(app)
    
    return app

def register_blueprints(app):
    """注册蓝图"""
    # 认证蓝图
    from app.auth import auth_bp
    app.register_blueprint(auth_bp, url_prefix='/auth')
    
    # API蓝图
    from app.api import api_bp
    app.register_blueprint(api_bp, url_prefix='/api')
    
    # 管理蓝图
    from app.admin import admin_bp
    app.register_blueprint(admin_bp, url_prefix='/admin')
    
    # 主页蓝图
    from app.main import main_bp
    app.register_blueprint(main_bp)

def register_error_handlers(app):
    """注册错误处理器"""
    from flask import render_template, jsonify, request
    
    @app.errorhandler(404)
    def not_found_error(error):
        if request.path.startswith('/api/'):
            return jsonify({'error': 'Not found', 'code': 404}), 404
        return render_template('errors/404.html'), 404
    
    @app.errorhandler(500)
    def internal_error(error):
        db.session.rollback()
        if request.path.startswith('/api/'):
            return jsonify({'error': 'Internal server error', 'code': 500}), 500
        return render_template('errors/500.html'), 500
    
    @app.errorhandler(403)
    def forbidden_error(error):
        if request.path.startswith('/api/'):
            return jsonify({'error': 'Forbidden', 'code': 403}), 403
        return render_template('errors/403.html'), 403

def register_context_processors(app):
    """注册上下文处理器"""
    from flask_login import current_user
    
    @app.context_processor
    def inject_global_vars():
        return {
            'app_name': 'OpenStack运维管理平台',
            'version': '2.0.0'
        }

# 用户加载器
@login_manager.user_loader
def load_user(user_id):
    """Flask-Login用户加载回调"""
    from app.models.user import User
    return User.query.get(int(user_id))