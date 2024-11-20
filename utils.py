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

# Common module name variations with exact matches
MODULE_VARIATIONS = {
    'project': ['project.png'],
    'employees': ['employees.png', 'employee.png', 'hr.png'],
    'timesheets': ['timesheet.png', 'timesheets.png'],
    'leaves': ['time_off.png', 'leave.png', 'leaves.png'],
    'sales': ['sales.png', 'Sales.png', 'sale.png', 'crm.png', 'CRM.png'],
    'inventory': ['Inventory.png', 'stock.png', 'warehouse.png'],
    'purchase': ['Purchase.png', 'procurement.png'],
    'point_of_sale': ['pos.png', 'point_of_sale.png'],
}

def normalize_module_name(module_name: str) -> str:
    """Normalize module name for icon matching."""
    try:
        logger.debug(f"Normalizing module name: {module_name}")
        
        if not module_name:
            logger.warning("Empty module name provided")
            return ""
            
        # Handle parentheses in module names
        name = re.sub(r'\s*\([^)]*\)', '', module_name)
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

def get_local_icon_path(module_name: str) -> str:
    """Get the local icon path with enhanced logging."""
    try:
        # Log input module name
        logger.info(f"Finding icon for module: {module_name}")
        
        # Default icon path
        default_icon = "/static/images/default_module_icon.svg"
        
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
            variations = MODULE_VARIATIONS[normalized_name]
            logger.info(f"Found variations for {normalized_name}: {variations}")
            
            for match in variations:
                icon_path = icons_dir / match
                logger.debug(f"Checking exact match: {match}")
                if icon_path.exists():
                    logger.info(f"Found exact match: {icon_path}")
                    return f"/static/module_icons/{match}"
                logger.debug(f"No match found for: {match}")
        
        # Case-insensitive search
        for icon_path in all_icons:
            icon_name = icon_path.stem.lower()
            normalized_icon = normalize_module_name(icon_name)
            logger.debug(f"Checking icon: {icon_name} (normalized: {normalized_icon})")
            
            if normalized_icon == normalized_name:
                logger.info(f"Found case-insensitive match: {icon_path}")
                return f"/static/module_icons/{icon_path.name}"
        
        logger.warning(f"No icon found for {module_name}, using default")
        return default_icon
        
    except Exception as e:
        logger.error(f"Error finding icon for {module_name}: {str(e)}")
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
                logger.debug(f"Processing file: {source_file.name}")
                if not target_file.exists():
                    logger.info(f"Copying file: {source_file} -> {target_file}")
                    shutil.copy2(source_file, target_file)
                    # Set file permissions (644)
                    target_file.chmod(stat.S_IRUSR | stat.S_IWUSR | stat.S_IRGRP | stat.S_IROTH)
                    logger.info(f"Successfully copied file: {source_file.name} -> {target_file}")
                    copied_files += 1
                else:
                    # Verify file integrity
                    if os.path.getsize(source_file) == os.path.getsize(target_file):
                        logger.debug(f"Skipped existing file (verified): {source_file.name}")
                        skipped_files += 1
                    else:
                        logger.warning(f"File size mismatch, re-copying: {source_file.name}")
                        shutil.copy2(source_file, target_file)
                        target_file.chmod(stat.S_IRUSR | stat.S_IWUSR | stat.S_IRGRP | stat.S_IROTH)
                        copied_files += 1
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
                    logger.info(f"Retrying copy: {source_file} -> {target_file}")
                    if not target_file.exists():
                        shutil.copy2(source_file, target_file)
                        target_file.chmod(stat.S_IRUSR | stat.S_IWUSR | stat.S_IRGRP | stat.S_IROTH)
                        logger.info(f"Successfully retried copying: {source_file.name}")
                        copied_files += 1
                        failed_files -= 1
                except Exception as e:
                    logger.error(f"Retry failed for {source_file.name}: {str(e)}")
        
        # Verify sales.png specifically
        sales_icon = target_dir / "sales.png"
        if sales_icon.exists():
            logger.info(f"Verified sales.png exists at: {sales_icon}")
            logger.info(f"Sales icon size: {os.path.getsize(sales_icon)} bytes")
        else:
            logger.error("sales.png not found in target directory")
        
        # Verify final icon inventory
        final_icons = list(target_dir.glob('*.png'))
        logger.info(f"Final icon inventory: {len(final_icons)} files")
        for icon in final_icons:
            logger.debug(f"Available icon: {icon.name} -> normalized: {normalize_module_name(icon.stem)}")
        logger.info(f"Icon copy summary - Copied: {copied_files}, Skipped: {skipped_files}, Failed: {failed_files}")
        
    except Exception as e:
        logger.error(f"Error ensuring module icons directory: {str(e)}", exc_info=True)
        raise

# Image queue with improved error handling and synchronization
image_queue = queue.Queue()
queue_lock = RLock()  # Using RLock for recursive locking capability
processed_items_lock = RLock()
queue_active = True
queue_event = Event()

# Shared state for processed items with thread-safe access
processed_items = set()
MAX_RETRIES = 3
QUEUE_TIMEOUT = 2  # Reduced from 5 to 2 seconds

def process_image_queue():
    """Process image queue in batches with enhanced logging."""
    global queue_active, processed_items
    
    logger.info("Starting image queue processing thread")
    batch_size = 4  # Process up to 4 items at once
    
    while queue_active:
        try:
            batch = []
            # Collect batch of items
            try:
                while len(batch) < batch_size:
                    task = image_queue.get(timeout=QUEUE_TIMEOUT)
                    if task is None:
                        if batch:
                            break
                        else:
                            logger.info("Received shutdown signal in image queue")
                            return
                    batch.append(task)
            except queue.Empty:
                if not batch:
                    logger.debug("Image queue timeout, continuing to wait")
                    continue

            logger.info(f"Processing batch of {len(batch)} items")
            
            # Process batch
            for module_name, callback in batch:
                try:
                    logger.info(f"Processing module icon: {module_name}")
                    
                    image_path = get_local_icon_path(module_name)
                    module_url = f"https://apps.odoo.com/apps/modules/browse?search={module_name.lower().replace(' ', '-')}"
                    
                    info = {
                        'url': module_url,
                        'image': image_path
                    }
                    
                    if callback:
                        callback(info)
                    
                    with processed_items_lock:
                        processed_items.add(module_name)
                    
                    logger.info(f"Successfully processed module: {module_name}")
                    logger.debug(f"Icon path: {image_path}")
                    
                except Exception as e:
                    logger.error(f"Error processing module {module_name}: {str(e)}")
                finally:
                    image_queue.task_done()

            # Signal batch completion
            queue_event.set()
            
        except Exception as e:
            logger.error(f"Error in batch processing: {str(e)}", exc_info=True)
            # Ensure queue.task_done() is called for any remaining items
            for _ in range(len(batch)):
                try:
                    image_queue.task_done()
                except ValueError:
                    pass

def clear_queue():
    """Clear the image queue and processed items."""
    global processed_items
    logger.info("Clearing image queue and processed items")
    try:
        while True:
            image_queue.get_nowait()
            image_queue.task_done()
    except queue.Empty:
        pass
    
    with processed_items_lock:
        processed_items.clear()
    logger.info("Queue and processed items cleared")

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
    """Get module recommendations with enhanced queueing and logging."""
    try:
        if not OPENAI_API_KEY:
            logger.error("OpenAI API key is not configured")
            return {"error": "OpenAI API key is not configured"}

        # Clear existing queue before processing new request
        clear_queue()
        logger.info("Cleared existing queue before processing new recommendations")

        # Your existing OpenAI call logic here...
        # For now we'll simulate module recommendations
        modules = [
            {"name": "Sales", "description": "Sales management module"},
            {"name": "Project", "description": "Project management module"},
            {"name": "Inventory", "description": "Inventory management module"},
            {"name": "Purchase", "description": "Purchase management module"}
        ]

        # Queue all module icons at once
        logger.info(f"Preparing to queue {len(modules)} modules for icon processing")
        module_info = {}
        
        def update_module_info(info, module_name):
            module_info[module_name] = info
            logger.debug(f"Updated module info for {module_name}: {info}")

        # Queue all modules at once with callbacks
        for module in modules:
            module_name = module["name"]
            logger.debug(f"Queueing module for icon processing: {module_name}")
            image_queue.put((module_name, lambda info, name=module_name: update_module_info(info, name)))

        # Wait for all items to be processed
        logger.info("Waiting for all module icons to be processed...")
        image_queue.join()
        logger.info("All module icons have been processed")

        # Prepare response with processed module information
        response = {
            "modules": modules,
            "urls": {name: info.get("url", "") for name, info in module_info.items()},
            "images": {name: info.get("image", "") for name, info in module_info.items()}
        }

        return response

    except Exception as e:
        logger.error(f"Error in get_module_recommendations: {str(e)}", exc_info=True)
        return {"error": str(e)}

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