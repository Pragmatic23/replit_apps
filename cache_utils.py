import os
import redis
import json
from datetime import datetime, timedelta
from functools import wraps
import hashlib
from typing import Any, Optional, Dict
import logging
from redis.exceptions import ConnectionError as RedisConnectionError

logger = logging.getLogger(__name__)

# Initialize Redis connection with fallback
class CacheStorage:
    def __init__(self):
        self.redis_available = False
        self.local_cache = {}
        try:
            self.redis = redis.from_url(os.environ.get("REDIS_URL", "redis://localhost:6379"))
            self.redis.ping()
            self.redis_available = True
            logger.info("Redis cache initialized successfully")
        except RedisConnectionError:
            logger.warning("Redis unavailable. Using in-memory cache as fallback")

    def get(self, key: str) -> Optional[Any]:
        if self.redis_available:
            try:
                data = self.redis.get(key)
                return json.loads(data) if data else None
            except Exception as e:
                logger.error(f"Redis get error: {str(e)}")
                return self.local_cache.get(key)
        return self.local_cache.get(key)

    def set(self, key: str, value: Any, expiration: int):
        if self.redis_available:
            try:
                self.redis.setex(key, expiration, json.dumps(value))
            except Exception as e:
                logger.error(f"Redis set error: {str(e)}")
                self.local_cache[key] = value
        else:
            self.local_cache[key] = value

# Initialize cache storage
cache_storage = CacheStorage()

def cache_with_redis(expiration: int = 3600):
    """Decorator for caching with Redis/memory fallback and request deduplication."""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Generate cache key
            key_parts = [str(arg) for arg in args]
            key_parts.extend(f"{k}:{v}" for k, v in sorted(kwargs.items()))
            key_string = "|".join(key_parts)
            cache_key = hashlib.md5(key_string.encode()).hexdigest()
            
            # Try to get from cache
            cached_result = cache_storage.get(cache_key)
            if cached_result:
                logger.info(f"Cache hit for key: {cache_key}")
                return cached_result
            
            # Execute function and cache result
            result = func(*args, **kwargs)
            cache_storage.set(cache_key, result, expiration)
            return result
            
        return wrapper
    return decorator