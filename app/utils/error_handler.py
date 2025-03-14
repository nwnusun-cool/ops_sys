from functools import wraps
import logging
from flask import jsonify

logger = logging.getLogger(__name__)

def error_handler(f):
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