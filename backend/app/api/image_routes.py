"""
镜像管理API路由
"""
from flask import request, jsonify, send_file, current_app
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename
import os
import tempfile
from app.services.openstack_service import get_openstack_service
from . import api_bp
import logging

logger = logging.getLogger(__name__)

@api_bp.route('/images', methods=['GET'])
@login_required
def list_images():
    """获取镜像列表"""
    cluster_id = request.args.get('cluster_id', type=int)
    if not cluster_id:
        return jsonify({'success': False, 'error': '集群ID是必需的'}), 400
    
    # 过滤参数
    filters = {
        'status': request.args.get('status', '').strip(),
        'visibility': request.args.get('visibility', '').strip(),
        'name': request.args.get('name', '').strip(),
        'is_public': request.args.get('is_public', '').strip(),
        'container_format': request.args.get('container_format', '').strip(),
        'disk_format': request.args.get('disk_format', '').strip(),
        'min_disk': request.args.get('min_disk', type=int),
        'min_ram': request.args.get('min_ram', type=int),
        'page': request.args.get('page', 1, type=int),
        'per_page': min(request.args.get('per_page', 20, type=int), 100),
        'sort_by': request.args.get('sort_by', 'created_at'),
        'sort_order': request.args.get('sort_order', 'desc')
    }
    
    try:
        openstack_service = get_openstack_service()
        result = openstack_service.list_images(cluster_id, filters)
        
        return jsonify({
            'success': True,
            'data': result['data'],
            'total': result['total'],
            'page': result['page'],
            'per_page': result['per_page'],
            'total_pages': result['total_pages']
        })
        
    except Exception as e:
        logger.error(f"Failed to list images for cluster {cluster_id}: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@api_bp.route('/images/<image_id>', methods=['GET'])
@login_required
def get_image_detail(image_id):
    """获取镜像详细信息"""
    cluster_id = request.args.get('cluster_id', type=int)
    if not cluster_id:
        return jsonify({'success': False, 'error': '集群ID是必需的'}), 400
    
    try:
        openstack_service = get_openstack_service()
        image_detail = openstack_service.get_image_detail(cluster_id, image_id)
        
        if image_detail:
            return jsonify({'success': True, 'data': image_detail})
        else:
            return jsonify({'success': False, 'error': '镜像不存在'}), 404
            
    except Exception as e:
        logger.error(f"Failed to get image detail {image_id}: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@api_bp.route('/images', methods=['POST'])
@login_required
def create_image():
    """创建镜像（支持URL上传和文件上传）"""
    cluster_id = request.form.get('cluster_id', type=int)
    if not cluster_id:
        return jsonify({'success': False, 'error': '集群ID是必需的'}), 400
    
    # 获取镜像基本信息
    image_data = {
        'name': request.form.get('name', '').strip(),
        'description': request.form.get('description', '').strip(),
        'disk_format': request.form.get('disk_format', 'qcow2'),
        'container_format': request.form.get('container_format', 'bare'),
        'visibility': request.form.get('visibility', 'private'),
        'min_disk': request.form.get('min_disk', 0, type=int),
        'min_ram': request.form.get('min_ram', 0, type=int),
        'protected': request.form.get('protected', 'false').lower() == 'true',
        'tags': request.form.get('tags', '').strip().split(',') if request.form.get('tags', '').strip() else []
    }
    
    # 验证必需字段
    if not image_data['name']:
        return jsonify({'success': False, 'error': '镜像名称是必需的'}), 400
    
    upload_type = request.form.get('upload_type', 'url')  # url 或 file
    
    try:
        openstack_service = get_openstack_service()
        
        if upload_type == 'url':
            # URL上传
            image_url = request.form.get('image_url', '').strip()
            if not image_url:
                return jsonify({'success': False, 'error': '镜像URL是必需的'}), 400
                
            result = openstack_service.create_image_from_url(cluster_id, image_data, image_url)
            
        elif upload_type == 'file':
            # 文件上传
            if 'image_file' not in request.files:
                return jsonify({'success': False, 'error': '请选择镜像文件'}), 400
                
            file = request.files['image_file']
            if file.filename == '':
                return jsonify({'success': False, 'error': '请选择镜像文件'}), 400
                
            # 保存临时文件
            filename = secure_filename(file.filename)
            temp_dir = tempfile.gettempdir()
            temp_path = os.path.join(temp_dir, filename)
            file.save(temp_path)
            
            try:
                result = openstack_service.create_image_from_file(cluster_id, image_data, temp_path)
            finally:
                # 清理临时文件
                if os.path.exists(temp_path):
                    os.unlink(temp_path)
        else:
            return jsonify({'success': False, 'error': '不支持的上传类型'}), 400
            
        if result['success']:
            return jsonify({'success': True, 'data': result['data'], 'message': '镜像创建成功'})
        else:
            return jsonify({'success': False, 'error': result['error']}), 500
            
    except Exception as e:
        logger.error(f"Failed to create image: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@api_bp.route('/images/<image_id>', methods=['PUT'])
@login_required
def update_image(image_id):
    """更新镜像属性"""
    cluster_id = request.json.get('cluster_id')
    if not cluster_id:
        return jsonify({'success': False, 'error': '集群ID是必需的'}), 400
    
    # 可更新的属性
    update_data = {}
    allowed_fields = ['name', 'description', 'visibility', 'min_disk', 'min_ram', 'protected', 'tags']
    
    for field in allowed_fields:
        if field in request.json:
            update_data[field] = request.json[field]
    
    if not update_data:
        return jsonify({'success': False, 'error': '没有提供要更新的字段'}), 400
    
    try:
        openstack_service = get_openstack_service()
        success = openstack_service.update_image(cluster_id, image_id, update_data)
        
        if success:
            return jsonify({'success': True, 'message': '镜像更新成功'})
        else:
            return jsonify({'success': False, 'error': '镜像更新失败'}), 500
            
    except Exception as e:
        logger.error(f"Failed to update image {image_id}: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@api_bp.route('/images/<image_id>', methods=['DELETE'])
@login_required
def delete_image(image_id):
    """删除镜像"""
    cluster_id = request.json.get('cluster_id')
    if not cluster_id:
        return jsonify({'success': False, 'error': '集群ID是必需的'}), 400
    
    try:
        openstack_service = get_openstack_service()
        success = openstack_service.delete_image(cluster_id, image_id)
        
        if success:
            return jsonify({'success': True, 'message': '镜像删除成功'})
        else:
            return jsonify({'success': False, 'error': '镜像删除失败'}), 500
            
    except Exception as e:
        logger.error(f"Failed to delete image {image_id}: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@api_bp.route('/images/<image_id>/download', methods=['GET'])
@login_required
def download_image(image_id):
    """下载镜像文件"""
    cluster_id = request.args.get('cluster_id', type=int)
    if not cluster_id:
        return jsonify({'success': False, 'error': '集群ID是必需的'}), 400
    
    try:
        openstack_service = get_openstack_service()
        result = openstack_service.download_image(cluster_id, image_id)
        
        if result['success']:
            # 返回文件流
            return send_file(
                result['file_path'],
                as_attachment=True,
                download_name=result['filename'],
                mimetype='application/octet-stream'
            )
        else:
            return jsonify({'success': False, 'error': result['error']}), 500
            
    except Exception as e:
        logger.error(f"Failed to download image {image_id}: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@api_bp.route('/images/formats', methods=['GET'])
@login_required
def get_image_formats():
    """获取支持的镜像格式"""
    return jsonify({
        'success': True,
        'data': {
            'disk_formats': [
                {'value': 'qcow2', 'label': 'QCOW2 (推荐)'},
                {'value': 'raw', 'label': 'RAW'},
                {'value': 'vmdk', 'label': 'VMDK'},
                {'value': 'vhd', 'label': 'VHD'},
                {'value': 'vhdx', 'label': 'VHDX'},
                {'value': 'iso', 'label': 'ISO'},
                {'value': 'ami', 'label': 'AMI'},
                {'value': 'ari', 'label': 'ARI'},
                {'value': 'aki', 'label': 'AKI'}
            ],
            'container_formats': [
                {'value': 'bare', 'label': 'Bare (推荐)'},
                {'value': 'ovf', 'label': 'OVF'},
                {'value': 'ova', 'label': 'OVA'},
                {'value': 'ami', 'label': 'AMI'},
                {'value': 'ari', 'label': 'ARI'},
                {'value': 'aki', 'label': 'AKI'},
                {'value': 'docker', 'label': 'Docker'}
            ],
            'visibility_options': [
                {'value': 'private', 'label': '私有'},
                {'value': 'shared', 'label': '共享'},
                {'value': 'public', 'label': '公开'},
                {'value': 'community', 'label': '社区'}
            ]
        }
    })

@api_bp.route('/images/statistics', methods=['GET'])
@login_required
def get_image_statistics():
    """获取镜像统计信息"""
    cluster_id = request.args.get('cluster_id', type=int)
    if not cluster_id:
        return jsonify({'success': False, 'error': '集群ID是必需的'}), 400
    
    try:
        openstack_service = get_openstack_service()
        stats = openstack_service.get_image_statistics(cluster_id)
        
        return jsonify({'success': True, 'data': stats})
        
    except Exception as e:
        logger.error(f"Failed to get image statistics for cluster {cluster_id}: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500