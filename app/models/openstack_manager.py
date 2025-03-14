import logging
from datetime import datetime, timedelta
import pytz
import re
import pandas as pd
import io
from keystoneauth1.identity import v3
from keystoneauth1 import session
from novaclient import client as nova_client
from cinderclient import client as cinder_client
from openstack import exceptions as openstack_exceptions
from .ssh_model import Database, SSHConnection

logger = logging.getLogger(__name__)

class CustomBytesIO:
    def __init__(self, bytes_io):# type: ignore[redeclared]
        self.bytes_io = bytes_io

    def __getattr__(self, attr):# type: ignore[redeclared]
        return getattr(self.bytes_io, attr)

    def truncate(self, size=None):# type: ignore[redeclared]
        return self.bytes_io.truncate(size=size)

    def seek(self, *args, **kwargs):# type: ignore[redeclared]
        return self.bytes_io.seek(*args, **kwargs)

    def write(self, *args, **kwargs):# type: ignore[redeclared]
        return self.bytes_io.write(*args, **kwargs)

    def close(self):# type: ignore[redeclared]
        return self.bytes_io.close()

    def tell(self):  # 添加 tell 方法
        return self.bytes_io.tell()

    def flush(self):
        """实现 flush 方法"""
        if hasattr(self.bytes_io, 'flush'):
            return self.bytes_io.flush()

    @property
    def mode(self):
        """实现 mode 属性"""
        return getattr(self.bytes_io, 'mode', 'wb')

    def seekable(self):
        """实现 seekable 方法"""
        return True

    def __init__(self, bytes_io):
        self.bytes_io = bytes_io

    def __getattr__(self, attr):
        return getattr(self.bytes_io, attr)

    def truncate(self, size=None):
        return self.bytes_io.truncate(size=size)

    def seek(self, *args, **kwargs):
        return self.bytes_io.seek(*args, **kwargs)

    def write(self, *args, **kwargs):
        return self.bytes_io.write(*args, **kwargs)

    def close(self):
        return self.bytes_io.close()

class OpenstackManager(object):
    def __init__(self,CLOUDS):
        self.CLOUDS = CLOUDS
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
        for cloud_name, cloud_config in self.CLOUDS.items():
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
            try:
                # output = io.BytesIO()
                output = CustomBytesIO(io.BytesIO())  # 使用 CustomBytesIO 包装 BytesIO
                with pd.ExcelWriter(output, engine="openpyxl") as writer:
                    df.to_excel(writer, index=False, sheet_name="Instances")
                output.seek(0)
                return output
            except TypeError as e:
                logger.error(f"Failed to create ExcelWriter: {str(e)}")
                raise ValueError("Failed to export data as Excel. Please check your pandas and openpyxl versions.")
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
                # output = io.BytesIO()
                output = CustomBytesIO(io.BytesIO())  # 使用 CustomBytesIO 包装 BytesIO
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
            if cinder_client:
                snapshot = cinder_client.volume_snapshots.get(snapshot_id)
                if snapshot.status == target_status:
                    return snapshot
                elif snapshot.status == 'error':
                    raise Exception(f"快照 {snapshot_id} 进入错误状态")
            else:
                raise Exception(f"未找到云环境 {cloud_name} 的 cinder 客户端")
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
        import time  # 添加 time 模块的导入
        start_time = time.time()
        nova = self.nova_clients.get(cloud_name)  # 修正为 self.nova_clients

        # 检查 nova 是否为 None
        if nova is None:
            raise Exception(f"未找到云环境 {cloud_name} 的 nova 客户端")

        while time.time() - start_time < timeout:
            instance = nova.servers.get(instance_id)
            if instance.status == target_status:
                return instance
            elif instance.status == "ERROR":
                raise Exception(f"实例 {instance_id} 进入错误状态")
            time.sleep(5)  # 每 5 秒检查一次状态

        raise Exception(f"实例 {instance_id} 未在 {timeout} 秒内变为 {target_status} 状态")
