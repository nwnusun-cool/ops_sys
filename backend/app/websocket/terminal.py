"""
WebSocket终端处理器
处理Pod exec终端连接
"""
import logging
import threading
import time
from flask import request
from flask_socketio import emit, disconnect
from flask_login import current_user
from kubernetes.stream import stream
from kubernetes.client.rest import ApiException
from app.services.k8s_service import get_k8s_service
from app.models.k8s_cluster import K8sCluster

logger = logging.getLogger(__name__)

class PodTerminalHandler:
    """Pod终端WebSocket处理器"""
    
    def __init__(self, socketio):
        self.socketio = socketio
        self.active_sessions = {}  # {session_id: {'stream': stream, 'thread': thread}}
        
        # 注册WebSocket事件
        self.register_events()
    
    def register_events(self):
        """注册WebSocket事件"""
        @self.socketio.on('pod_terminal_connect')
        def on_terminal_connect(data):
            self.handle_connect(data)
        
        @self.socketio.on('pod_terminal_input') 
        def on_terminal_input(data):
            self.handle_input(data)
            
        @self.socketio.on('pod_terminal_resize')
        def on_terminal_resize(data):
            self.handle_resize(data)
            
        @self.socketio.on('pod_terminal_disconnect')
        def on_terminal_disconnect(data):
            self.handle_disconnect(data)
            
        @self.socketio.on('disconnect')
        def on_disconnect():
            self.handle_client_disconnect()
    
    def handle_connect(self, data):
        """处理终端连接请求"""
        try:
            logger.info(f"收到终端连接请求: {data}")
            
            # 验证用户登录
            if not current_user.is_authenticated:
                logger.warning("未认证的用户尝试连接终端")
                emit('pod_terminal_error', {'error': 'Not authenticated'})
                disconnect()
                return
            
            # 获取连接参数
            cluster_id = data.get('cluster_id')
            namespace = data.get('namespace') 
            pod_name = data.get('pod_name')
            container = data.get('container')
            
            if not all([cluster_id, namespace, pod_name]):
                emit('pod_terminal_error', {'error': 'Missing required parameters'})
                return
            
            # 验证集群存在
            cluster = K8sCluster.query.get(cluster_id)
            if not cluster:
                emit('pod_terminal_error', {'error': 'Cluster not found'})
                return
            
            logger.info(f"Creating terminal session for {namespace}/{pod_name} in cluster {cluster_id}")
            
            # 创建exec流
            session_id = request.sid
            self.create_terminal_session(session_id, cluster_id, namespace, pod_name, container)
            
        except Exception as e:
            logger.error(f"Failed to handle terminal connect: {str(e)}")
            emit('pod_terminal_error', {'error': str(e)})
    
    def create_terminal_session(self, session_id, cluster_id, namespace, pod_name, container):
        """创建终端会话"""
        try:
            k8s_service = get_k8s_service()
            
            # 准备exec流
            exec_stream = k8s_service.create_pod_exec_ws_stream(
                cluster_id, namespace, pod_name, container
            )
            
            # 存储会话信息
            self.active_sessions[session_id] = {
                'stream': exec_stream,
                'cluster_id': cluster_id,
                'namespace': namespace,
                'pod_name': pod_name,
                'container': container,
                'thread': None
            }
            
            # 发送连接成功信号
            emit('pod_terminal_connected', {
                'session_id': session_id,
                'pod_name': pod_name,
                'container': container
            })
            
            logger.info(f"Terminal session {session_id} created successfully")
            
            # 启动输出读取线程
            output_thread = threading.Thread(
                target=self.read_output_loop,
                args=(session_id, exec_stream),
                daemon=True
            )
            output_thread.start()
            self.active_sessions[session_id]['thread'] = output_thread
            
        except Exception as e:
            logger.error(f"Failed to create terminal session: {str(e)}")
            emit('pod_terminal_error', {'error': str(e)})
            if session_id in self.active_sessions:
                del self.active_sessions[session_id]
    
    def read_output_loop(self, session_id, exec_stream):
        """读取命令输出的循环"""
        try:
            logger.info(f"开始读取输出循环: session_id={session_id}")
            while session_id in self.active_sessions:
                try:
                    # 检查是否有可读数据
                    if exec_stream.is_open():
                        # 从stdout读取
                        if exec_stream.peek_stdout():
                            output = exec_stream.read_stdout()
                            if output:
                                logger.debug(f"收到stdout输出: {len(output)} 字节")
                                self.socketio.emit('pod_terminal_output', {
                                    'data': output
                                }, room=session_id)
                        
                        # 从stderr读取
                        if exec_stream.peek_stderr():
                            error_output = exec_stream.read_stderr()
                            if error_output:
                                logger.debug(f"收到stderr输出: {len(error_output)} 字节")
                                self.socketio.emit('pod_terminal_output', {
                                    'data': error_output
                                }, room=session_id)
                        
                        # 短暂休眠避免CPU占用过高
                        time.sleep(0.01)
                    else:
                        logger.info(f"Exec流已关闭: session_id={session_id}")
                        break
                except Exception as read_error:
                    logger.error(f"读取输出时出错: {str(read_error)}")
                    time.sleep(0.1)  # 出错时稍长的休眠
            
        except Exception as e:
            logger.error(f"Error in output reading loop for session {session_id}: {str(e)}")
            self.socketio.emit('pod_terminal_error', {
                'error': f'Connection lost: {str(e)}'
            }, room=session_id)
        finally:
            # 清理会话
            if session_id in self.active_sessions:
                self.cleanup_session(session_id)
    
    def handle_input(self, data):
        """处理终端输入"""
        try:
            session_id = request.sid
            if session_id not in self.active_sessions:
                emit('pod_terminal_error', {'error': 'Terminal session not found'})
                return
            
            input_data = data.get('data', '')
            session = self.active_sessions[session_id]
            exec_stream = session['stream']
            
            # 发送输入到Pod
            if exec_stream.is_open():
                exec_stream.write_stdin(input_data)
            else:
                emit('pod_terminal_error', {'error': 'Terminal session closed'})
                
        except Exception as e:
            logger.error(f"Failed to handle terminal input: {str(e)}")
            emit('pod_terminal_error', {'error': str(e)})
    
    def handle_resize(self, data):
        """处理终端窗口大小调整"""
        try:
            session_id = request.sid
            if session_id not in self.active_sessions:
                return
            
            rows = data.get('rows', 24)
            cols = data.get('cols', 80)
            
            # Kubernetes exec API不直接支持resize
            # 这里可以记录大小，但实际resize需要在创建时设置
            logger.debug(f"Terminal resize request: {cols}x{rows}")
            
        except Exception as e:
            logger.error(f"Failed to handle terminal resize: {str(e)}")
    
    def handle_disconnect(self, data):
        """处理终端断开连接"""
        session_id = request.sid
        self.cleanup_session(session_id)
    
    def handle_client_disconnect(self):
        """处理客户端断开连接"""
        session_id = request.sid
        self.cleanup_session(session_id)
    
    def cleanup_session(self, session_id):
        """清理终端会话"""
        try:
            if session_id in self.active_sessions:
                session = self.active_sessions[session_id]
                
                # 关闭exec流
                if session['stream']:
                    try:
                        session['stream'].close()
                    except Exception as e:
                        logger.warning(f"Error closing stream: {str(e)}")
                
                # 停止线程（线程应该会自动退出）
                if session['thread'] and session['thread'].is_alive():
                    # 线程会在流关闭后自动退出
                    pass
                
                # 删除会话记录
                del self.active_sessions[session_id]
                
                logger.info(f"Terminal session {session_id} cleaned up")
                
        except Exception as e:
            logger.error(f"Error cleaning up session {session_id}: {str(e)}")