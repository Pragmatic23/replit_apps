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

def ensure_module_icons_dir():
    """Ensure the module_icons directory exists and contains all icons."""
    source_dir = "Images for Odoo Apps recomendor"
    target_dir = "static/module_icons"
    
    try:
        if not os.path.exists(target_dir):
            os.makedirs(target_dir)
        
        # Copy all PNG files from source to target
        if os.path.exists(source_dir):
            copied_files = 0
            for file in os.listdir(source_dir):
                if file.lower().endswith('.png'):
                    source_file = os.path.join(source_dir, file)
                    target_file = os.path.join(target_dir, file)
                    if not os.path.exists(target_file):
                        shutil.copy2(source_file, target_file)
                        copied_files += 1
            logger.info(f"Copied {copied_files} icon files to {target_dir}")
    except Exception as e:
        logger.error(f"Error ensuring module icons directory: {str(e)}", exc_info=True)

def normalize_module_name(module_name: str) -> str:
    """Normalize module name for icon matching."""
    # Remove common prefixes
    name = module_name.lower()
    prefixes = ['odoo_', 'module_', 'app_', 'addon_']
    for prefix in prefixes:
        if name.startswith(prefix):
            name = name[len(prefix):]
    
    # Replace special characters
    name = name.replace(' ', '_').replace('-', '_')
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
        
        icons_dir = "static/module_icons"
        if not os.path.exists(icons_dir):
            logger.error(f"Icons directory not found: {icons_dir}")
            return default_icon
        
        # List of possible icon name variations
        possible_names = [
            f"{normalized_name}.png",
            f"{module_name.lower()}.png",
            f"{module_name}.png",
            # Additional variations
            f"odoo_{normalized_name}.png",
            f"module_{normalized_name}.png",
            f"{normalized_name}_icon.png"
        ]
        
        # Log all attempted matches
        logger.info(f"Attempting to match icon names: {possible_names}")
        
        # Check for exact matches first
        for icon_name in possible_names:
            icon_path = os.path.join(icons_dir, icon_name)
            if os.path.exists(icon_path):
                logger.info(f"Found exact match icon for module {module_name}: {icon_name}")
                return f"/static/module_icons/{icon_name}"
        
        # If no exact match, try fuzzy matching
        all_icons = os.listdir(icons_dir)
        logger.info(f"No exact match found. Trying fuzzy matching with {len(all_icons)} icons")
        
        for icon_file in all_icons:
            if icon_file.lower().endswith('.png'):
                base_name = os.path.splitext(icon_file)[0].lower()
                # Try matching parts of the name
                name_parts = normalized_name.split('_')
                for part in name_parts:
                    if len(part) > 3 and (part in base_name or base_name in part):
                        logger.info(f"Found fuzzy match icon for module {module_name}: {icon_file} (matched part: {part})")
                        return f"/static/module_icons/{icon_file}"
        
        logger.warning(f"No icon found for module {module_name}, using default")
        return default_icon
        
    except Exception as e:
        logger.error(f"Error finding local icon for {module_name}: {str(e)}", exc_info=True)
        return default_icon

def process_image_queue():
    """Background thread for processing image queue with improved error handling."""
    global queue_active
    
    logger.info("Starting image queue processing thread")
    
    while queue_active:
        try:
            # Use increased timeout to prevent premature exits
            task = image_queue.get(timeout=5)
            if task is None:
                logger.info("Received shutdown signal in image queue")
                break
            
            module_name, callback = task
            logger.info(f"Processing module icon: {module_name}")
            
            # Thread-safe check for already processed items
            with processed_items_lock:
                if module_name in processed_items:
                    logger.info(f"Module {module_name} already processed, skipping")
                    image_queue.task_done()
                    continue
            
            try:
                image_path = get_local_icon_path(module_name)
                module_url = f"https://apps.odoo.com/apps/modules/browse?search={module_name.lower().replace(' ', '-')}"
                
                info = {
                    'url': module_url,
                    'image': image_path
                }
                
                if callback:
                    callback(info)
                
                # Thread-safe addition to processed set
                with processed_items_lock:
                    processed_items.add(module_name)
                    logger.info(f"Successfully processed module: {module_name}")
                
                # Signal task completion
                queue_event.set()
                image_queue.task_done()
                
            except Exception as e:
                logger.error(f"Error processing module {module_name}: {str(e)}", exc_info=True)
                # Ensure task_done is called even on error
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