import time
from functools import wraps

def cache_with_timeout(timeout=300):
    def decorator(f):
        cache = {}

        @wraps(f)
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