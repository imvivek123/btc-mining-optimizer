# src/utils.py
"""
Shared utility functions for logging, caching, and data formatting.
"""

import logging
import os
from datetime import datetime
import json
from typing import Any, Dict

# Set up logging
def setup_logging(level=logging.INFO):
    """
    Configure application-wide logging.
    
    Args:
        level: Logging level (e.g., logging.INFO, logging.DEBUG)
    """
    log_format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    logging.basicConfig(
        level=level,
        format=log_format,
        handlers=[
            logging.FileHandler('mining_simulator.log'),
            logging.StreamHandler()
        ]
    )


def format_usd(value: float) -> str:
    """Format a value as USD currency string."""
    return f"${value:,.2f}"


def format_percent(value: float, decimals: int = 1) -> str:
    """Format a value as percentage string."""
    return f"{value:.{decimals}f}%"


def format_btc(value: float, decimals: int = 8) -> str:
    """Format a value as BTC string."""
    return f"{value:.{decimals}f} BTC"


def format_hashrate(value_th: float) -> str:
    """Format hashrate in appropriate units."""
    if value_th >= 1000:
        return f"{value_th / 1000:.2f} PH/s"
    elif value_th >= 1:
        return f"{value_th:.2f} TH/s"
    else:
        return f"{value_th * 1000:.2f} GH/s"


def format_power(value_kw: float) -> str:
    """Format power in appropriate units."""
    if value_kw >= 1000:
        return f"{value_kw / 1000:.2f} MW"
    else:
        return f"{value_kw:.2f} kW"


def decision_to_emoji(decision: str) -> str:
    """Convert decision string to emoji."""
    emoji_map = {
        "GO": "🟢",
        "NO-GO": "🔴",
        "CAUTION": "🟡"
    }
    return emoji_map.get(decision, "⚫")


def decision_to_color(decision: str) -> str:
    """Convert decision string to hex color for charts."""
    color_map = {
        "GO": "#00AA00",           # Green
        "NO-GO": "#FF0000",        # Red
        "CAUTION": "#FFAA00"       # Yellow/Orange
    }
    return color_map.get(decision, "#808080")


def ensure_directory(path: str) -> bool:
    """
    Ensure a directory exists, creating it if necessary.
    
    Args:
        path: Directory path
        
    Returns:
        bool: True if successful
    """
    try:
        if not os.path.exists(path):
            os.makedirs(path, exist_ok=True)
        return True
    except Exception as e:
        logging.error(f"Error creating directory {path}: {e}")
        return False


def save_json(data: Dict, path: str) -> bool:
    """
    Save dictionary to JSON file.
    
    Args:
        data: Dictionary to save
        path: Output file path
        
    Returns:
        bool: True if successful
    """
    try:
        ensure_directory(os.path.dirname(path))
        with open(path, 'w') as f:
            json.dump(data, f, indent=2, default=str)
        logging.info(f"Saved JSON to {path}")
        return True
    except Exception as e:
        logging.error(f"Error saving JSON to {path}: {e}")
        return False


def load_json(path: str) -> Dict:
    """
    Load dictionary from JSON file.
    
    Args:
        path: Input file path
        
    Returns:
        dict: Loaded data or empty dict if failed
    """
    try:
        with open(path, 'r') as f:
            data = json.load(f)
        logging.info(f"Loaded JSON from {path}")
        return data
    except Exception as e:
        logging.error(f"Error loading JSON from {path}: {e}")
        return {}


def get_timestamp_str() -> str:
    """Get current timestamp as formatted string."""
    return datetime.now().strftime('%Y-%m-%d %H:%M:%S')


def get_filename_timestamp() -> str:
    """Get current timestamp suitable for filenames."""
    return datetime.now().strftime('%Y%m%d_%H%M%S')


if __name__ == "__main__":
    # Test utility functions
    print("\n=== Utility Functions Test ===\n")
    
    # Test formatting functions
    print("Formatting tests:")
    print(f"  USD: {format_usd(12345.67)}")
    print(f"  Percent: {format_percent(85.5)}")
    print(f"  BTC: {format_btc(1.23456789)}")
    print(f"  Hashrate: {format_hashrate(100)}")
    print(f"  Power: {format_power(3.25)}")
    print()
    
    # Test decision helpers
    print("Decision helpers:")
    for decision in ["GO", "NO-GO", "CAUTION"]:
        print(f"  {decision}: {decision_to_emoji(decision)} (color: {decision_to_color(decision)})")
    print()
    
    # Test timestamp
    print(f"Current timestamp: {get_timestamp_str()}")
    print(f"Filename timestamp: {get_filename_timestamp()}")
