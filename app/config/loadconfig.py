import logging
import os 
import yaml
# 配置日志
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

base_dir = os.path.dirname(os.path.abspath(__file__))
config_path = os.path.join(base_dir, "config.json")

with open(config_path, "r") as f:
    config = yaml.safe_load(f)

CLOUDS = config["openstack_environments"]
SECURITY = config.get(
    "security",
    {"delete_password": "2524354300", "delete_password_expires": 3600},
)
SECRET_KEY = config.get("security", {}).get(
    "secret_key", "your-default-secret-key-here"
)
CORRECT_PASSWORD = config.get("page_password", None)
if not CORRECT_PASSWORD:
    raise ValueError("Page password is not set in the configuration file.")