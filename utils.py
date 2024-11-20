import os
from openai import OpenAI
from typing import List, Optional, Dict, Tuple, Any, Union, Generator
import requests
from bs4 import BeautifulSoup
import json
import logging
import re
from functools import lru_cache
from concurrent.futures import ThreadPoolExecutor, TimeoutError
import time
from threading import Lock, Event, RLock
from datetime import datetime, timedelta
import asyncio
import aiohttp
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from cache_utils import cache_with_redis
from flask import Response, stream_with_context
import queue
import threading
import shutil
from pathlib import Path
import stat
import hashlib
import redis

# Configure logging with more detailed format
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s - %(filename)s:%(lineno)d'
)
logger = logging.getLogger(__name__)

# OpenAI Configuration
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    logger.error("OpenAI API key is not configured")
    raise ValueError("OpenAI API key is required")

openai_client = OpenAI(api_key=OPENAI_API_KEY)

# Initialize Redis client with fallback to memory cache
try:
    redis_client = redis.from_url(os.environ.get("REDIS_URL", "redis://localhost:6379"))
    redis_client.ping()
    logger.info("Redis connected successfully for icon caching")
    USE_REDIS = True
except (redis.ConnectionError, redis.ResponseError) as e:
    logger.warning(f"Redis unavailable for icon caching, using memory cache: {str(e)}")
    USE_REDIS = False

# Memory cache for fallback
icon_cache = {}
CACHE_TIMEOUT = 3600  # 1 hour cache timeout

class IconCache:
    def __init__(self):
        self.memory_cache = {}
        self.cache_lock = RLock()

    def get_cache_key(self, module_name: str) -> str:
        """Generate a consistent cache key for a module name."""
        return f"icon_cache:{hashlib.md5(module_name.encode()).hexdigest()}"

    def get_icon(self, module_name: str) -> Optional[str]:
        """Get icon path from cache with Redis/memory fallback."""
        cache_key = self.get_cache_key(module_name)
        
        if USE_REDIS:
            try:
                cached_path = redis_client.get(cache_key)
                if cached_path:
                    logger.debug(f"Redis cache hit for {module_name}")
                    return cached_path.decode('utf-8')
            except Exception as e:
                logger.error(f"Redis error while getting icon: {str(e)}")
                
        with self.cache_lock:
            cached_item = self.memory_cache.get(cache_key)
            if cached_item:
                path, timestamp = cached_item
                if time.time() - timestamp < CACHE_TIMEOUT:
                    logger.debug(f"Memory cache hit for {module_name}")
                    return path
                else:
                    del self.memory_cache[cache_key]
        
        return None

    def set_icon(self, module_name: str, icon_path: str) -> None:
        """Store icon path in cache with Redis/memory fallback."""
        cache_key = self.get_cache_key(module_name)
        
        if USE_REDIS:
            try:
                redis_client.setex(cache_key, CACHE_TIMEOUT, icon_path)
                logger.debug(f"Icon cached in Redis for {module_name}")
                return
            except Exception as e:
                logger.error(f"Redis error while setting icon: {str(e)}")
        
        with self.cache_lock:
            self.memory_cache[cache_key] = (icon_path, time.time())
            logger.debug(f"Icon cached in memory for {module_name}")

    def clear_cache(self) -> None:
        """Clear both Redis and memory caches."""
        if USE_REDIS:
            try:
                keys = redis_client.keys("icon_cache:*")
                if keys:
                    redis_client.delete(*keys)
                logger.info("Redis icon cache cleared")
            except Exception as e:
                logger.error(f"Error clearing Redis cache: {str(e)}")
        
        with self.cache_lock:
            self.memory_cache.clear()
            logger.info("Memory icon cache cleared")

# Initialize the icon cache
icon_cache_manager = IconCache()

# Common module name variations with exact matches
MODULE_VARIATIONS = {
    'sales': ['sales.png', 'Sales.png', 'sale.png', 'crm.png'],
    'inventory': ['Inventory.png', 'stock.png', 'warehouse.png'],
    'purchase': ['Purchase.png', 'procurement.png'],
    'point_of_sale': ['pos.png', 'point_of_sale.png'],
    'project': ['project.png'],
    'employees': ['employees.png', 'employee.png', 'hr.png'],
    'timesheets': ['timesheet.png', 'timesheets.png'],
    'leaves': ['time_off.png', 'leave.png', 'leaves.png']
}

def normalize_module_name(module_name: str) -> str:
    """Normalize module name for icon matching."""
    try:
        logger.debug(f"Normalizing module name: {module_name}")
        
        if not module_name:
            logger.warning("Empty module name provided")
            return ""
            
        # Handle parentheses and special cases first
        name = re.sub(r'\s*\([^)]*\)', '', module_name)
        name = name.replace("Point of Sale (POS)", "point_of_sale")
        logger.debug(f"After removing parentheses: {name}")
        
        # Convert to lowercase
        name = name.lower()
        logger.debug(f"After lowercase conversion: {name}")
        
        # Remove common prefixes
        prefixes = ['odoo_', 'module_', 'app_', 'addon_']
        for prefix in prefixes:
            if name.startswith(prefix):
                name = name[len(prefix):]
                logger.debug(f"After removing prefix {prefix}: {name}")
        
        # Replace special characters and normalize spaces
        name = re.sub(r'[^a-z0-9]+', '_', name)
        name = re.sub(r'_+', '_', name)
        name = name.strip('_')
        logger.debug(f"After special character handling: {name}")
        
        return name
        
    except Exception as e:
        logger.error(f"Error normalizing module name {module_name}: {str(e)}", exc_info=True)
        return module_name.lower()

# Image queue with improved error handling and synchronization
image_queue = queue.Queue()
queue_lock = RLock()  # Using RLock for recursive locking capability
processed_items_lock = RLock()
queue_active = True
queue_event = Event()
queue_timeout = 30  # Timeout in seconds

# Shared state for processed items with thread-safe access
processed_items = set()
MAX_RETRIES = 3

def process_image_queue():
    """Background thread for processing image queue with improved error handling and retry mechanism."""
    global queue_active
    
    logger.info("Starting image queue processing thread")
    last_activity = time.time()
    
    def process_module_with_retry(module_name: str, callback: callable, max_retries: int = MAX_RETRIES) -> bool:
        """Process a single module with retry mechanism."""
        nonlocal last_activity
        
        for attempt in range(max_retries):
            try:
                logger.info(f"Processing module icon: {module_name} (attempt {attempt + 1}/{max_retries})")
                
                # Update activity timestamp
                last_activity = time.time()
                
                image_path = get_local_icon_path(module_name)
                module_url = f"https://apps.odoo.com/apps/modules/browse?search={module_name.lower().replace(' ', '-')}"
                
                info = {
                    'url': module_url,
                    'image': image_path
                }
                
                if callback:
                    callback(info)
                
                logger.info(f"Successfully processed module: {module_name}")
                return True
                
            except Exception as e:
                logger.error(f"Error processing module {module_name} (attempt {attempt + 1}): {str(e)}")
                if attempt < max_retries - 1:
                    time.sleep(1 * (attempt + 1))  # Exponential backoff
                    continue
                return False
    
    while queue_active:
        try:
            # Check for inactivity timeout
            if time.time() - last_activity > queue_timeout:
                logger.debug("Queue inactive, continuing to process")
                last_activity = time.time()
            
            task = image_queue.get(timeout=5)
            if task is None:
                logger.info("Received shutdown signal in image queue")
                break
            
            module_name, callback = task
            
            # Thread-safe check for already processed items
            with processed_items_lock:
                if module_name in processed_items:
                    logger.info(f"Module {module_name} already processed, skipping")
                    image_queue.task_done()
                    continue
            
            success = process_module_with_retry(module_name, callback)
            
            if success:
                # Thread-safe addition to processed set
                with processed_items_lock:
                    processed_items.add(module_name)
            
            # Signal task completion
            queue_event.set()
            image_queue.task_done()
            
        except queue.Empty:
            if time.time() - last_activity > queue_timeout:
                logger.debug("Queue timeout, resetting activity timer")
                last_activity = time.time()
            continue
        except Exception as e:
            logger.error(f"Error in image queue processing: {str(e)}", exc_info=True)
            try:
                image_queue.task_done()
            except ValueError:
                pass

# Start image processing thread
image_thread = threading.Thread(target=process_image_queue, daemon=True)
image_thread.start()

def get_local_icon_path(module_name: str) -> str:
    """Get the local icon path for a module with enhanced matching."""
    try:
        # Ensure module icons are in place
        ensure_module_icons_dir()
        
        # Log input module name
        logger.info(f"Finding icon for module: {module_name}")
        
        # Default icon path
        default_icon = "/static/images/default_module_icon.svg"
        
        # Special case handling for Point of Sale
        if "point of sale" in module_name.lower() or "pos" in module_name.lower():
            module_name = "point_of_sale"
        
        # Normalize the module name for matching
        normalized_name = normalize_module_name(module_name)
        logger.info(f"Normalized name for matching: {normalized_name}")
        
        icons_dir = Path("static/module_icons")
        if not icons_dir.exists():
            logger.error(f"Icons directory not found: {icons_dir}")
            return default_icon
        
        # Log all available icons
        all_icons = list(icons_dir.glob('*.png'))
        logger.info(f"Available icons ({len(all_icons)}): {[icon.name for icon in all_icons]}")
        
        # Try exact matches from MODULE_VARIATIONS first
        if normalized_name in MODULE_VARIATIONS:
            logger.info(f"Checking exact matches for {normalized_name}: {MODULE_VARIATIONS[normalized_name]}")
            for match in MODULE_VARIATIONS[normalized_name]:
                icon_path = icons_dir / match
                if icon_path.exists():
                    logger.info(f"Found exact match: {icon_path}")
                    return f"/static/module_icons/{match}"
        
        # Case-insensitive search for direct matches
        for icon_path in all_icons:
            if normalize_module_name(icon_path.stem) == normalized_name:
                logger.info(f"Found case-insensitive match: {icon_path}")
                return f"/static/module_icons/{icon_path.name}"
        
        # Try plural/singular forms
        singular = normalized_name.rstrip('s')
        plural = f"{normalized_name}s"
        
        logger.debug(f"Trying plural/singular forms - Singular: {singular}, Plural: {plural}")
        
        for icon_path in all_icons:
            icon_normalized = normalize_module_name(icon_path.stem)
            if icon_normalized in (singular, plural):
                logger.info(f"Found plural/singular match: {icon_path}")
                return f"/static/module_icons/{icon_path.name}"
        
        logger.warning(f"No suitable icon found for module {module_name}, using default")
        return default_icon
        
    except Exception as e:
        logger.error(f"Error finding local icon for {module_name}: {str(e)}", exc_info=True)
        return default_icon

def ensure_module_icons_dir():
    """Ensure the module_icons directory exists and contains all icons."""
    source_dir = Path("Images for Odoo Apps recomendor")  # Case-sensitive path
    target_dir = Path("static/module_icons")
    
    try:
        logger.info(f"Source directory: {source_dir.absolute()}")
        logger.info(f"Target directory: {target_dir.absolute()}")
        
        # Create target directory if it doesn't exist
        target_dir.mkdir(parents=True, exist_ok=True)
        
        # Set directory permissions (755)
        target_dir.chmod(stat.S_IRWXU | stat.S_IRGRP | stat.S_IXGRP | stat.S_IROTH | stat.S_IXOTH)
        logger.info(f"Created or verified target directory: {target_dir} with permissions")
        
        if not source_dir.exists():
            logger.error(f"Source directory not found: {source_dir}")
            return
            
        # Log available icons in source directory with normalized names
        source_icons = list(source_dir.glob('*.png'))
        logger.info(f"Source icons found: {len(source_icons)}")
        for icon in source_icons:
            logger.debug(f"Source icon: {icon.name} -> normalized: {normalize_module_name(icon.stem)}")
        
        # Track file operations
        copied_files = 0
        failed_files = 0
        skipped_files = 0
        retry_files = []
        
        for source_file in source_icons:
            target_file = target_dir / source_file.name
            try:
                if not target_file.exists():
                    shutil.copy2(source_file, target_file)
                    # Set file permissions (644)
                    target_file.chmod(stat.S_IRUSR | stat.S_IWUSR | stat.S_IRGRP | stat.S_IROTH)
                    logger.info(f"Copied file: {source_file.name} -> {target_file}")
                    copied_files += 1
                else:
                    logger.debug(f"Skipped existing file: {source_file.name}")
                    skipped_files += 1
            except Exception as e:
                logger.error(f"Failed to copy {source_file.name}: {str(e)}")
                failed_files += 1
                retry_files.append(source_file)
        
        # Retry failed copies
        if retry_files:
            logger.info(f"Retrying {len(retry_files)} failed copies...")
            for source_file in retry_files:
                try:
                    target_file = target_dir / source_file.name
                    if not target_file.exists():
                        shutil.copy2(source_file, target_file)
                        target_file.chmod(stat.S_IRUSR | stat.S_IWUSR | stat.S_IRGRP | stat.S_IROTH)
                        logger.info(f"Successfully retried copying: {source_file.name}")
                        copied_files += 1
                        failed_files -= 1
                except Exception as e:
                    logger.error(f"Retry failed for {source_file.name}: {str(e)}")
        
        # Verify final icon inventory
        final_icons = list(target_dir.glob('*.png'))
        logger.info(f"Final icon inventory: {len(final_icons)} files")
        for icon in final_icons:
            logger.debug(f"Available icon: {icon.name} -> normalized: {normalize_module_name(icon.stem)}")
        logger.info(f"Icon copy summary - Copied: {copied_files}, Skipped: {skipped_files}, Failed: {failed_files}")
        
    except Exception as e:
        logger.error(f"Error ensuring module icons directory: {str(e)}", exc_info=True)
        raise

# Updated system prompt as per requirements
SYSTEM_PROMPT = """Assist me in creating a system that accurately recommends Odoo apps based solely on user input and predefined requirements. Use the provided dataset of official Odoo modules and their descriptions to generate responses. Avoid suggesting unrelated or random Odoo modules that are not part of the dataset. Ensure that each recommendation is relevant to the user's input and linked to its correct functionality and description."""

# Image queue with improved error handling and synchronization
image_queue = queue.Queue()
queue_lock = RLock()  # Using RLock for recursive locking capability
processed_items_lock = RLock()
queue_active = True
queue_event = Event()

# Shared state for processed items with thread-safe access
processed_items = set()
MAX_RETRIES = 3

def process_image_queue():
    """Background thread for processing image queue with improved error handling and retry mechanism."""
    global queue_active
    
    logger.info("Starting image queue processing thread")
    
    def process_module_with_retry(module_name: str, callback: callable, max_retries: int = MAX_RETRIES) -> bool:
        """Process a single module with retry mechanism."""
        for attempt in range(max_retries):
            try:
                logger.info(f"Processing module icon: {module_name} (attempt {attempt + 1}/{max_retries})")
                
                image_path = get_local_icon_path(module_name)
                module_url = f"https://apps.odoo.com/apps/modules/browse?search={module_name.lower().replace(' ', '-')}"
                
                info = {
                    'url': module_url,
                    'image': image_path
                }
                
                if callback:
                    callback(info)
                
                logger.info(f"Successfully processed module: {module_name}")
                return True
                
            except Exception as e:
                logger.error(f"Error processing module {module_name} (attempt {attempt + 1}): {str(e)}")
                if attempt < max_retries - 1:
                    time.sleep(1 * (attempt + 1))  # Exponential backoff
                    continue
                return False
    
    while queue_active:
        try:
            # Use increased timeout to prevent premature exits
            task = image_queue.get(timeout=5)
            if task is None:
                logger.info("Received shutdown signal in image queue")
                break
            
            module_name, callback = task
            
            # Thread-safe check for already processed items
            with processed_items_lock:
                if module_name in processed_items:
                    logger.info(f"Module {module_name} already processed, skipping")
                    image_queue.task_done()
                    continue
            
            success = process_module_with_retry(module_name, callback)
            
            if success:
                # Thread-safe addition to processed set
                with processed_items_lock:
                    processed_items.add(module_name)
            
            # Signal task completion
            queue_event.set()
            image_queue.task_done()
            
        except queue.Empty:
            logger.debug("Image queue timeout, continuing to wait")
            continue
        except Exception as e:
            logger.error(f"Error in image queue processing: {str(e)}", exc_info=True)
            try:
                image_queue.task_done()
            except ValueError:
                pass

# Start image processing thread
image_thread = threading.Thread(target=process_image_queue, daemon=True)
image_thread.start()

@cache_with_redis(expiration=3600)  # Cache for 1 hour
def get_module_recommendations(
    requirements: str = "",
    industry: str = "",
    features: Optional[List[str]] = None,
    preferred_edition: str = "community",
    has_experience: str = "no",
    stream: bool = False
) -> Union[Dict[str, Any], Response]:
    """Get module recommendations with streaming support and optimizations."""
    try:
        if not OPENAI_API_KEY:
            logger.error("OpenAI API key is not configured")
            return {"error": "OpenAI API key is not configured"}

        context_parts = [
            f"Industry: {industry}" if industry else None,
            f"Features: {', '.join(features)}" if features else None,
            f"Edition: {preferred_edition.title()}" if preferred_edition else None,
            f"Experience: {'Yes' if has_experience == 'yes' else 'No'}",
            f"Requirements: {requirements}" if requirements else None
        ]
        
        context = "\n".join(filter(None, context_parts))
        prompt = f'''Recommend 4 Odoo modules for:\n{context}\n\nFormat:\nModule: [Name]\nDescription: [Core functionality]\nFeatures: [Key features]\nBenefits: [Value]'''

        if stream:
            return Response(
                stream_with_context(stream_openai_response(prompt)),
                content_type='text/event-stream'
            )

        response = openai_client.chat.completions.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt}
            ],
            temperature=0.2,
            max_tokens=1000
        )

        content = response.choices[0].message.content
        if not content:
            return {"error": "No recommendations generated"}

        modules = parse_module_response(content)
        if not modules:
            return {"error": "No valid recommendations found"}

        # Reset queue event before processing new batch
        queue_event.clear()
        
        module_info = {}
        for module in modules:
            try:
                image_queue.put(
                    (module['name'], lambda info, name=module['name']: module_info.update({name: info})),
                    timeout=5
                )
            except queue.Full:
                logger.warning(f"Image generation queue full, skipping image for {module['name']}")

        # Wait for all tasks to be processed with a timeout
        queue_event.wait(timeout=10)

        result = {
            'text': content,
            'modules': modules,
            'urls': {name: info['url'] for name, info in module_info.items()},
            'images': {name: info['image'] for name, info in module_info.items()}
        }

        return result

    except Exception as e:
        logger.error(f"Error generating recommendations: {str(e)}", exc_info=True)
        return {"error": f"Unable to generate recommendations: {str(e)}"}

def parse_module_response(content: str) -> List[Dict[str, str]]:
    """Parse the OpenAI response content into structured module data with improved error handling."""
    if not content or not isinstance(content, str):
        logger.error("Invalid content provided for parsing")
        return []
        
    modules = []
    try:
        pattern = r'(?:^|\n\n)(?:\d+\.|Module:)\s*(.*?)(?=(?:\n\n(?:\d+\.|Module:)|$))'
        sections = list(re.finditer(pattern, content, re.DOTALL))
        
        if not sections:
            return []
            
        with ThreadPoolExecutor(max_workers=min(4, len(sections))) as executor:
            futures = []
            for section in sections:
                futures.append(executor.submit(parse_section, section.group(1).strip()))
            
            for future in futures:
                try:
                    result = future.result(timeout=5)
                    if result:
                        modules.append(result)
                except TimeoutError:
                    logger.error("Timeout processing module section")
                    continue
                    
        return modules
        
    except Exception as e:
        logger.error(f"Error parsing module response: {str(e)}", exc_info=True)
        return []

def parse_section(section_text: str) -> Optional[Dict[str, str]]:
    """Parse a single module section with improved error handling."""
    try:
        lines = [line.strip() for line in section_text.split('\n') if line.strip()]
        if len(lines) < 2:
            return None
            
        module_name = re.sub(r'^(Module(?: Name)?:?\s*)', '', lines[0], flags=re.IGNORECASE)
        module_name = module_name.strip()
        
        description_lines = []
        features_lines = []
        benefits_lines = []
        current_section = description_lines
        
        for line in lines[1:]:
            lower_line = line.lower()
            if lower_line.startswith('features:'):
                current_section = features_lines
                line = re.sub(r'^Features:?\s*', '', line, flags=re.IGNORECASE)
            elif lower_line.startswith('benefits:'):
                current_section = benefits_lines
                line = re.sub(r'^Benefits:?\s*', '', line, flags=re.IGNORECASE)
            elif lower_line.startswith('description:'):
                current_section = description_lines
                line = re.sub(r'^Description:?\s*', '', line, flags=re.IGNORECASE)
            current_section.append(line)
        
        if module_name:
            return {
                'name': module_name,
                'description': ' '.join(description_lines),
                'features': features_lines,
                'benefits': benefits_lines
            }
        return None
    except Exception as e:
        logger.error(f"Error processing module section: {str(e)}", exc_info=True)
        return None

def stream_openai_response(prompt: str) -> Generator[str, None, None]:
    """Stream OpenAI API response with improved error handling."""
    try:
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt}
        ]
        
        response = openai_client.chat.completions.create(
            model="gpt-4",
            messages=messages,
            temperature=0.2,
            max_tokens=1000,
            stream=True
        )
        
        for chunk in response:
            if chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content
                
    except Exception as e:
        logger.error(f"Error streaming OpenAI response: {str(e)}", exc_info=True)
        yield json.dumps({"error": str(e)})

def get_local_icon_path(module_name: str) -> str:
    """Get the local icon path for a module with caching."""
    try:
        # Check cache first
        cached_path = icon_cache_manager.get_icon(module_name)
        if cached_path:
            logger.info(f"Cache hit for module {module_name}")
            return cached_path
            
        logger.info(f"Cache miss for module {module_name}, finding icon...")
        
        # Ensure module icons are in place
        ensure_module_icons_dir()
        
        # Default icon path
        default_icon = "/static/images/default_module_icon.svg"
        
        # Special case handling for Point of Sale
        if "point of sale" in module_name.lower() or "pos" in module_name.lower():
            module_name = "point_of_sale"
        
        # Normalize the module name for matching
        normalized_name = normalize_module_name(module_name)
        logger.info(f"Normalized name for matching: {normalized_name}")
        
        icons_dir = Path("static/module_icons")
        if not icons_dir.exists():
            logger.error(f"Icons directory not found: {icons_dir}")
            return default_icon
        
        icon_path = default_icon
        
        # Try exact matches from MODULE_VARIATIONS first
        if normalized_name in MODULE_VARIATIONS:
            logger.info(f"Checking exact matches for {normalized_name}: {MODULE_VARIATIONS[normalized_name]}")
            for match in MODULE_VARIATIONS[normalized_name]:
                potential_path = icons_dir / match
                if potential_path.exists():
                    icon_path = f"/static/module_icons/{match}"
                    break
        
        # If no match found, try case-insensitive search
        if icon_path == default_icon:
            for icon_file in icons_dir.glob('*.png'):
                if normalize_module_name(icon_file.stem) == normalized_name:
                    icon_path = f"/static/module_icons/{icon_file.name}"
                    break
        
        # Cache the result
        icon_cache_manager.set_icon(module_name, icon_path)
        logger.info(f"Icon path {icon_path} cached for module {module_name}")
        
        return icon_path
        
    except Exception as e:
        logger.error(f"Error finding local icon for {module_name}: {str(e)}", exc_info=True)
        return "/static/images/default_module_icon.svg"