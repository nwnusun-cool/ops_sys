"""
认证路由
"""
from flask import render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_user, logout_user, login_required, current_user
from app.models.user import User
from app.models.base import db
from .forms import LoginForm, UserForm, ChangePasswordForm
from . import auth_bp

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    """用户登录"""
    if current_user.is_authenticated:
        return redirect(url_for('main.dashboard'))
    
    errors = {}
    form_data = {}
    
    if request.method == 'POST':
        form_data = request.form.to_dict()
        errors = LoginForm.validate_login_data(form_data)
        
        if not errors:
            user = User.query.filter_by(username=form_data['username']).first()
            
            if user and user.check_password(form_data['password']) and user.is_active:
                login_user(user, remember=form_data.get('remember_me'))
                user.update_last_login()
                
                # 获取登录前尝试访问的页面
                next_page = request.args.get('next')
                if not next_page or not next_page.startswith('/'):
                    next_page = url_for('main.dashboard')
                
                flash(f'欢迎回来，{user.username}！', 'success')
                return redirect(next_page)
            else:
                flash('用户名或密码错误，或账户已被禁用', 'error')
    
    return render_template('auth/login.html', errors=errors, form_data=form_data)

@auth_bp.route('/logout')
@login_required
def logout():
    """用户退出"""
    username = current_user.username
    logout_user()
    flash(f'{username} 已安全退出', 'info')
    return redirect(url_for('auth.login'))

@auth_bp.route('/profile')
@login_required
def profile():
    """用户资料"""
    return render_template('auth/profile.html', user=current_user)

@auth_bp.route('/change_password', methods=['GET', 'POST'])
@login_required
def change_password():
    """修改密码"""
    errors = {}
    form_data = {}
    
    if request.method == 'POST':
        form_data = request.form.to_dict()
        errors = ChangePasswordForm.validate_password_data(form_data)
        
        if not errors:
            if current_user.check_password(form_data['current_password']):
                current_user.set_password(form_data['new_password'])
                db.session.commit()
                flash('密码修改成功', 'success')
                return redirect(url_for('auth.profile'))
            else:
                flash('当前密码错误', 'error')
    
    return render_template('auth/change_password.html', errors=errors, form_data=form_data)