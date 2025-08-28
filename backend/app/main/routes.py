"""
主页路由
"""
from flask import render_template, redirect, url_for, jsonify
from flask_login import login_required, current_user
from app.models.user import User
from app.models.cluster import OpenstackCluster
from . import main_bp

@main_bp.route('/')
def index():
    """首页"""
    if current_user.is_authenticated:
        return redirect(url_for('main.dashboard'))
    return redirect(url_for('auth.login'))

@main_bp.route('/dashboard')
@login_required
def dashboard():
    """仪表盘"""
    # 获取统计数据
    stats = {
        'total_users': User.query.count(),
        'total_clusters': OpenstackCluster.query.count(),
        'active_clusters': OpenstackCluster.query.filter_by(is_active=True).count(),
        'user_role': current_user.role
    }
    
    # 获取最近的集群
    recent_clusters = OpenstackCluster.query.filter_by(is_active=True).limit(5).all()
    
    return render_template('dashboard/index.html', 
                         stats=stats, 
                         clusters=recent_clusters)

@main_bp.route('/clusters')
@login_required
def clusters():
    """集群管理页面"""
    return render_template('clusters/index.html')

@main_bp.route('/instances')
@login_required
def instances():
    """实例管理页面"""
    return render_template('instances/index.html')

@main_bp.route('/instances/create')
@login_required
def create_instance():
    """创建实例页面"""
    return render_template('instances/create.html')

@main_bp.route('/volumes')
@login_required
def volumes():
    """卷管理页面"""
    return render_template('volumes/index.html')

@main_bp.route('/networks')
@login_required
def networks():
    """网络管理页面"""
    return render_template('networks/index.html')

@main_bp.route('/network-topology')
@login_required
def network_topology():
    """网络拓扑页面"""
    return render_template('network_topology/index.html')

@main_bp.route('/routers')
@login_required
def routers():
    """路由管理页面"""
    return render_template('routers/index.html')

@main_bp.route('/security-groups')
@login_required
def security_groups():
    """安全组管理页面"""
    return render_template('security_groups/index.html')

@main_bp.route('/snapshots')
@login_required
def snapshots():
    """快照管理页面"""
    return render_template('snapshots/index.html')

@main_bp.route('/api/stats')
@login_required
def api_stats():
    """API统计信息"""
    stats = {
        'users': User.query.count(),
        'clusters': OpenstackCluster.query.count(),
        'active_clusters': OpenstackCluster.query.filter_by(is_active=True).count(),
        'current_user': {
            'username': current_user.username,
            'role': current_user.role,
            'login_count': current_user.login_count
        }
    }
    return jsonify(stats)