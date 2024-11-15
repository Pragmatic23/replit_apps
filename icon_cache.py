import os
import redis
from functools import wraps
import json
import logging
from typing import Optional, Dict
import hashlib
import time

logger = logging.getLogger(__name__)

# Configure Redis
REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
CACHE_TIMEOUT = 3600  # 1 hour

class IconCache:
    _instance = None
    _initialized = False

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if not self._initialized:
            self.redis_client = None
            self.initialize_redis()
            IconCache._initialized = True

    def initialize_redis(self):
        try:
            self.redis_client = redis.from_url(REDIS_URL)
            self.redis_client.ping()
            logger.info("Redis connection established for icon caching")
        except (redis.ConnectionError, ConnectionRefusedError) as e:
            logger.warning(f"Redis unavailable: {str(e)}, using filesystem cache for icons")
            self.redis_client = None

    @property
    def is_redis_available(self):
        return self.redis_client is not None

    def get_cache_key(self, module_name: str) -> str:
        """Generate a consistent cache key for module icons."""
        return f"icon:{hashlib.md5(module_name.encode()).hexdigest()}"

    def get_fs_cache_path(self, cache_key: str) -> str:
        """Get filesystem cache path for icons."""
        cache_dir = os.path.join("static", "icon_cache")
        if not os.path.exists(cache_dir):
            os.makedirs(cache_dir)
        return os.path.join(cache_dir, f"{cache_key}.json")

    def get(self, module_name: str) -> Optional[Dict]:
        """Get cached icon information."""
        cache_key = self.get_cache_key(module_name)

        # Try Redis first if available
        if self.is_redis_available:
            try:
                cached_data = self.redis_client.get(cache_key)
                if cached_data:
                    return json.loads(cached_data.decode('utf-8'))
            except Exception as e:
                logger.error(f"Redis get error: {str(e)}")

        # Try filesystem cache
        fs_cache_path = self.get_fs_cache_path(cache_key)
        if os.path.exists(fs_cache_path):
            try:
                with open(fs_cache_path, 'r') as f:
                    cached_data = json.load(f)
                    if cached_data.get('timestamp', 0) + CACHE_TIMEOUT > time.time():
                        return cached_data.get('data')
            except Exception as e:
                logger.error(f"Filesystem cache get error: {str(e)}")

        return None

    def set(self, module_name: str, data: Dict, expiration: int = CACHE_TIMEOUT):
        """Set icon information in cache."""
        cache_key = self.get_cache_key(module_name)
        cache_data = {
            'data': data,
            'timestamp': time.time()
        }

        # Try to cache in Redis if available
        if self.is_redis_available:
            try:
                self.redis_client.setex(
                    cache_key,
                    expiration,
                    json.dumps(data)
                )
            except Exception as e:
                logger.error(f"Redis set error: {str(e)}")

        # Always cache to filesystem as fallback
        try:
            fs_cache_path = self.get_fs_cache_path(cache_key)
            with open(fs_cache_path, 'w') as f:
                json.dump(cache_data, f)
        except Exception as e:
            logger.error(f"Filesystem cache set error: {str(e)}")

    def clear(self, module_name: Optional[str] = None):
        """Clear icon cache for a specific module or all modules."""
        if module_name:
            cache_keys = [self.get_cache_key(module_name)]
        else:
            if self.is_redis_available:
                try:
                    cache_keys = self.redis_client.keys("icon:*")
                except Exception as e:
                    logger.error(f"Redis keys error: {str(e)}")
                    cache_keys = []
            else:
                cache_keys = []

            # Clear filesystem cache
            cache_dir = os.path.join("static", "icon_cache")
            if os.path.exists(cache_dir):
                for file in os.listdir(cache_dir):
                    if file.startswith("icon:") and file.endswith(".json"):
                        try:
                            os.remove(os.path.join(cache_dir, file))
                        except Exception as e:
                            logger.error(f"Error removing cache file {file}: {str(e)}")

        # Clear Redis cache if available
        if self.is_redis_available:
            for key in cache_keys:
                try:
                    self.redis_client.delete(key)
                except Exception as e:
                    logger.error(f"Redis delete error: {str(e)}")

# Create singleton instance
icon_cache = IconCache()

def cache_icon_info(expiration: int = CACHE_TIMEOUT):
    """Decorator for caching icon information."""
    def decorator(func):
        @wraps(func)
        def wrapper(module_name: str) -> Optional[Dict]:
            # Try to get from cache first
            cached_result = icon_cache.get(module_name)
            if cached_result is not None:
                return cached_result

            # Get fresh data
            result = func(module_name)
            if result:
                icon_cache.set(module_name, result, expiration)
            return result
        return wrapper
    return decorator
