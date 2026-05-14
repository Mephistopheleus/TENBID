"""Logger setup for TENBID with full signal marking"""
import logging
import sys
from datetime import datetime

def setup_logger(config):
    log_level = getattr(logging, config.get('LOGGING', 'level', fallback='INFO').upper())
    log_file = config.get('LOGGING', 'log_file', fallback='logs/tenbid.log')
    
    # Create logger
    logger = logging.getLogger('TENBID')
    logger.setLevel(log_level)
    logger.handlers.clear()
    
    # File handler
    file_handler = logging.FileHandler(log_file, mode='a', encoding='utf-8')
    file_handler.setLevel(log_level)
    
    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    
    # Format
    formatter = logging.Formatter(
        '%(asctime)s | %(levelname)-8s | %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    file_handler.setFormatter(formatter)
    console_handler.setFormatter(formatter)
    
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    
    return logger
