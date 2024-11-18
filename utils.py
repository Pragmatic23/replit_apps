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
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s - %(filename)s:%(lineno)d'
)
logger = logging.getLogger(__name__)

# OpenAI Configuration
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    logger.error("OpenAI API key is not configured")
    raise ValueError("OpenAI API key is required")

openai_client = OpenAI(api_key=OPENAI_API_KEY)

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

# Common module name variations
MODULE_VARIATIONS = {
    'leaves': ['leave', 'time_off', 'holidays'],
    'timesheets': ['timesheet', 'time_tracking', 'time_management'],
    'employees': ['employee', 'hr', 'human_resources'],
    'projects': ['project', 'tasks', 'task_management'],
    'sales': ['sale', 'selling', 'crm'],
    'inventory': ['stock', 'warehouse', 'inventories'],
    'purchases': ['purchase', 'procurement', 'buying'],
    'accounting': ['account', 'finance', 'invoicing']
}

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
            
        # Log available icons in source directory
        source_icons = list(source_dir.glob('*.png'))
        logger.debug(f"Available icons in source directory: {[icon.name for icon in source_icons]}")
        
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
        
        # Log final icon inventory
        final_icons = list(target_dir.glob('*.png'))
        logger.info(f"Final icon inventory: {len(final_icons)} files")
        logger.debug(f"Available icons after copy: {[icon.name for icon in final_icons]}")
        logger.info(f"Icon copy summary - Copied: {copied_files}, Skipped: {skipped_files}, Failed: {failed_files}")
        
    except Exception as e:
        logger.error(f"Error ensuring module icons directory: {str(e)}", exc_info=True)
        raise

def get_name_variations(module_name: str) -> List[str]:
    """Get all possible variations of a module name."""
    normalized = module_name.lower()
    variations = {normalized}
    
    # Add common variations
    if normalized in MODULE_VARIATIONS:
        variations.update(MODULE_VARIATIONS[normalized])
    
    # Handle plural/singular forms
    if normalized.endswith('s'):
        variations.add(normalized[:-1])  # Remove 's'
    else:
        variations.add(f"{normalized}s")  # Add 's'
    
    # Handle common suffixes
    suffixes = ['_management', '_module', '_app', '_system']
    for suffix in suffixes:
        if normalized.endswith(suffix):
            variations.add(normalized[:-len(suffix)])
        else:
            variations.add(f"{normalized}{suffix}")
    
    logger.debug(f"Generated variations for {module_name}: {variations}")
    return list(variations)

def get_match_score(name1: str, name2: str) -> float:
    """Calculate match score between two module names."""
    name1_parts = set(name1.lower().split('_'))
    name2_parts = set(name2.lower().split('_'))
    
    # Remove common words that don't add meaning
    common_words = {'module', 'app', 'system', 'management'}
    name1_parts = {part for part in name1_parts if part not in common_words}
    name2_parts = {part for part in name2_parts if part not in common_words}
    
    common_parts = name1_parts.intersection(name2_parts)
    
    if not name1_parts or not name2_parts:
        return 0
    
    # Calculate weighted Jaccard similarity
    similarity = len(common_parts) / max(len(name1_parts), len(name2_parts))
    
    # Boost score if one name contains the other
    if name1.lower() in name2.lower() or name2.lower() in name1.lower():
        similarity += 0.3
    
    return min(similarity, 1.0)

def normalize_module_name(module_name: str) -> str:
    """Normalize module name for icon matching."""
    # Remove common prefixes
    name = module_name.lower()
    prefixes = ['odoo_', 'module_', 'app_', 'addon_']
    for prefix in prefixes:
        if name.startswith(prefix):
            name = name[len(prefix):]
    
    # Replace special characters and normalize spaces
    name = re.sub(r'[^a-z0-9]+', '_', name.lower())
    name = re.sub(r'_+', '_', name)
    name = name.strip('_')
    
    logger.debug(f"Normalized module name: {module_name} -> {name}")
    return name

def get_local_icon_path(module_name: str) -> str:
    """Get the local icon path for a module with enhanced matching."""
    try:
        # Ensure module icons are in place
        ensure_module_icons_dir()
        
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
        
        # Direct matches based on module type
        exact_matches = {
            'employees': ['employees.png', 'employee.png', 'hr.png'],
            'timesheets': ['timesheet.png', 'timesheets.png', 'time_tracking.png'],
            'leaves': ['leave.png', 'leaves.png', 'time_off.png']
        }
        
        # Try exact matches first
        if normalized_name in exact_matches:
            logger.info(f"Checking exact matches for {normalized_name}: {exact_matches[normalized_name]}")
            for match in exact_matches[normalized_name]:
                icon_path = icons_dir / match
                if icon_path.exists():
                    logger.info(f"Found exact match: {icon_path}")
                    return f"/static/module_icons/{match}"
        
        # Get all possible name variations
        name_variations = get_name_variations(normalized_name)
        logger.info(f"Trying variations: {name_variations}")
        
        best_match = None
        best_score = 0
        match_details = []
        
        for icon_path in all_icons:
            icon_name = normalize_module_name(icon_path.stem)
            logger.debug(f"Checking icon: {icon_path.name} (normalized: {icon_name})")
            
            # Try exact matches first
            if icon_name in name_variations:
                logger.info(f"Found exact variation match: {icon_path}")
                return f"/static/module_icons/{icon_path.name}"
            
            # Calculate match score for each variation
            for variation in name_variations:
                match_score = get_match_score(variation, icon_name)
                match_details.append({
                    'icon': icon_path.name,
                    'variation': variation,
                    'score': match_score
                })
                
                if match_score > best_score:
                    best_score = match_score
                    best_match = icon_path
                    logger.debug(f"New best match: {icon_path.name} (score: {match_score})")
        
        # Log all attempted matches for debugging
        logger.debug(f"Match attempts: {json.dumps(match_details, indent=2)}")
        
        # Lower threshold to 0.2 for more permissive matching
        if best_match and best_score >= 0.2:
            logger.info(f"Using best match: {best_match.name} (score: {best_score})")
            return f"/static/module_icons/{best_match.name}"
        
        logger.warning(f"No suitable icon found for module {module_name}, using default")
        return default_icon
        
    except Exception as e:
        logger.error(f"Error finding local icon for {module_name}: {str(e)}", exc_info=True)
        return default_icon

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