"""
认证表单 - 简化版，不使用Flask-WTF
"""

class LoginForm:
    """登录表单验证"""
    @staticmethod
    def validate_login_data(data):
        errors = {}
        
        if not data.get('username'):
            errors['username'] = '用户名不能为空'
        elif len(data.get('username', '')) < 3:
            errors['username'] = '用户名至少3个字符'
            
        if not data.get('password'):
            errors['password'] = '密码不能为空'
            
        return errors

class UserForm:
    """用户表单验证"""
    @staticmethod
    def validate_user_data(data, user_id=None):
        from app.models.user import User
        errors = {}
        
        # 验证用户名
        if not data.get('username'):
            errors['username'] = '用户名不能为空'
        elif len(data.get('username', '')) < 3:
            errors['username'] = '用户名至少3个字符'
        else:
            # 检查用户名是否已存在
            query = User.query.filter_by(username=data['username'])
            if user_id:
                query = query.filter(User.id != user_id)
            if query.first():
                errors['username'] = '用户名已存在'
        
        # 验证邮箱
        if not data.get('email'):
            errors['email'] = '邮箱不能为空'
        elif '@' not in data.get('email', ''):
            errors['email'] = '邮箱格式不正确'
        else:
            # 检查邮箱是否已存在
            query = User.query.filter_by(email=data['email'])
            if user_id:
                query = query.filter(User.id != user_id)
            if query.first():
                errors['email'] = '邮箱已被使用'
        
        # 验证密码（新建用户时必须）
        if not user_id and not data.get('password'):
            errors['password'] = '密码不能为空'
        elif data.get('password') and len(data.get('password', '')) < 6:
            errors['password'] = '密码至少6个字符'
        
        # 验证确认密码
        if data.get('password') and data.get('password') != data.get('confirm_password'):
            errors['confirm_password'] = '两次密码输入不一致'
            
        return errors

class ChangePasswordForm:
    """修改密码表单验证"""
    @staticmethod
    def validate_password_data(data):
        errors = {}
        
        if not data.get('current_password'):
            errors['current_password'] = '当前密码不能为空'
            
        if not data.get('new_password'):
            errors['new_password'] = '新密码不能为空'
        elif len(data.get('new_password', '')) < 6:
            errors['new_password'] = '新密码至少6个字符'
            
        if data.get('new_password') != data.get('confirm_password'):
            errors['confirm_password'] = '两次密码输入不一致'
            
        return errors