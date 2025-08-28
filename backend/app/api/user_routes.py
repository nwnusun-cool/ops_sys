"""
用户管理API路由
提供用户的CRUD操作和用户管理功能
"""
import logging
from datetime import datetime
from flask import request, jsonify, send_file
from flask_login import login_required, current_user
from werkzeug.security import generate_password_hash
from . import api_bp as api
from app.models.base import db
from app.models.user import User
from app.models.log import OperationLog

logger = logging.getLogger(__name__)

def super_admin_required(f):
    """超级管理员权限装饰器"""
    from functools import wraps
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.can_manage_users():
            return jsonify({'success': False, 'error': '权限不足，需要超级管理员权限'}), 403
        return f(*args, **kwargs)
    return decorated_function

@api.route('/users', methods=['GET'])
@login_required
@super_admin_required
def list_users():
    """获取用户列表"""
    try:
        # 获取查询参数
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 20, type=int)
        role = request.args.get('role')
        is_active = request.args.get('is_active')
        search = request.args.get('search', '').strip()
        sort_by = request.args.get('sort_by', 'created_at')
        sort_order = request.args.get('sort_order', 'desc')
        
        # 构建查询
        query = User.query
        
        # 角色过滤
        if role:
            query = query.filter_by(role=role)
        
        # 状态过滤
        if is_active is not None:
            active_filter = is_active.lower() in ['true', '1', 'yes']
            query = query.filter_by(is_active=active_filter)
        
        # 搜索过滤
        if search:
            query = query.filter(
                db.or_(
                    User.username.ilike(f'%{search}%'),
                    User.email.ilike(f'%{search}%')
                )
            )
        
        # 排序
        if hasattr(User, sort_by):
            if sort_order.lower() == 'desc':
                query = query.order_by(getattr(User, sort_by).desc())
            else:
                query = query.order_by(getattr(User, sort_by))
        
        # 分页
        pagination = query.paginate(
            page=page,
            per_page=per_page,
            error_out=False
        )
        
        users = pagination.items
        
        # 转换数据
        users_data = []
        for user in users:
            user_data = user.to_dict()
            # 添加额外信息
            user_data['operation_logs_count'] = user.operation_logs.count()
            users_data.append(user_data)
        
        # 统计信息
        total_users = User.query.count()
        active_users = User.query.filter_by(is_active=True).count()
        role_counts = {}
        for role_name in ['viewer', 'operator', 'admin', 'super_admin']:
            role_counts[role_name] = User.query.filter_by(role=role_name).count()
        
        return jsonify({
            'success': True,
            'data': users_data,
            'pagination': {
                'page': page,
                'per_page': per_page,
                'total': pagination.total,
                'pages': pagination.pages,
                'has_next': pagination.has_next,
                'has_prev': pagination.has_prev
            },
            'statistics': {
                'total_users': total_users,
                'active_users': active_users,
                'inactive_users': total_users - active_users,
                'role_counts': role_counts
            }
        })
        
    except Exception as e:
        logger.error(f"Failed to list users: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@api.route('/users/<int:user_id>', methods=['GET'])
@login_required
@super_admin_required
def get_user_detail(user_id):
    """获取用户详细信息"""
    try:
        user = User.query.get_or_404(user_id)
        
        user_data = user.to_dict()
        
        # 获取最近的操作日志
        recent_logs = user.operation_logs.order_by(
            OperationLog.created_at.desc()
        ).limit(10).all()
        
        user_data['recent_operations'] = [
            {
                'id': log.id,
                'operation_type': log.operation_type,
                'operation_object': f'{log.resource_type}:{log.resource_name}' if log.resource_type and log.resource_name else 'unknown',
                'result': log.result,
                'details': log.details,
                'created_at': log.created_at.isoformat() if log.created_at else None,
                'cluster_name': log.cluster.name if log.cluster else None
            }
            for log in recent_logs
        ]
        
        return jsonify({
            'success': True,
            'data': user_data
        })
        
    except Exception as e:
        logger.error(f"Failed to get user detail {user_id}: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@api.route('/users', methods=['POST'])
@login_required
@super_admin_required
def create_user():
    """创建用户"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': '缺少请求数据'}), 400
        
        # 验证必填字段
        required_fields = ['username', 'email', 'password', 'role']
        for field in required_fields:
            if not data.get(field):
                return jsonify({'success': False, 'error': f'缺少必填字段: {field}'}), 400
        
        # 验证角色
        valid_roles = ['viewer', 'operator', 'admin', 'super_admin']
        if data['role'] not in valid_roles:
            return jsonify({'success': False, 'error': f'无效的角色，必须是: {", ".join(valid_roles)}'}), 400
        
        # 检查用户名是否存在
        if User.query.filter_by(username=data['username']).first():
            return jsonify({'success': False, 'error': '用户名已存在'}), 400
        
        # 检查邮箱是否存在
        if User.query.filter_by(email=data['email']).first():
            return jsonify({'success': False, 'error': '邮箱已存在'}), 400
        
        # 创建用户
        user = User(
            username=data['username'],
            email=data['email'],
            role=data['role'],
            is_active=data.get('is_active', True)
        )
        user.set_password(data['password'])
        
        db.session.add(user)
        db.session.commit()
        
        # 记录操作日志
        OperationLog.log_operation(
            user_id=current_user.id,
            operation_type='user_create',
            operation_object=f'user:{user.username}',
            result='success',
            details=f'创建用户: {user.username}, 角色: {user.role}'
        )
        
        logger.info(f"User {user.username} created by {current_user.username}")
        
        return jsonify({
            'success': True,
            'message': f'用户 {user.username} 创建成功',
            'data': user.to_dict()
        })
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Failed to create user: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@api.route('/users/<int:user_id>', methods=['PUT'])
@login_required
@super_admin_required
def update_user(user_id):
    """更新用户信息"""
    try:
        user = User.query.get_or_404(user_id)
        data = request.get_json()
        
        if not data:
            return jsonify({'success': False, 'error': '缺少请求数据'}), 400
        
        # 防止修改自己的角色
        if user.id == current_user.id and 'role' in data:
            return jsonify({'success': False, 'error': '不能修改自己的角色'}), 400
        
        changes = []
        
        # 更新用户名
        if 'username' in data and data['username'] != user.username:
            if User.query.filter_by(username=data['username']).filter(User.id != user_id).first():
                return jsonify({'success': False, 'error': '用户名已存在'}), 400
            changes.append(f"用户名: {user.username} -> {data['username']}")
            user.username = data['username']
        
        # 更新邮箱
        if 'email' in data and data['email'] != user.email:
            if User.query.filter_by(email=data['email']).filter(User.id != user_id).first():
                return jsonify({'success': False, 'error': '邮箱已存在'}), 400
            changes.append(f"邮箱: {user.email} -> {data['email']}")
            user.email = data['email']
        
        # 更新角色
        if 'role' in data and data['role'] != user.role:
            valid_roles = ['viewer', 'operator', 'admin', 'super_admin']
            if data['role'] not in valid_roles:
                return jsonify({'success': False, 'error': f'无效的角色，必须是: {", ".join(valid_roles)}'}), 400
            changes.append(f"角色: {user.role} -> {data['role']}")
            user.role = data['role']
        
        # 更新状态
        if 'is_active' in data and data['is_active'] != user.is_active:
            # 防止禁用自己
            if user.id == current_user.id and not data['is_active']:
                return jsonify({'success': False, 'error': '不能禁用自己的账户'}), 400
            changes.append(f"状态: {'启用' if user.is_active else '禁用'} -> {'启用' if data['is_active'] else '禁用'}")
            user.is_active = data['is_active']
        
        # 更新密码
        if 'password' in data and data['password']:
            user.set_password(data['password'])
            changes.append("密码已更新")
        
        if changes:
            user.updated_at = datetime.utcnow()
            db.session.commit()
            
            # 记录操作日志
            OperationLog.log_operation(
                user_id=current_user.id,
                operation_type='user_update',
                operation_object=f'user:{user.username}',
                result='success',
                details=f'更新用户信息: {", ".join(changes)}'
            )
            
            logger.info(f"User {user.username} updated by {current_user.username}: {changes}")
        
        return jsonify({
            'success': True,
            'message': f'用户 {user.username} 更新成功',
            'data': user.to_dict(),
            'changes': changes
        })
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Failed to update user {user_id}: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@api.route('/users/<int:user_id>', methods=['DELETE'])
@login_required
@super_admin_required
def delete_user(user_id):
    """删除用户"""
    try:
        user = User.query.get_or_404(user_id)
        
        # 防止删除自己
        if user.id == current_user.id:
            return jsonify({'success': False, 'error': '不能删除自己的账户'}), 400
        
        # 防止删除最后一个超级管理员
        if user.role == 'super_admin':
            super_admin_count = User.query.filter_by(role='super_admin', is_active=True).count()
            if super_admin_count <= 1:
                return jsonify({'success': False, 'error': '不能删除最后一个超级管理员'}), 400
        
        username = user.username
        
        # 记录操作日志（在删除前记录）
        OperationLog.log_operation(
            user_id=current_user.id,
            operation_type='user_delete',
            operation_object=f'user:{username}',
            result='success',
            details=f'删除用户: {username}, 角色: {user.role}'
        )
        
        db.session.delete(user)
        db.session.commit()
        
        logger.info(f"User {username} deleted by {current_user.username}")
        
        return jsonify({
            'success': True,
            'message': f'用户 {username} 删除成功'
        })
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Failed to delete user {user_id}: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@api.route('/users/batch-action', methods=['POST'])
@login_required
@super_admin_required
def batch_user_action():
    """批量用户操作"""
    try:
        data = request.get_json()
        
        if not data or not data.get('user_ids') or not data.get('action'):
            return jsonify({'success': False, 'error': '缺少必要参数'}), 400
        
        user_ids = data['user_ids']
        action = data['action']
        
        # 验证操作类型
        if action not in ['delete', 'enable', 'disable', 'change_role']:
            return jsonify({'success': False, 'error': '不支持的操作类型'}), 400
        
        results = []
        success_count = 0
        
        for user_id in user_ids:
            try:
                user = User.query.get(user_id)
                if not user:
                    results.append({
                        'user_id': user_id,
                        'username': f'用户ID:{user_id}',
                        'success': False,
                        'message': '用户不存在',
                        'error': '用户不存在'
                    })
                    continue
                
                # 防止对自己执行操作
                if user.id == current_user.id:
                    results.append({
                        'user_id': user_id,
                        'username': user.username,
                        'success': False,
                        'message': '不能对自己执行此操作',
                        'error': '不能对自己执行此操作'
                    })
                    continue
                
                success = False
                message = ""
                
                if action == 'delete':
                    # 防止删除最后一个超级管理员
                    if user.role == 'super_admin':
                        super_admin_count = User.query.filter_by(role='super_admin', is_active=True).count()
                        if super_admin_count <= 1:
                            message = '不能删除最后一个超级管理员'
                        else:
                            db.session.delete(user)
                            success = True
                            message = '删除成功'
                    else:
                        db.session.delete(user)
                        success = True
                        message = '删除成功'
                        
                elif action == 'enable':
                    user.is_active = True
                    success = True
                    message = '启用成功'
                    
                elif action == 'disable':
                    user.is_active = False
                    success = True
                    message = '禁用成功'
                    
                elif action == 'change_role':
                    new_role = data.get('new_role')
                    if not new_role:
                        message = '缺少新角色参数'
                    elif new_role not in ['viewer', 'operator', 'admin', 'super_admin']:
                        message = '无效的角色'
                    else:
                        user.role = new_role
                        success = True
                        message = f'角色更改为 {new_role} 成功'
                
                if success:
                    success_count += 1
                    # 记录成功日志
                    OperationLog.log_operation(
                        user_id=current_user.id,
                        operation_type=f'user_batch_{action}',
                        operation_object=f'user:{user.username}',
                        result='success',
                        details=f'批量{action}用户: {user.username}'
                    )
                
                results.append({
                    'user_id': user_id,
                    'username': user.username,
                    'success': success,
                    'message': message if success else '操作失败',
                    'error': None if success else message
                })
                
            except Exception as e:
                results.append({
                    'user_id': user_id,
                    'username': f'用户ID:{user_id}',
                    'success': False,
                    'message': '操作失败',
                    'error': str(e)
                })
        
        # 提交所有更改
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': f'批量{action}操作完成，成功: {success_count}/{len(user_ids)}',
            'data': {
                'total_count': len(user_ids),
                'success_count': success_count,
                'results': results
            }
        })
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Batch user action failed: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@api.route('/users/export', methods=['POST'])
@login_required
@super_admin_required
def export_users():
    """导出用户数据到Excel"""
    try:
        import pandas as pd
        from io import BytesIO
        
        data = request.get_json()
        export_all = data.get('export_all', True)
        user_ids = data.get('user_ids', [])
        filters = data.get('filters', {})
        
        # 获取用户列表
        if export_all:
            query = User.query
            # 应用过滤条件
            if filters.get('role'):
                query = query.filter_by(role=filters['role'])
            if filters.get('is_active') is not None:
                active_filter = filters['is_active']
                query = query.filter_by(is_active=active_filter)
            if filters.get('search'):
                search = filters['search']
                query = query.filter(
                    db.or_(
                        User.username.ilike(f'%{search}%'),
                        User.email.ilike(f'%{search}%')
                    )
                )
            users = query.all()
        else:
            users = User.query.filter(User.id.in_(user_ids)).all()
        
        if not users:
            return jsonify({'success': False, 'error': '没有找到要导出的用户'}), 400
        
        # 准备Excel数据
        excel_data = []
        for user in users:
            excel_data.append({
                'ID': user.id,
                '用户名': user.username,
                '邮箱': user.email,
                '角色': {
                    'viewer': '查看者',
                    'operator': '操作员',
                    'admin': '管理员',
                    'super_admin': '超级管理员'
                }.get(user.role, user.role),
                '状态': '启用' if user.is_active else '禁用',
                '登录次数': user.login_count,
                '最后登录': user.last_login.strftime('%Y-%m-%d %H:%M:%S') if user.last_login else '从未登录',
                '创建时间': user.created_at.strftime('%Y-%m-%d %H:%M:%S') if user.created_at else '',
                '更新时间': user.updated_at.strftime('%Y-%m-%d %H:%M:%S') if user.updated_at else '',
                '操作记录数': user.operation_logs.count()
            })
        
        # 创建DataFrame
        df = pd.DataFrame(excel_data)
        
        # 创建Excel文件
        output = BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, sheet_name='用户列表', index=False)
            
            # 设置列宽
            worksheet = writer.sheets['用户列表']
            for column in worksheet.columns:
                max_length = 0
                column_letter = column[0].column_letter
                for cell in column:
                    try:
                        if len(str(cell.value)) > max_length:
                            max_length = len(str(cell.value))
                    except:
                        pass
                adjusted_width = min(max_length + 2, 50)
                worksheet.column_dimensions[column_letter].width = adjusted_width
        
        output.seek(0)
        
        # 生成文件名
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f'users_{timestamp}.xlsx'
        
        # 记录操作日志
        OperationLog.log_operation(
            user_id=current_user.id,
            operation_type='user_export',
            operation_object='users:export',
            result='success',
            details=f'导出用户数据: {len(excel_data)}个用户'
        )
        
        return send_file(
            BytesIO(output.getvalue()),
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
            download_name=filename
        )
        
    except Exception as e:
        logger.error(f"User export failed: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@api.route('/users/statistics', methods=['GET'])
@login_required
@super_admin_required
def get_user_statistics():
    """获取用户统计信息"""
    try:
        from sqlalchemy import func
        from datetime import datetime, timedelta
        
        # 基础统计
        total_users = User.query.count()
        active_users = User.query.filter_by(is_active=True).count()
        
        # 角色统计
        role_stats = db.session.query(
            User.role, 
            func.count(User.id).label('count')
        ).group_by(User.role).all()
        
        role_counts = {role: count for role, count in role_stats}
        
        # 最近登录统计（最近30天）
        thirty_days_ago = datetime.utcnow() - timedelta(days=30)
        recent_logins = User.query.filter(
            User.last_login >= thirty_days_ago
        ).count()
        
        # 新用户统计（最近7天）
        seven_days_ago = datetime.utcnow() - timedelta(days=7)
        new_users = User.query.filter(
            User.created_at >= seven_days_ago
        ).count()
        
        # 每日登录统计（最近7天）
        daily_logins = []
        for i in range(7):
            day_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=i)
            day_end = day_start + timedelta(days=1)
            
            logins = User.query.filter(
                User.last_login >= day_start,
                User.last_login < day_end
            ).count()
            
            daily_logins.append({
                'date': day_start.strftime('%Y-%m-%d'),
                'logins': logins
            })
        
        return jsonify({
            'success': True,
            'data': {
                'total_users': total_users,
                'active_users': active_users,
                'inactive_users': total_users - active_users,
                'role_counts': role_counts,
                'recent_logins_30d': recent_logins,
                'new_users_7d': new_users,
                'daily_logins': list(reversed(daily_logins))
            }
        })
        
    except Exception as e:
        logger.error(f"Failed to get user statistics: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500