import time
from functools import wraps
import logging

logger = logging.getLogger(__name__)

def performance_logger(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        start_time = time.time()
        result = f(*args, **kwargs)
        end_time = time.time()
        duration = end_time - start_time
        if duration > 1.0:
            logger.warning(f"Slow API call: {f.__name__} took {duration:.2f} seconds")
        return result
    return wrapper