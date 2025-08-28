"""
项目管理脚本
提供数据库管理、用户管理等功能
"""
import os
import click
from flask.cli import with_appcontext
from app import create_app, db
from app.models import User, OpenstackCluster, OperationLog

@click.group()
def cli():
    """OpenStack运维平台管理工具"""
    pass

@cli.command()
@click.option('--env', default='development', help='Environment name')
def init_db(env):
    """初始化数据库"""
    app = create_app(env)
    with app.app_context():
        db.create_all()
        click.echo('✓ Database initialized')

@cli.command()
@click.option('--username', prompt=True, help='Username')
@click.option('--email', prompt=True, help='Email address')
@click.option('--password', prompt=True, hide_input=True, confirmation_prompt=True, help='Password')
@click.option('--role', type=click.Choice(['super_admin', 'admin', 'operator', 'viewer']), 
              default='viewer', help='User role')
@with_appcontext
def create_user(username, email, password, role):
    """创建用户"""
    existing_user = User.query.filter(
        (User.username == username) | (User.email == email)
    ).first()
    
    if existing_user:
        click.echo(f'✗ User with username "{username}" or email "{email}" already exists')
        return
    
    user = User(username=username, email=email, role=role)
    user.set_password(password)
    
    db.session.add(user)
    db.session.commit()
    
    click.echo(f'✓ User "{username}" created with role "{role}"')

@cli.command()
@click.option('--username', prompt=True, help='Username')
@with_appcontext
def delete_user(username):
    """删除用户"""
    user = User.query.filter_by(username=username).first()
    if not user:
        click.echo(f'✗ User "{username}" not found')
        return
    
    if click.confirm(f'Delete user "{username}"?'):
        db.session.delete(user)
        db.session.commit()
        click.echo(f'✓ User "{username}" deleted')

@cli.command()
@with_appcontext
def list_users():
    """列出所有用户"""
    users = User.query.all()
    
    click.echo(f'{"ID":<5} {"Username":<15} {"Email":<25} {"Role":<12} {"Active":<8}')
    click.echo('-' * 70)
    
    for user in users:
        click.echo(f'{user.id:<5} {user.username:<15} {user.email:<25} '
                  f'{user.role:<12} {"Yes" if user.is_active else "No":<8}')

@cli.command()
@click.option('--name', prompt=True, help='Cluster name')
@click.option('--auth-url', prompt=True, help='Keystone auth URL')
@click.option('--username', prompt=True, help='OpenStack username')
@click.option('--password', prompt=True, hide_input=True, help='OpenStack password')
@click.option('--project', prompt=True, help='OpenStack project name')
@with_appcontext
def add_cluster(name, auth_url, username, password, project):
    """添加OpenStack集群"""
    existing = OpenstackCluster.query.filter_by(name=name).first()
    if existing:
        click.echo(f'✗ Cluster "{name}" already exists')
        return
    
    cluster = OpenstackCluster(
        name=name,
        auth_url=auth_url,
        description=f'OpenStack集群 {name}'
    )
    
    credentials = {
        'username': username,
        'password': password,
        'project_name': project,
        'user_domain_name': 'Default',
        'project_domain_name': 'Default'
    }
    cluster.set_credentials(credentials)
    
    db.session.add(cluster)
    db.session.commit()
    
    click.echo(f'✓ Cluster "{name}" added')

@cli.command()
@with_appcontext
def list_clusters():
    """列出所有集群"""
    clusters = OpenstackCluster.query.all()
    
    click.echo(f'{"ID":<5} {"Name":<15} {"Auth URL":<40} {"Status":<12} {"Active":<8}')
    click.echo('-' * 85)
    
    for cluster in clusters:
        click.echo(f'{cluster.id:<5} {cluster.name:<15} {cluster.auth_url:<40} '
                  f'{cluster.connection_status:<12} {"Yes" if cluster.is_active else "No":<8}')

@cli.command()
@click.option('--cluster-id', type=int, prompt=True, help='Cluster ID')
@with_appcontext 
def test_cluster(cluster_id):
    """测试集群连接"""
    cluster = OpenstackCluster.query.get(cluster_id)
    if not cluster:
        click.echo(f'✗ Cluster with ID {cluster_id} not found')
        return
    
    click.echo(f'Testing connection to cluster "{cluster.name}"...')
    result = cluster.test_connection()
    
    if result['success']:
        click.echo('✓ Connection successful')
    else:
        click.echo(f'✗ Connection failed: {result["error"]}')

@cli.command()
@with_appcontext
def clear_logs():
    """清除操作日志"""
    if click.confirm('Clear all operation logs?'):
        count = OperationLog.query.count()
        OperationLog.query.delete()
        db.session.commit()
        click.echo(f'✓ Cleared {count} log entries')

if __name__ == '__main__':
    app = create_app()
    with app.app_context():
        cli()