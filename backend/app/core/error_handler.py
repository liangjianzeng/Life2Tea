"""
error_handler.py — Unified Error Handling and Logging Utilities

Provides decorators and utilities for consistent error handling and logging across the application.
Replaces print() statements with structured logger calls and proper exception propagation.
"""

import functools
import traceback
from typing import Callable, Any, Optional
from loguru import logger


def safe_api_call(
    default: Any = None,
    log_error: bool = True,
    message: str = "",
):
    """
    Decorator for API endpoints to handle exceptions and return consistent responses.
    
    Usage:
        @router.get("/endpoint")
        @safe_api_call(default={})
        async def my_endpoint(...):
            ...
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            try:
                result = await func(*args, **kwargs) if asyncio.iscoroutinefunction(func) else func(*args, **kwargs)
                return result
            except Exception as e:
                if log_error:
                    logger.error(f"{message or func.__name__} failed: {e}\n{traceback.format_exc()}")
                raise
        return wrapper
    return decorator


def log_function_call(level: str = "info"):
    """
    Decorator to log function calls with arguments and return values.
    
    Usage:
        @log_function_call()
        def my_function(param1, param2):
            ...
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            logger.log(level, f"CALL {func.__name__} args={args[1:] if args else ''}, kwargs={kwargs}")
            try:
                result = await func(*args, **kwargs)
                logger.log(level, f"RETURN {func.__name__} -> {result}")
                return result
            except Exception as e:
                logger.error(f"EXCEPTION {func.__name__}: {e}\n{traceback.format_exc()}")
                raise
        
        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            logger.log(level, f"CALL {func.__name__} args={args[1:] if args else ''}, kwargs={kwargs}")
            try:
                result = func(*args, **kwargs)
                logger.log(level, f"RETURN {func.__name__} -> {result}")
                return result
            except Exception as e:
                logger.error(f"EXCEPTION {func.__name__}: {e}\n{traceback.format_exc()}")
                raise
        
        return async_wrapper if asyncio.iscoroutinefunction(func) else sync_wrapper
    return decorator


def replace_print_with_logger(file_path: str):
    """
    Replace print() statements with logger calls in a file.
    
    Args:
        file_path: Path to the Python file to process
    
    Returns:
        Modified content string
    """
    import re
    
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Pattern for print statements
    # Match: print(f"...", flush=True) or print("...")
    pattern = r'print\((f?)"([^"]*)"(?:,\s*flush\s*=\s*True)?\)'
    
    def replace_print(match):
        prefix = match.group(1)
        message = match.group(2)
        
        # Convert f-string placeholders {var} to .format() style
        if prefix == 'f':
            # Extract variables from the string
            import re as regex
            vars_found = regex.findall(r'\{([^}]+)\}', message)
            
            # Build format string and args
            format_str = message.replace('{', '{:').replace('}', '}')  # Placeholder conversion
            if vars_found:
                return f'logger.info("{message}", {", ".join(vars_found)})'
        
        return f'logger.info("{message}")'
    
    new_content = re.sub(pattern, replace_print, content)
    
    return new_content


# Constants for consistent log messages
LOG_MESSAGES = {
    "START_PLUGIN": "Starting plugin: {}",
    "PLUGIN_STARTED": "Plugin started successfully: {}, PID={}",
    "PLUGIN_STOPPED": "Plugin stopped: {}",
    "LOAD_ERROR": "Failed to load plugin {}: {}",
    "UNLOAD_ERROR": "Failed to unload plugin {}: {}",
    "HTTP_ERROR": "HTTP request failed: {} {} -> {}",
    "DATABASE_ERROR": "Database operation failed: {}",
    "AUTH_FAILED": "Authentication failed for user: {}",
}
