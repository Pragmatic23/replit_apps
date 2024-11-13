import os
import json
import time
import hashlib
import threading
import logging
import tempfile
import pickle
import zlib
import random
from typing import Any, Optional, Dict
from functools import wraps

logger = logging.getLogger(__name__)

class CircuitBreaker:
    def __init__(self, failure_threshold: int = 5, reset_timeout: int = 60):
        self.failure_threshold = failure_threshold
        self.reset_timeout = reset_timeout
        self.failures = 0
        self.last_failure_time = 0
        self.state = "closed"  # closed, open, half-open
        self.lock = threading.Lock()

    def record_failure(self):
        with self.lock:
            current_time = time.time()
            if current_time - self.last_failure_time > self.reset_timeout:
                self.failures = 0
            
            self.failures += 1
            self.last_failure_time = current_time
            
            if self.failures >= self.failure_threshold:
                self.state = "open"
                logger.warning("Circuit breaker opened due to multiple failures")

    def record_success(self):
        with self.lock:
            self.failures = 0
            self.state = "closed"

    def allow_request(self) -> bool:
        with self.lock:
            if self.state == "closed":
                return True
            elif self.state == "open":
                if time.time() - self.last_failure_time > self.reset_timeout:
                    self.state = "half-open"
                    return True
                return False
            else:  # half-open
                return random.random() < 0.1  # Allow 10% of requests through

class CacheStats:
    def __init__(self):
        self.hits = 0
        self.misses = 0
        self.errors = 0
        self._lock = threading.Lock()
    
    def record_hit(self):
        with self._lock:
            self.hits += 1
    
    def record_miss(self):
        with self._lock:
            self.misses += 1
    
    def record_error(self):
        with self._lock:
            self.errors += 1
    
    @property
    def hit_rate(self):
        total = self.hits + self.misses
        return (self.hits / total * 100) if total > 0 else 0

class RecommendationCache:
    def __init__(self):
        self.memory_cache = {}
        self.disk_cache_dir = os.path.join(tempfile.gettempdir(), 'odoo_recommender_cache')
        self.cache_version = "1.1"
        self.max_memory_items = 1000
        self.cleanup_interval = 3600  # 1 hour
        self.last_cleanup = time.time()
        self.lock = threading.Lock()
        self.stats = CacheStats()
        
        # Create disk cache directory
        os.makedirs(self.disk_cache_dir, exist_ok=True)
        
        # Start maintenance thread
        self._start_maintenance_thread()
    
    def _start_maintenance_thread(self):
        def maintenance_task():
            while True:
                try:
                    time.sleep(self.cleanup_interval)
                    self._cleanup()
                except Exception as e:
                    logger.error(f"Cache maintenance error: {str(e)}")
                    time.sleep(60)
        
        thread = threading.Thread(target=maintenance_task, daemon=True)
        thread.start()
    
    def _generate_key(self, *args, **kwargs) -> str:
        """Generate a unique cache key."""
        key_parts = [str(arg) for arg in args]
        key_parts.extend(f"{k}:{v}" for k, v in sorted(kwargs.items()))
        key_string = "|".join(key_parts)
        return hashlib.sha256(key_string.encode()).hexdigest()
    
    def _compress_data(self, data: Any) -> bytes:
        """Compress data for storage."""
        pickled = pickle.dumps(data)
        return zlib.compress(pickled)
    
    def _decompress_data(self, compressed_data: bytes) -> Any:
        """Decompress stored data."""
        decompressed = zlib.decompress(compressed_data)
        return pickle.loads(decompressed)
    
    def get(self, key: str) -> Optional[Any]:
        """Get value from cache with fallback to disk."""
        try:
            # Check memory cache first
            with self.lock:
                if key in self.memory_cache:
                    entry = self.memory_cache[key]
                    if entry['expires'] > time.time():
                        self.stats.record_hit()
                        return entry['value']
                    else:
                        del self.memory_cache[key]
            
            # Try disk cache
            cache_path = os.path.join(self.disk_cache_dir, f"{key}.cache")
            if os.path.exists(cache_path):
                with open(cache_path, 'rb') as f:
                    compressed_data = f.read()
                    data = self._decompress_data(compressed_data)
                    if data['expires'] > time.time() and data['version'] == self.cache_version:
                        # Restore to memory cache
                        self.set(key, data['value'], expiration=int(data['expires'] - time.time()))
                        self.stats.record_hit()
                        return data['value']
                    else:
                        os.remove(cache_path)
            
            self.stats.record_miss()
            return None
            
        except Exception as e:
            self.stats.record_error()
            logger.error(f"Cache get error: {str(e)}")
            return None
    
    def set(self, key: str, value: Any, expiration: int = 3600):
        """Set value in cache with disk backup."""
        try:
            expires = time.time() + expiration
            
            # Update memory cache
            with self.lock:
                if len(self.memory_cache) >= self.max_memory_items:
                    oldest_key = min(self.memory_cache.items(), key=lambda x: x[1]['expires'])
                    del self.memory_cache[oldest_key[0]]
                
                self.memory_cache[key] = {
                    'value': value,
                    'expires': expires
                }
            
            # Update disk cache
            cache_path = os.path.join(self.disk_cache_dir, f"{key}.cache")
            compressed_data = self._compress_data({
                'value': value,
                'expires': expires,
                'version': self.cache_version
            })
            
            with open(cache_path, 'wb') as f:
                f.write(compressed_data)
                
        except Exception as e:
            self.stats.record_error()
            logger.error(f"Cache set error: {str(e)}")
    
    def _cleanup(self):
        """Clean up expired cache entries."""
        current_time = time.time()
        
        # Clean memory cache
        with self.lock:
            expired_keys = [k for k, v in self.memory_cache.items() 
                          if v['expires'] <= current_time]
            for k in expired_keys:
                del self.memory_cache[k]
        
        # Clean disk cache
        try:
            for filename in os.listdir(self.disk_cache_dir):
                filepath = os.path.join(self.disk_cache_dir, filename)
                if os.path.getctime(filepath) < current_time - (24 * 3600):  # 24 hours
                    os.remove(filepath)
        except Exception as e:
            logger.error(f"Cache cleanup error: {str(e)}")

# Initialize global cache instance
recommendation_cache = RecommendationCache()

def cache_recommendation(expiration: int = 3600):
    """Decorator for caching recommendation responses."""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Don't cache streaming responses
            if kwargs.get('stream', False):
                return func(*args, **kwargs)
            
            cache_key = recommendation_cache._generate_key(*args, **kwargs)
            cached_result = recommendation_cache.get(cache_key)
            
            if cached_result is not None:
                logger.info(f"Cache hit for recommendation key: {cache_key}")
                return cached_result
            
            result = func(*args, **kwargs)
            if result and not isinstance(result, Exception):
                recommendation_cache.set(cache_key, result, expiration)
            
            return result
        return wrapper
    return decorator
