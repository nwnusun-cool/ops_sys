"""
管理路由
"""
from flask import render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from app.models.user import User
from app.models.cluster import OpenstackCluster
from app.models.base import db
from . import admin_bp

def admin_required(f):
    """管理员权限装饰器"""
    from functools import wraps
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.can_manage_clusters():
            flash('您没有权限访问此页面', 'error')
            return redirect(url_for('main.dashboard'))
        return f(*args, **kwargs)
    return decorated_function

@admin_bp.route('/')
@login_required
@admin_required
def dashboard():
    """管理后台首页"""
    return redirect(url_for('main.dashboard'))

@admin_bp.route('/users')
@login_required
def users():
    """用户管理"""
    if not current_user.can_manage_users():
        flash('您没有权限管理用户', 'error')
        return redirect(url_for('main.dashboard'))
    
    users = User.query.all()
    return render_template('admin/users.html', users=users)

@admin_bp.route('/clusters')
@login_required
@admin_required  
def clusters():
    """集群管理"""
    clusters = OpenstackCluster.query.all()
    return render_template('admin/clusters.html', clusters=clusters)

@admin_bp.route('/api/clusters/<int:cluster_id>/test', methods=['POST'])
@login_required
@admin_required
def test_cluster_connection(cluster_id):
    """测试集群连接"""
    cluster = OpenstackCluster.query.get_or_404(cluster_id)
    
    try:
        result = cluster.test_connection()
        return jsonify(result)
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500