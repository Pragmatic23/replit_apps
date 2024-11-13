import os
import json
import time
import hashlib
import threading
import logging
from typing import Any, Optional, Dict, Set
from datetime import datetime, timedelta
from functools import wraps
import tempfile
import pickle
import zlib
import random

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

class CacheStorage:
    def __init__(self):
        self.local_cache = {}
        self.disk_cache_dir = os.path.join(tempfile.gettempdir(), 'odoo_recommender_cache')
        self.cache_version = "1.0"
        self.warm_cache_interval = 3600
        self.frequently_accessed = set()
        self.access_counts = {}
        self.last_cleanup = time.time()
        self.cleanup_interval = 3600
        self.access_threshold = 5
        self.lock = threading.Lock()
        self.circuit_breaker = CircuitBreaker()
        self.reconnect_delay = 5
        self.max_reconnect_attempts = 3
        
        # Create disk cache directory
        os.makedirs(self.disk_cache_dir, exist_ok=True)
        
        # Start maintenance threads
        self._start_maintenance_threads()

    def _start_maintenance_threads(self):
        """Start maintenance threads for cache warming and cleanup."""
        def run_maintenance():
            while True:
                try:
                    time.sleep(self.warm_cache_interval)
                    self._warm_frequent_keys()
                    self._cleanup_old_entries()
                except Exception as e:
                    logger.error(f"Error in maintenance thread: {str(e)}")
                    time.sleep(60)

        maintenance_thread = threading.Thread(target=run_maintenance, daemon=True)
        maintenance_thread.start()

    def _store_in_all_layers(self, key: str, value: Any, expiration: int = 3600):
        """Store value in all available cache layers with improved error handling."""
        # Store in memory with LRU-like eviction
        with self.lock:
            if len(self.local_cache) >= 1000:  # Limit local cache size
                oldest_key = min(self.local_cache.items(), key=lambda x: x[1]['access_time'])
                del self.local_cache[oldest_key[0]]
            
            self.local_cache[key] = {
                'value': value,
                'expires': time.time() + expiration,
                'access_time': time.time()
            }
        
        # Store on disk with compression
        try:
            cache_path = self._get_disk_cache_path(key)
            with open(cache_path, 'wb') as f:
                pickle.dump({
                    'value': value,
                    'expires': time.time() + expiration,
                    'version': self.cache_version
                }, f, protocol=pickle.HIGHEST_PROTOCOL)
        except Exception as e:
            logger.error(f"Disk cache write error: {str(e)}")

    def get(self, key: str) -> Optional[Any]:
        """Get value from cache with improved fallback mechanisms."""
        current_time = time.time()
        
        # Update access tracking
        with self.lock:
            if key not in self.access_counts:
                self.access_counts[key] = {'count': 0, 'last_access': current_time}
            self.access_counts[key]['count'] += 1
            self.access_counts[key]['last_access'] = current_time
            
            if self.access_counts[key]['count'] >= self.access_threshold:
                self.frequently_accessed.add(key)
        
        # Try memory cache
        with self.lock:
            if key in self.local_cache:
                cache_entry = self.local_cache[key]
                if cache_entry['expires'] > current_time:
                    cache_entry['access_time'] = current_time
                    return cache_entry['value']
                else:
                    del self.local_cache[key]
        
        # Try disk cache
        try:
            cache_path = self._get_disk_cache_path(key)
            if os.path.exists(cache_path):
                with open(cache_path, 'rb') as f:
                    data = pickle.load(f)
                    if data['expires'] > current_time and data['version'] == self.cache_version:
                        return data['value']
                    else:
                        os.remove(cache_path)
        except Exception as e:
            logger.error(f"Disk cache read error: {str(e)}")
        
        return None

    def set(self, key: str, value: Any, expiration: int = 3600):
        """Set value in cache with improved error handling and storage mechanisms."""
        self._store_in_all_layers(key, value, expiration)

    def _warm_frequent_keys(self):
        """Warm up frequently accessed cache entries."""
        with self.lock:
            current_time = time.time()
            for key in self.frequently_accessed:
                try:
                    value = self.get(key)
                    if value is not None:
                        self._store_in_all_layers(key, value)
                except Exception as e:
                    logger.error(f"Error warming cache for key {key}: {str(e)}")
    
    def _cleanup_old_entries(self):
        """Clean up old cache entries."""
        current_time = time.time()
        if current_time - self.last_cleanup < self.cleanup_interval:
            return
            
        with self.lock:
            # Clean up access counts
            self.access_counts = {
                k: v for k, v in self.access_counts.items()
                if current_time - v['last_access'] < 86400  # 24 hours
            }
            
            # Update frequently accessed set
            self.frequently_accessed = {
                k for k, v in self.access_counts.items()
                if v['count'] >= self.access_threshold
            }
            
            # Clean up disk cache
            try:
                for filename in os.listdir(self.disk_cache_dir):
                    filepath = os.path.join(self.disk_cache_dir, filename)
                    if os.path.getctime(filepath) < current_time - 86400:
                        os.remove(filepath)
            except Exception as e:
                logger.error(f"Error cleaning disk cache: {str(e)}")
            
            self.last_cleanup = current_time
    
    def _get_disk_cache_path(self, key: str) -> str:
        """Get the disk cache file path for a key."""
        return os.path.join(self.disk_cache_dir, f"{key}.cache")
    

# Initialize cache storage
cache_storage = CacheStorage()

def cache_with_redis(expiration: int = 3600):
    """Decorator for caching with improved Redis/memory/disk fallback."""
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

import threading
import time
import logging
from typing import Any, Optional, Dict
from functools import wraps
import hashlib
import pickle
import os
import tempfile

logger = logging.getLogger(__name__)

class SimpleCache:
    def __init__(self, max_size=1000, expiration=3600):
        self.cache = {}
        self.max_size = max_size
        self.default_expiration = expiration
        self.lock = threading.Lock()
        
        # Create disk cache directory
        self.disk_cache_dir = os.path.join(tempfile.gettempdir(), 'odoo_recommender_cache')
        os.makedirs(self.disk_cache_dir, exist_ok=True)
    
    def get(self, key: str) -> Optional[Any]:
        """Get value from cache with disk fallback."""
        current_time = time.time()
        
        # Try memory cache first
        with self.lock:
            if key in self.cache:
                value, expires = self.cache[key]
                if expires > current_time:
                    return value
                else:
                    del self.cache[key]
        
        # Try disk cache as fallback
        try:
            cache_path = os.path.join(self.disk_cache_dir, f"{key}.cache")
            if os.path.exists(cache_path):
                with open(cache_path, 'rb') as f:
                    data = pickle.load(f)
                    if data['expires'] > current_time:
                        # Restore to memory cache
                        self.set(key, data['value'], remaining_time=data['expires'] - current_time)
                        return data['value']
                    else:
                        os.remove(cache_path)
        except Exception as e:
            logger.error(f"Error reading from disk cache: {str(e)}")
        
        return None
    
    def set(self, key: str, value: Any, expiration: Optional[int] = None, remaining_time: Optional[float] = None):
        """Set value in cache with disk backup."""
        with self.lock:
            # Implement LRU-like eviction
            if len(self.cache) >= self.max_size:
                oldest_key = min(self.cache.items(), key=lambda x: x[1][1])
                del self.cache[oldest_key[0]]
            
            expires = time.time() + (remaining_time if remaining_time else (expiration or self.default_expiration))
            self.cache[key] = (value, expires)
        
        # Store on disk as backup
        try:
            cache_path = os.path.join(self.disk_cache_dir, f"{key}.cache")
            with open(cache_path, 'wb') as f:
                pickle.dump({
                    'value': value,
                    'expires': expires
                }, f, protocol=pickle.HIGHEST_PROTOCOL)
        except Exception as e:
            logger.error(f"Error writing to disk cache: {str(e)}")

    def cleanup(self):
        """Clean up expired entries."""
        current_time = time.time()
        with self.lock:
            # Clean memory cache
            expired_keys = [k for k, v in self.cache.items() if v[1] <= current_time]
            for k in expired_keys:
                del self.cache[k]
            
            # Clean disk cache
            try:
                for filename in os.listdir(self.disk_cache_dir):
                    filepath = os.path.join(self.disk_cache_dir, filename)
                    if os.path.getctime(filepath) < current_time - self.default_expiration:
                        os.remove(filepath)
            except Exception as e:
                logger.error(f"Error cleaning disk cache: {str(e)}")

# Initialize cache
cache = SimpleCache()

def cache_response(expiration: int = 3600):
    """Decorator for caching with memory and disk fallback."""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Generate cache key
            key_parts = [func.__name__]
            key_parts.extend(str(arg) for arg in args)
            key_parts.extend(f"{k}:{v}" for k, v in sorted(kwargs.items()))
            key_string = "|".join(key_parts)
            cache_key = hashlib.md5(key_string.encode()).hexdigest()
            
            # Try to get from cache
            cached_result = cache.get(cache_key)
            if cached_result is not None:
                logger.info(f"Cache hit for key: {cache_key}")
                return cached_result
            
            # Execute function and cache result
            result = func(*args, **kwargs)
            cache.set(cache_key, result, expiration)
            return result
            
        return wrapper
    return decorator