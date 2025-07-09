from flask import Flask, request, jsonify, render_template, send_file
from keystoneauth1.identity import v3
from keystoneauth1 import session
from novaclient import client as nova_client
from datetime import datetime, timedelta
import pytz
import re
import logging
import pandas as pd
import io
import yaml
from functools import wraps
from pathlib import Path
import jwt
import time
from werkzeug.utils import secure_filename
from cinderclient import client as cinder_client
import asyncio
import threading
import paramiko
import os
from src.ssh.ssh_manager import SSHManager
from src.models.ssh_model import Database, SSHConnection
import websockets
from concurrent.futures import ThreadPoolExecutor
import functools
from openstack import exceptions as openstack_exceptions

# 初始化 Flask 应用
app = Flask(__name__)

# 配置日志
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# 加载配置文件
# 获取当前脚本所在的目录
base_dir = os.path.dirname(os.path.abspath(__file__))
config_path = os.path.join(base_dir, "config", "config.json")

with open(config_path, "r") as f:
    config = yaml.safe_load(f)

CLOUDS = config["openstack_environments"]
SECURITY = config.get(
    "security",
    {"delete_password": "2524354300", "delete_password_expires": 3600},
)
app.config["SECRET_KEY"] = config.get("security", {}).get(
    "secret_key", "your-default-secret-key-here"
)
CORRECT_PASSWORD = config.get("page_password", None)
if not CORRECT_PASSWORD:
    raise ValueError("Page password is not set in the configuration file.")

# 创建线程池
executor = ThreadPoolExecutor(max_workers=3)


def error_handler(f):
    """错误处理装饰器"""

    @wraps(f)
    def decorated_function(*args, **kwargs):
        try:
            return f(*args, **kwargs)
        except ValueError as e:
            logger.warning(f"Value Error: {str(e)}")
            return jsonify({"status": "error", "message": str(e)}), 400
        except Exception as e:
            logger.error(f"Unexpected Error: {str(e)}", exc_info=True)
            return jsonify({"status": "error", "message": str(e)}), 500

    return decorated_function


class OpenstackManager:
    def __init__(self):
        self.sessions = {}
        self.nova_clients = {}
        self.cinder_clients = {}  # 添加 cinder 客户端
        self._init_clients()
        self.instance_cache = {}
        self.volume_cache = {}  # 添加卷缓存
        self.cache_timeout = timedelta(minutes=5)
        self.last_cache_update = {}

    def _init_clients(self):
        """初始化所有环境的客户端"""
        logger.info("Initializing OpenStack clients...")
        for cloud_name, cloud_config in CLOUDS.items():
            try:
                auth = v3.Password(**cloud_config)
                self.sessions[cloud_name] = session.Session(auth=auth)
                self.nova_clients[cloud_name] = nova_client.Client(
                    2, session=self.sessions[cloud_name]
                )
                self.cinder_clients[cloud_name] = cinder_client.Client(
                    3, session=self.sessions[cloud_name]
                )
                logger.info(f"✓ {cloud_name} connected successfully")
            except Exception as e:
                logger.error(f"✗ {cloud_name} connection failed: {str(e)}")

    def _get_cached_instances(self, cloud_name):
        """获取缓存的实例数据，如果过期则重新获取"""
        current_time = datetime.now()
        if (
                cloud_name not in self.instance_cache
                or current_time - self.last_cache_update.get(cloud_name, datetime.min)
                > self.cache_timeout
        ):
            self.instance_cache[cloud_name] = self._fetch_instances(cloud_name)
            self.last_cache_update[cloud_name] = current_time
        return self.instance_cache[cloud_name]

    def _fetch_instances(self, cloud_name):
        """从 OpenStack 获取实例数据"""
        instances = self.nova_clients[cloud_name].servers.list(detailed=True)
        return [
            self._format_instance_data(instance, cloud_name) for instance in instances
        ]

    def _get_cached_volumes(self, cloud_name):
        """获取缓存的卷数据"""
        current_time = datetime.now()
        if (
                cloud_name not in self.volume_cache
                or current_time
                - self.last_cache_update.get(f"{cloud_name}_volumes", datetime.min)
                > self.cache_timeout
        ):
            self.volume_cache[cloud_name] = self._fetch_volumes(cloud_name)
            self.last_cache_update[f"{cloud_name}_volumes"] = current_time
        return self.volume_cache[cloud_name]

    def _fetch_volumes(self, cloud_name):
        """从 OpenStack 获取卷数据"""
        volumes = self.cinder_clients[cloud_name].volumes.list(detailed=True)
        return [self._format_volume_data(volume, cloud_name) for volume in volumes]

    def clean_string(self, value):
        """清理字符串，确保中文字符正确显示"""
        if isinstance(value, str):
            ansi_escape = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")
            value = ansi_escape.sub("", value)
            try:
                value = value.encode("latin1").decode("utf-8")
            except (UnicodeEncodeError, UnicodeDecodeError):
                pass
        return value

    def _format_instance_data(self, instance, cloud_name):
        """格式化实例数据"""
        networks = instance.addresses
        ip_addresses = []
        for network_name, addresses in networks.items():
            for addr in addresses:
                ip_type = (
                    "float" if addr.get("OS-EXT-IPS:type") == "floating" else "fixed"
                )
                ip_addresses.append(f"{addr['addr']}({ip_type})")

        flavor = self._get_flavor_info(instance, cloud_name)

        return {
            "cloud": cloud_name,
            "name": self.clean_string(instance.name),
            "id": instance.id,
            "status": instance.status,
            "ip_addresses": ", ".join(ip_addresses) if ip_addresses else "N/A",
            "flavor": self.clean_string(flavor),
            "created": self._format_datetime(instance.created),
            "updated": self._format_datetime(instance.updated),
            "metadata": instance.metadata,
            "security_groups": [sg["name"] for sg in instance.security_groups],
            "power_state": self._get_power_state(instance),
        }

    def _get_flavor_info(self, instance, cloud_name):
        """获取实例配置信息"""
        try:
            flavor_id = instance.flavor["id"]
            flavor = self.nova_clients[cloud_name].flavors.get(flavor_id)
            return (
                f"{flavor.name} ({flavor.vcpus}vCPU, "
                f"{flavor.ram}MB RAM, {flavor.disk}GB Disk)"
            )
        except Exception as e:
            logger.warning(f"Failed to get flavor info: {str(e)}")
            return "Unknown"

    def _format_datetime(self, dt_str):
        """格式化日期时间为本地时间"""
        try:
            dt = datetime.strptime(dt_str, "%Y-%m-%dT%H:%M:%SZ")
            local_tz = pytz.timezone("Asia/Shanghai")
            dt = pytz.utc.localize(dt).astimezone(local_tz)
            return dt.strftime("%Y-%m-%d %H:%M:%S")
        except Exception:
            return dt_str

    def _get_power_state(self, instance):
        """获取实例电源状态"""
        power_states = {
            0: "NOSTATE",
            1: "RUNNING",
            3: "PAUSED",
            4: "SHUTDOWN",
            6: "CRASHED",
            7: "SUSPENDED",
        }
        return power_states.get(
            getattr(instance, "OS-EXT-STS:power_state", 0), "UNKNOWN"
        )

    def search_instances(self, cloud_name, filters=None):
        """
        搜索实例
        """
        if cloud_name not in self.nova_clients:
            raise ValueError(f"Unknown cloud environment: {cloud_name}")

        instances = self._get_cached_instances(cloud_name)
        filtered_instances = self._apply_filters(instances, filters)

        # 排序
        if filters and "sort_by" in filters:
            reverse = filters.get("sort_order", "desc").lower() == "desc"
            filtered_instances.sort(
                key=lambda x: str(x.get(filters["sort_by"], "")), reverse=reverse
            )

        # 分页
        page = int(filters.get("page", 1)) if filters else 1
        per_page = int(filters.get("per_page", 10)) if filters else 10
        start_idx = (page - 1) * per_page
        end_idx = start_idx + per_page

        return {
            "total": len(filtered_instances),
            "page": page,
            "per_page": per_page,
            "total_pages": (len(filtered_instances) + per_page - 1) // per_page,
            "data": filtered_instances[start_idx:end_idx],
        }

    def _apply_filters(self, instances, filters):
        """应用过滤条件"""
        if not filters:
            return instances

        filtered = instances

        # 状态过滤
        if "status" in filters and filters["status"]:
            logger.info(f"Filtering by status: {filters['status']}")  # 添加日志
            filtered = [
                i
                for i in filtered
                if i["status"] and i["status"].upper() == filters["status"].upper()
            ]

        # 实例类型过滤
        if "instance_type" in filters and filters["instance_type"]:
            logger.info(
                f"Filtering by instance type: {filters['instance_type']}"
            )  # 添加日志
            filtered = [
                i
                for i in filtered
                if i["flavor"]
                   and filters["instance_type"].lower() in i["flavor"].lower()
            ]

        # IP地址过滤
        if "ip" in filters and filters["ip"]:
            logger.info(f"Filtering by IP: {filters['ip']}")  # 添加日志
            filtered = [
                i
                for i in filtered
                if i["ip_addresses"] and filters["ip"] in i["ip_addresses"]
            ]

        # 创建日期过滤
        if "created_date" in filters and filters["created_date"]:
            logger.info(
                f"Filtering by created date: {filters['created_date']}"
            )  # 添加日志
            filter_date = datetime.strptime(filters["created_date"], "%Y-%m-%d").date()
            filtered = [
                i
                for i in filtered
                if i["created"]
                   and datetime.strptime(i["created"][:10], "%Y-%m-%d").date()
                   == filter_date
            ]

        # 名称搜索
        if "name" in filters and filters["name"]:
            logger.info(f"Filtering by name: {filters['name']}")  # 添加日志
            filtered = [
                i
                for i in filtered
                if i["name"] and filters["name"].lower() in i["name"].lower()
            ]

        logger.info(f"Filter result count: {len(filtered)}")  # 添加日志
        return filtered

    def get_instance_details(self, cloud_name, instance_id):
        """获取实例详细信息"""
        try:
            instance = self.nova_clients[cloud_name].servers.get(instance_id)
            return self._format_instance_data(instance, cloud_name)
        except Exception as e:
            logger.error(f"Failed to get instance details: {str(e)}")
            raise

    def perform_action(self, cloud_name, instance_id, action):
        """执行实例操作"""
        actions = {
            "start": ("启动", lambda i: i.start()),
            "stop": ("停止", lambda i: i.stop()),
            "reboot": ("重启", lambda i: i.reboot(reboot_type="SOFT")),
            "hard_reboot": ("强制重启", lambda i: i.reboot(reboot_type="HARD")),
            "pause": ("暂停", lambda i: i.pause()),
            "unpause": ("恢复", lambda i: i.unpause()),
            "lock": ("锁定", lambda i: i.lock()),
            "unlock": ("解锁", lambda i: i.unlock()),
            "delete": ("删除", lambda i: i.delete()),
        }

        if action not in actions:
            raise ValueError(f"Unsupported action: {action}")

        try:
            instance = self.nova_clients[cloud_name].servers.get(instance_id)
            action_name, action_func = actions[action]
            logger.info(f"Performing {action_name} on instance {instance.name}")
            action_func(instance)

            # 清除缓存
            if cloud_name in self.instance_cache:
                del self.instance_cache[cloud_name]

            return f"实例{action_name}操作已执行"
        except Exception as e:
            logger.error(f"Failed to perform action: {str(e)}")
            raise

    def export_instances(self, cloud_name, filters=None, format="excel"):
        """导出实例数据"""
        instances = self._get_cached_instances(cloud_name)
        if filters:
            instances = self._apply_filters(instances, filters)

        df = pd.DataFrame(instances)

        if format == "excel":
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine="openpyxl") as writer:
                df.to_excel(writer, index=False, sheet_name="Instances")
            output.seek(0)
            return output
        elif format == "csv":
            output = io.StringIO()
            df.to_csv(output, index=False)
            return output.getvalue()
        else:
            raise ValueError(f"Unsupported export format: {format}")

    def _format_volume_data(self, volume, cloud_name):
        """格式化卷数据"""
        try:
            attachments = volume.attachments
            attached_instances = []
            for attachment in attachments:
                try:
                    instance = self.nova_clients[cloud_name].servers.get(
                        attachment["server_id"]
                    )
                    attached_instances.append(
                        {
                            "instance_id": attachment["server_id"],
                            "instance_name": instance.name,
                            "device": attachment["device"],
                        }
                    )
                except Exception:
                    attached_instances.append(
                        {
                            "instance_id": attachment["server_id"],
                            "instance_name": "Unknown",
                            "device": attachment["device"],
                        }
                    )

            # 处理卷名称，确保非空
            volume_name = volume.name if volume.name else volume.id
            # 如果名称是 None 或空字符串，使用卷ID
            if not volume_name or volume_name.strip() == "":
                volume_name = f"volume-{volume.id[:8]}"

            return {
                "cloud": cloud_name,
                "id": volume.id,
                "name": volume_name,  # 使用处理后的名称
                "size": volume.size,
                "status": volume.status,
                "type": getattr(volume, "volume_type", "-"),
                "attachments": attached_instances,
                "bootable": volume.bootable,
                "encrypted": getattr(volume, "encrypted", False),
                "created_at": (
                    self._format_datetime(volume.created_at)
                    if hasattr(volume, "created_at")
                    else "-"
                ),
                "availability_zone": getattr(volume, "availability_zone", "-"),
            }
        except Exception as e:
            logger.error(f"Error formatting volume data: {str(e)}")
            # 返回一个基本的数据结构，确保至少显示卷ID
            return {
                "cloud": cloud_name,
                "id": volume.id,
                "name": f"volume-{volume.id[:8]}",
                "size": getattr(volume, "size", "-"),
                "status": getattr(volume, "status", "unknown"),
                "type": getattr(volume, "volume_type", "-"),
                "attachments": [],
                "bootable": getattr(volume, "bootable", "false"),
                "encrypted": getattr(volume, "encrypted", False),
                "created_at": "-",
                "availability_zone": "-",
            }

    def search_volumes(self, cloud_name, filters=None):
        """搜索卷"""
        if cloud_name not in self.cinder_clients:
            raise ValueError(f"Unknown cloud environment: {cloud_name}")

        volumes = self._get_cached_volumes(cloud_name)
        logger.info(f"========{volumes}=====")
        filtered_volumes = self._apply_volume_filters(volumes, filters)

        # 排序
        if filters and "sort_by" in filters:
            reverse = filters.get("sort_order", "desc").lower() == "desc"
            filtered_volumes.sort(
                key=lambda x: str(x.get(filters["sort_by"], "")), reverse=reverse
            )

        # 分页
        page = int(filters.get("page", 1)) if filters else 1
        per_page = int(filters.get("per_page", 10)) if filters else 10
        start_idx = (page - 1) * per_page
        end_idx = start_idx + per_page

        return {
            "total": len(filtered_volumes),
            "page": page,
            "per_page": per_page,
            "total_pages": (len(filtered_volumes) + per_page - 1) // per_page,
            "data": filtered_volumes[start_idx:end_idx],
        }

    def _apply_volume_filters(self, volumes, filters):
        """应用卷过滤条件"""
        if not filters:
            return volumes

        filtered = volumes

        # 名称过滤
        if "name" in filters and filters["name"]:
            filtered = [
                v
                for v in filtered
                if v["name"] and filters["name"].lower() in v["name"].lower()
            ]

        # 状态过滤
        if "status" in filters and filters["status"]:
            filtered = [v for v in filtered if v["status"] == filters["status"]]

        # 大小过滤
        if "size" in filters and filters["size"]:
            try:
                size = int(filters["size"])
                filtered = [v for v in filtered if v["size"] == size]
            except ValueError:
                pass

        # 类型过滤
        if "type" in filters and filters["type"]:
            filtered = [v for v in filtered if v["type"] == filters["type"]]

        return filtered

    def get_volume_details(self, cloud_name, volume_id):
        """获取卷详情"""
        try:
            volume = self.cinder_clients[cloud_name].volumes.get(volume_id)
            return self._format_volume_data(volume, cloud_name)
        except Exception as e:
            logger.error(f"Failed to get volume details: {str(e)}")
            raise

    def perform_volume_action(self, cloud_name, volume_id, action, **kwargs):
        """执行卷操作"""
        try:
            volume = self.cinder_clients[cloud_name].volumes.get(volume_id)

            if action == "delete":
                # 检查卷是否被挂载
                if volume.status == "in-use":
                    raise ValueError("无法删除已挂载的卷，请先卸载")
                volume.delete()
                message = "卷删除操作已执行"
            elif action == "extend":
                new_size = kwargs.get("new_size")
                if not new_size:
                    raise ValueError("未指定新的卷大小")
                volume.extend(volume, new_size)
                message = f"卷大小调整为 {new_size}GB"
            else:
                raise ValueError(f"不支持的操作: {action}")

            # 清除缓存
            if cloud_name in self.volume_cache:
                del self.volume_cache[cloud_name]

            return message
        except Exception as e:
            logger.error(f"Failed to perform volume action: {str(e)}")
            raise

    def export_volumes(self, cloud_name, filters=None, format="excel"):
        """导出卷数据"""
        try:
            volumes = self._get_cached_volumes(cloud_name)
            if filters:
                volumes = self._apply_volume_filters(volumes, filters)

            # 将卷数据转换为 DataFrame
            df = pd.DataFrame(volumes)

            # 处理附件信息
            if "attachments" in df.columns:
                df["attachments"] = df["attachments"].apply(
                    lambda x: ", ".join([f"{a['instance_name']}({a['device']})" for a in x])
                    if x
                    else "N/A"
                )

            if format == "excel":
                output = io.BytesIO()
                with pd.ExcelWriter(output, engine="openpyxl") as writer:
                    df.to_excel(writer, index=False, sheet_name="Volumes")
                output.seek(0)
                return output
            elif format == "csv":
                output = io.StringIO()
                df.to_csv(output, index=False)
                return output.getvalue()
            else:
                raise ValueError(f"Unsupported export format: {format}")
        except Exception as e:
            logger.error(f"Failed to export volumes: {str(e)}")
            raise

    def extend_volume(self, cloud_name, volume_id, new_size):
        """扩容卷"""
        try:
            volume = self.cinder_clients[cloud_name].volumes.get(volume_id)
            if volume.status != "available":
                raise ValueError("卷必须处于可用状态才能扩容")

            if new_size <= volume.size:
                raise ValueError("新的大小必须大于当前大小")

            # 执行扩容操作
            self.cinder_clients[cloud_name].volumes.extend(volume, new_size)

            # 清除缓存
            if cloud_name in self.volume_cache:
                del self.volume_cache[cloud_name]

            return f"卷 {volume_id} 已成功扩容到 {new_size}GB"
        except Exception as e:
            logger.error(f"Failed to extend volume: {str(e)}")
            raise

    def _wait_for_snapshot_status(self, cloud_name, snapshot_id, target_status, timeout=300):
        """
        等待快照状态变为目标状态
        :param cloud_name: 云环境名称
        :param snapshot_id: 快照 ID
        :param target_status: 目标状态（如 'available'）
        :param timeout: 超时时间（秒）
        :return: 快照对象
        """
        import time
        start_time = time.time()
        cinder_client = self.cinder_clients.get(cloud_name)

        while time.time() - start_time < timeout:
            snapshot = cinder_client.volume_snapshots.get(snapshot_id)
            if snapshot.status == target_status:
                return snapshot
            elif snapshot.status == 'error':
                raise Exception(f"快照 {snapshot_id} 进入错误状态")
            time.sleep(5)  # 每 5 秒检查一次状态

        raise Exception(f"快照 {snapshot_id} 未在 {timeout} 秒内变为 {target_status} 状态")

    def create_snapshot(self, cloud_name, volume_id, name, description):
        """
        创建卷快照
        :param cloud_name: 云环境名称
        :param volume_id: 卷 ID
        :param name: 快照名称
        :param description: 快照描述
        :return: 快照对象或 None（如果创建失败）
        """
        try:
            # 获取对应云环境的 cinder 客户端
            cinder_client = self.cinder_clients.get(cloud_name)
            if not cinder_client:
                logger.error(f"未找到云环境 {cloud_name} 的 cinder 客户端")
                return None

            # 调用 OpenStack API 创建快照
            snapshot = cinder_client.volume_snapshots.create(
                volume_id=volume_id,
                name=name,
                description=description,
                force=False  # True 如果卷处于挂载状态，强制创建快照
            )

            # 等待快照创建完成
            snapshot = self._wait_for_snapshot_status(cloud_name, snapshot.id, 'available')
            if snapshot.status == 'available':
                logger.info(f"快照创建成功: {snapshot.id}")
                return snapshot.to_dict()  # 将 Snapshot 对象转换为字典
            else:
                logger.error(f"快照创建失败，状态为: {snapshot.status}")
                return None

        except openstack_exceptions.ResourceNotFound:
            logger.error(f"卷 {volume_id} 不存在")
            return None
        except openstack_exceptions.ConflictException as e:
            logger.error(f"卷 {volume_id} 处于不可用状态: {str(e)}")
            return None
        except Exception as e:
            logger.error(f"创建快照时发生错误: {str(e)}")
            return None

    def get_snapshots(self, cloud_name, volume_id):
        # 这里实现调用 OpenStack API 获取快照列表的逻辑
        # 例如：
        # snapshots = openstack_client.get_volume_snapshots(volume_id)
        # return snapshots
        pass

    def delete_snapshot(self, cloud_name, snapshot_id):
        # 这里实现调用 OpenStack API 删除快照的逻辑
        # 例如：
        # openstack_client.delete_volume_snapshot(snapshot_id)
        pass

    def wait_for_instance_status(self, cloud_name, instance_id, target_status, timeout=300):
        """等待实例达到目标状态"""
        start_time = time.time()
        nova = manager.nova_clients.get(cloud_name)

        while time.time() - start_time < timeout:
            instance = nova.servers.get(instance_id)
            if instance.status == target_status:
                return instance
            elif instance.status == "ERROR":
                raise Exception(f"实例 {instance_id} 进入错误状态")
            time.sleep(5)  # 每 5 秒检查一次状态

        raise Exception(f"实例 {instance_id} 未在 {timeout} 秒内变为 {target_status} 状态")


# 初始化 OpenStack 管理器
manager = OpenstackManager()


# 修改初始化部分
def init_app():
    """异步初始化应用"""
    global manager, db, ssh_manager

    # 初始化数据库
    db = Database()

    # 初始化 OpenStack 管理器
    manager = OpenstackManager()

    # 初始化 SSH 管理器
    ssh_manager = SSHConnection()

    # 初始化文件传输管理器


# 异步加载云环境
def async_init_clouds():
    """异步初始化云环境"""
    try:
        manager._init_clients()
    except Exception as e:
        logger.error(f"Failed to initialize cloud environments: {e}")


# 在应用启动时异步初始化
init_app()
executor.submit(async_init_clouds)


# 添加缓存装饰器
def cache_with_timeout(timeout=300):  # 5分钟缓存
    def decorator(f):
        cache = {}

        @functools.wraps(f)
        def wrapper(*args, **kwargs):
            key = str(args) + str(kwargs)
            now = time.time()

            if key in cache:
                result, timestamp = cache[key]
                if now - timestamp < timeout:
                    return result

            result = f(*args, **kwargs)
            cache[key] = (result, now)
            return result

        return wrapper

    return decorator


# 添加性能监控装饰器
def performance_logger(f):
    @functools.wraps(f)
    def wrapper(*args, **kwargs):
        start_time = time.time()
        result = f(*args, **kwargs)
        end_time = time.time()
        duration = end_time - start_time
        if duration > 1.0:  # 记录执行时间超过1秒的请求
            logger.warning(f"Slow API call: {f.__name__} took {duration:.2f} seconds")
        return result

    return wrapper


# 优化云环境列表接口
@app.route("/api/clouds", methods=["GET"])
@error_handler
@performance_logger
@cache_with_timeout(timeout=10)
def list_clouds():
    """获取云环境列表"""
    return jsonify({"status": "success", "data": list(CLOUDS.keys())})


def run_websocket_server():
    """在单独的线程中运行WebSocket服务器"""
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        ssh_manager = SSHConnection()
        start_server = websockets.serve(
            ssh_manager.ws_handler, "0.0.0.0", 8765, loop=loop
        )
        loop.run_until_complete(start_server)
        loop.run_forever()
    except Exception as e:
        logger.error(f"WebSocket服务器运行错误: {str(e)}")


# 启动WebSocket服务器线程
websocket_thread = threading.Thread(target=run_websocket_server)
websocket_thread.daemon = True
websocket_thread.start()


# Flask 路由
@app.route("/")
def index():
    return render_template("index.html")


# 优化环境列表接口
@app.route("/environments", methods=["GET"])
@error_handler
@cache_with_timeout(timeout=10)
def list_environments():
    """获取所有 OpenStack 环境"""
    environments = list(CLOUDS.keys())
    return jsonify({"status": "success", "data": environments})


@app.route("/instances", methods=["GET"])
@error_handler
def list_instances():
    """获取实例列表"""
    cloud_name = request.args.get("cloud_name")
    if not cloud_name:
        raise ValueError("Missing cloud_name parameter")

    # 记录请求参数
    logger.info(f"Received request with parameters: {request.args}")

    # 获取所有过滤条件
    filters = {
        "status": request.args.get("status"),
        "instance_type": request.args.get("instance_type"),
        "ip": request.args.get("ip"),
        "created_date": request.args.get("created_date"),
        "name": request.args.get("name"),
        "page": request.args.get("page", "1"),
        "per_page": request.args.get("per_page", "10"),
        "sort_by": request.args.get("sort_by"),
        "sort_order": request.args.get("sort_order", "desc"),
    }

    # 记录过滤条件
    logger.info(f"Applied filters: {filters}")

    result = manager.search_instances(cloud_name, filters)

    # 记录结果
    logger.info(f"Found {result['total']} instances after filtering")

    return jsonify({"status": "success", **result})


@app.route("/instances/export", methods=["GET"])
@error_handler
def export_instances():
    """导出实例数据"""
    cloud_name = request.args.get("cloud_name")
    if not cloud_name:
        raise ValueError("Missing cloud_name parameter")

    format = request.args.get("format", "excel")
    filters = {
        "status": request.args.get("status"),
        "instance_type": request.args.get("instance_type"),
        "ip": request.args.get("ip"),
        "created_date": request.args.get("created_date"),
        "name": request.args.get("name"),
    }

    output = manager.export_instances(cloud_name, filters, format)

    if format == "excel":
        return send_file(
            output,
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            as_attachment=True,
            download_name=f'instances_{cloud_name}_{datetime.now().strftime("%Y%m%d")}.xlsx',
        )
    else:
        return send_file(
            io.BytesIO(output.encode()),
            mimetype="text/csv",
            as_attachment=True,
            download_name=f'instances_{cloud_name}_{datetime.now().strftime("%Y%m%d")}.csv',
        )


@app.route("/instances/<cloud_name>/<instance_id>", methods=["GET"])
@error_handler
def get_instance(cloud_name, instance_id):
    """获取实例详情"""
    instance = manager.get_instance_details(cloud_name, instance_id)
    return jsonify({"status": "success", "data": instance})


@app.route("/instances/<cloud_name>/<instance_id>/<action>", methods=["POST"])
@error_handler
def perform_instance_action(cloud_name, instance_id, action):
    """执行实例操作"""
    try:
        # 如果是删除操作，验证token
        if action == "delete":
            auth_header = request.headers.get("Authorization")
            if not auth_header or not auth_header.startswith("Bearer "):
                return jsonify({"status": "error", "message": "缺少授权token"}), 401

            token = auth_header.split(" ")[1]
            try:
                jwt.decode(token, app.config["SECRET_KEY"], algorithms=["HS256"])
            except jwt.ExpiredSignatureError:
                return jsonify({"status": "error", "message": "删除授权已过期"}), 401
            except jwt.InvalidTokenError:
                return jsonify({"status": "error", "message": "无效的删除授权"}), 401

        result = manager.perform_action(cloud_name, instance_id, action)
        return jsonify({"status": "success", "message": result})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/verify-delete-password", methods=["POST"])
@error_handler
def verify_delete_password():
    """验证删除密码"""
    try:
        data = request.get_json()
        if not data or "password" not in data:
            raise ValueError("Missing password")

        # 获取输入的密码和配置的密码
        input_password = data["password"]
        correct_password = SECURITY.get("delete_password")

        # 添加调试日志
        logger.warning(f"real password: {correct_password}")
        logger.warning(f"reciver password: {input_password}")
        logger.warning(f"real password type: {type(correct_password)}")
        logger.warning(f"reciver password type: {type(input_password)}")

        if not correct_password:
            logger.error("Delete password not configured in config file")
            raise ValueError("Delete password not configured")

        # 将两个密码都转换为字符串进行比较
        if str(input_password) == str(correct_password):
            return jsonify(
                {
                    "status": "success",
                    "message": "密码验证成功",
                    "token": generate_delete_token(),
                }
            )
        else:
            logger.warning(f"Invalid delete password attempt")
            return jsonify({"status": "error", "message": "删除密码错误"}), 401

    except ValueError as e:
        logger.error(f"Password verification error: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 400
    except Exception as e:
        logger.error(f"Unexpected error in password verification: {str(e)}")
        return jsonify({"status": "error", "message": "密码验证失败"}), 500


def generate_delete_token():
    """生成删除操作的临时token"""
    try:
        expires = time.time() + int(SECURITY.get("delete_password_expires", 3600))
        return jwt.encode(
            {"exp": expires},
            app.config["SECRET_KEY"],
            algorithm="HS256",
        )
    except Exception as e:
        logger.error(f"Error generating delete token: {str(e)}")
        raise


@app.route("/api/volumes", methods=["GET"])
@error_handler
def get_volumes():
    # 获取并验证查询参数
    cloud_name = request.args.get("cloud_name")
    name = request.args.get("name", "")
    status = request.args.get("status", "")
    size = request.args.get("size", "")
    volume_type = request.args.get("type", "")

    # 分页参数处理
    def safe_int(value, default):
        if not value or value == "undefined" or value == "null":
            return default
        try:
            return int(value)
        except (ValueError, TypeError):
            return default

    # 使用安全的参数处理
    page = safe_int(request.args.get("page"), 1)
    per_page = safe_int(request.args.get("per_page"), 10)
    sort_by = request.args.get("sort_by") or "created_at"
    sort_order = request.args.get("sort_order") or "desc"

    app.logger.info(
        f"Processing volume request with: page={page}, per_page={per_page}, sort_by={sort_by}, sort_order={sort_order}"
    )

    result = manager.search_volumes(
        cloud_name,
        {
            "name": name,
            "status": status,
            "size": size,
            "type": volume_type,
            "page": page,
            "per_page": per_page,
            "sort_by": sort_by,
            "sort_order": sort_order,
        },
    )
    app.logger.info(f"Found {len(result.get('data', []))} volumes after filtering")
    return jsonify({"status": "success", **result})


@app.route("/api/volumes/<cloud_name>/<volume_id>", methods=["GET"])
@error_handler
def get_volume(cloud_name, volume_id):
    """获取卷详情"""
    volume = manager.get_volume_details(cloud_name, volume_id)
    return jsonify({"status": "success", "data": volume})


@app.route("/api/volumes/<cloud_name>/<volume_id>/<action>", methods=["POST"])
@error_handler
def perform_volume_action(cloud_name, volume_id, action):
    """执行卷操作"""
    data = request.get_json() or {}

    # 如果是删除操作，验证token
    if action == "delete":
        auth_header = request.headers.get("Authorization")
        if not auth_header or not auth_header.startswith("Bearer "):
            return jsonify({"status": "error", "message": "缺少授权token"}), 401

        token = auth_header.split(" ")[1]
        try:
            jwt.decode(token, app.config["SECRET_KEY"], algorithms=["HS256"])
        except jwt.ExpiredSignatureError:
            return jsonify({"status": "error", "message": "删除授权已过期"}), 401
        except jwt.InvalidTokenError:
            return jsonify({"status": "error", "message": "无效的删除授权"}), 401

    result = manager.perform_volume_action(cloud_name, volume_id, action, **data)
    return jsonify({"status": "success", "message": result})


@app.route("/volumes/export", methods=["GET"])
@error_handler
def export_volumes():
    """导出卷数据"""
    cloud_name = request.args.get("cloud_name")
    if not cloud_name:
        raise ValueError("Missing cloud_name parameter")

    format = request.args.get("format", "excel")
    filters = {
        "name": request.args.get("name"),
        "status": request.args.get("status"),
        "size": request.args.get("size"),
        "type": request.args.get("type"),
    }

    output = manager.export_volumes(cloud_name, filters, format)

    if format == "excel":
        return send_file(
            output,
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            as_attachment=True,
            download_name=f'volumes_{cloud_name}_{datetime.now().strftime("%Y%m%d")}.xlsx',
        )
    else:
        return send_file(
            io.BytesIO(output.encode()),
            mimetype="text/csv",
            as_attachment=True,
            download_name=f'volumes_{cloud_name}_{datetime.now().strftime("%Y%m%d")}.csv',
        )


# 优化 SSH 连接列表接口
@app.route("/api/ssh/connections", methods=["GET"])
@error_handler
# @cache_with_timeout(timeout=10)  # 1分钟缓存
def get_ssh_connections():
    """获取所有SSH连接"""
    connections = db.get_all_connections()
    return jsonify({"status": "success", "data": connections})


@app.route("/api/ssh/connections", methods=["POST"])
@error_handler
def add_ssh_connection():
    """添加新的SSH连接"""
    data = request.json
    required_fields = ["name", "host", "username", "password"]
    for field in required_fields:
        if field not in data:
            raise ValueError(f"Missing required field: {field}")

    connection_id = db.add_connection(
        name=data["name"],
        host=data["host"],
        username=data["username"],
        password=data["password"],
        port=int(data.get("port", 22)),
        description=data.get("description", ""),
    )
    return jsonify({"status": "success", "id": connection_id})


@app.route("/api/ssh/connections/<int:connection_id>", methods=["PUT"])
@error_handler
def update_ssh_connection(connection_id):
    """更新SSH连接"""
    data = request.json
    db.update_connection(
        connection_id=connection_id,
        name=data["name"],
        host=data["host"],
        username=data["username"],
        password=data["password"],
        port=int(data.get("port", 22)),
        description=data.get("description", ""),
    )
    return jsonify({"status": "success"})


@app.route("/api/ssh/connections/<int:connection_id>", methods=["DELETE"])
@error_handler
def delete_ssh_connection(connection_id):
    """删除SSH连接"""
    db.delete_connection(connection_id)
    return jsonify({"status": "success"})


@app.route("/api/ssh/test-connection", methods=["POST"])
@error_handler
def test_ssh_connection():
    """测试SSH连接"""
    data = request.json
    try:
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        # 设置超时时间
        ssh.connect(
            hostname=data["host"],
            port=int(data.get("port", 22)),
            username=data["username"],
            password=data["password"],
            timeout=5,
        )

        # 测试执行简单命令
        stdin, stdout, stderr = ssh.exec_command('echo "Connection test successful"')
        output = stdout.read().decode()
        logger.warning(f"SSH连接测试输出：{output}")
        ssh.close()
        return jsonify({"status": "success", "message": "SSH连接测试成功！"})
    except paramiko.AuthenticationException:
        return (
            jsonify({"status": "error", "message": "认证失败：用户名或密码错误"}),
            401,
        )
    except paramiko.SSHException as e:
        return jsonify({"status": "error", "message": f"SSH连接错误：{str(e)}"}), 500
    except Exception as e:
        return jsonify({"status": "error", "message": f"连接测试失败：{str(e)}"}), 500


# 添加文件下载路由
@app.route("/downloads/<filename>")
def download_file_route(filename):
    """提供文件下载"""
    return send_file(
        os.path.join(app.config["DOWNLOAD_FOLDER"], filename),
        as_attachment=True,
        download_name=filename,
    )


@app.route("/api/ssh/connect/<int:connection_id>", methods=["POST"])
@error_handler
def connect_ssh(connection_id):
    connection = db.get_connection_by_id(connection_id)
    if not connection:
        return jsonify({"status": "error", "message": "连接信息不存在"}), 404

    result = ssh_manager.connect_and_get_shell(connection)
    return jsonify(result)


@app.route("/api/ssh/shell/<int:connection_id>", methods=["POST"])
@error_handler
def shell_command(connection_id):
    command = request.json.get("command")
    if not command:
        return jsonify({"status": "error", "message": "命令不能为空"}), 400

    # 发送命令
    write_result = ssh_manager.write_to_shell(connection_id, command)
    if write_result["status"] == "error":
        return jsonify(write_result), 500

    # 读取输出
    read_result = ssh_manager.read_shell_output(connection_id)
    return jsonify(read_result)


@app.route("/api/ssh/close/<int:connection_id>", methods=["POST"])
@error_handler
def close_ssh(connection_id):
    result = ssh_manager.close_connection(connection_id)
    return jsonify(result)


# 添加获取单个 SSH 连接详情的路由
@app.route("/api/ssh/connections/<int:connection_id>", methods=["GET"])
@error_handler
def get_ssh_connection(connection_id):
    """获取单个SSH连接详情"""
    try:
        connection = db.get_connection_by_id(connection_id)
        if not connection:
            return jsonify({"status": "error", "message": "连接不存在"}), 404

        # 因为 connection 已经是字典格式，直接使用
        return jsonify(
            {
                "status": "success",
                "data": {
                    "id": connection_id,
                    "name": connection.get("name", ""),
                    "host": connection.get("host", ""),
                    "port": connection.get("port", 22),
                    "username": connection.get("username", ""),
                    "password": connection.get("password", ""),
                    "description": connection.get("description", ""),
                },
            }
        )
    except Exception as e:
        logger.error(f"获取SSH连接详情失败: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/api/volumes/<cloud_name>/<volume_id>/extend", methods=["POST"])
@error_handler
def extend_volume(cloud_name, volume_id):
    """扩容卷"""
    data = request.get_json()
    if not data or "new_size" not in data:
        raise ValueError("Missing new_size parameter")

    new_size = int(data["new_size"])
    if new_size <= 0:
        raise ValueError("New size must be greater than 0")

    result = manager.extend_volume(cloud_name, volume_id, new_size)
    return jsonify({"status": "success", "message": result})


@app.route('/api/volumes/<cloud_name>/<volume_id>/snapshots', methods=['POST'])
def create_volume_snapshot(cloud_name, volume_id):
    data = request.get_json()
    snapshot_name = data.get('name')
    snapshot_description = data.get('description')

    if not snapshot_name:
        return jsonify({'status': 'error', 'message': '快照名称不能为空'}), 400

    # 调用 OpenStack API 创建快照
    try:
        snapshot = manager.create_snapshot(cloud_name, volume_id, snapshot_name, snapshot_description)
        return jsonify({'status': 'success', 'data': snapshot})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/api/volumes/<cloud_name>/<volume_id>/snapshots', methods=['GET'])
def get_volume_snapshots(cloud_name, volume_id):
    try:
        snapshots = manager.get_snapshots(cloud_name, volume_id)
        return jsonify({'status': 'success', 'data': snapshots})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/api/volumes/<cloud_name>/<volume_id>/snapshots/<snapshot_id>', methods=['DELETE'])
def delete_volume_snapshot(cloud_name, volume_id, snapshot_id):
    try:
        manager.delete_snapshot(cloud_name, snapshot_id)
        return jsonify({'status': 'success'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/check-password', methods=['POST'])
def check_password():
    data = request.get_json()
    password = data.get('password')

    if password == CORRECT_PASSWORD:
        return jsonify({'status': 'success'})
    else:
        return jsonify({'status': 'error', 'message': '密码错误'}), 401


@app.route("/api/instances/create", methods=["POST"])
@error_handler
def create_instance():
    """创建实例"""
    data = request.get_json()
    cloud_name = data.get("cloud_name")
    instance_name = data.get("instance_name")
    flavor_id = data.get("flavor_id")
    image_id = data.get("image_id")
    network_id = data.get("network_id")
    key_name = data.get("key_name")
    security_groups = data.get("security_groups", [])

    if not all([cloud_name, instance_name, flavor_id, image_id, network_id]):
        raise ValueError("缺少必要的参数")

    try:
        nova = manager.nova_clients.get(cloud_name)
        if not nova:
            raise ValueError(f"未找到云环境: {cloud_name}")

        # 创建实例
        instance = nova.servers.create(
            name=instance_name,
            flavor=flavor_id,
            image=image_id,
            nics=[{"net-id": network_id}],
            key_name=key_name,
            security_groups=security_groups
        )

        # 等待实例创建完成
        instance = manager.wait_for_instance_status(cloud_name, instance.id, "ACTIVE")

        return jsonify({
            "status": "success",
            "message": "实例创建成功",
            "data": manager._format_instance_data(instance, cloud_name)
        })
    except Exception as e:
        logger.error(f"创建实例失败: {str(e)}")
        raise ValueError(f"创建实例失败: {str(e)}")


@app.route("/api/flavors", methods=["GET"])
@error_handler
def get_flavors():
    """获取实例类型列表"""
    cloud_name = request.args.get("cloud_name")
    if not cloud_name:
        raise ValueError("缺少 cloud_name 参数")

    nova = manager.nova_clients.get(cloud_name)
    if not nova:
        raise ValueError(f"未找到云环境: {cloud_name}")

    flavors = nova.flavors.list()
    return jsonify({
        "status": "success",
        "data": [{"id": flavor.id, "name": flavor.name} for flavor in flavors]
    })


@app.route("/api/images", methods=["GET"])
@error_handler
def get_images():
    """获取镜像列表"""
    cloud_name = request.args.get("cloud_name")
    if not cloud_name:
        raise ValueError("缺少 cloud_name 参数")

    nova = manager.nova_clients.get(cloud_name)
    if not nova:
        raise ValueError(f"未找到云环境: {cloud_name}")

    images = nova.images.list()
    return jsonify({
        "status": "success",
        "data": [{"id": image.id, "name": image.name} for image in images]
    })


@app.route("/api/networks", methods=["GET"])
@error_handler
def get_networks():
    """获取网络列表"""
    cloud_name = request.args.get("cloud_name")
    if not cloud_name:
        raise ValueError("缺少 cloud_name 参数")

    nova = manager.nova_clients.get(cloud_name)
    if not nova:
        raise ValueError(f"未找到云环境: {cloud_name}")

    networks = nova.networks.list()
    return jsonify({
        "status": "success",
        "data": [{"id": network.id, "name": network.label} for network in networks]
    })


@app.route("/api/keypairs", methods=["GET"])
@error_handler
def get_keypairs():
    """获取密钥对列表"""
    cloud_name = request.args.get("cloud_name")
    if not cloud_name:
        raise ValueError("缺少 cloud_name 参数")

    nova = manager.nova_clients.get(cloud_name)
    if not nova:
        raise ValueError(f"未找到云环境: {cloud_name}")

    keypairs = nova.keypairs.list()
    return jsonify({
        "status": "success",
        "data": [{"name": keypair.name} for keypair in keypairs]
    })


@app.route("/api/security-groups", methods=["GET"])
@error_handler
def get_security_groups():
    """获取安全组列表"""
    cloud_name = request.args.get("cloud_name")
    if not cloud_name:
        raise ValueError("缺少 cloud_name 参数")

    nova = manager.nova_clients.get(cloud_name)
    if not nova:
        raise ValueError(f"未找到云环境: {cloud_name}")

    security_groups = nova.security_groups.list()
    return jsonify({
        "status": "success",
        "data": [{"name": group.name} for group in security_groups]
    })


if __name__ == '__main__':
    app.run(debug=True)

# 启动 Flask 应用
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
