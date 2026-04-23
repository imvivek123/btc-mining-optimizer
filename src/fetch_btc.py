# src/fetch_btc.py
"""
Fetch live Bitcoin price, network statistics, and compute mining earnings.
Uses CoinGecko API (free tier, no authentication needed).
"""

import logging
from typing import Dict, Tuple
from pycoingecko import CoinGeckoAPI
import config

logger = logging.getLogger(__name__)


def fetch_btc_price_usd() -> float:
    """
    Fetch current Bitcoin price in USD from CoinGecko.
    
    Returns:
        float: Current BTC price in USD
        
    Fallback: Returns config.BTC_PRICE_USD if API fails
    """
    try:
        cg = CoinGeckoAPI()
        price_data = cg.get_price(ids='bitcoin', vs_currencies='usd')
        price = price_data['bitcoin']['usd']
        logger.info(f"Fetched BTC price: ${price:,.2f}")
        return price
    except Exception as e:
        logger.warning(f"Failed to fetch BTC price from CoinGecko: {e}. Using fallback: ${config.BTC_PRICE_USD:,.2f}")
        return config.BTC_PRICE_USD


def fetch_network_stats() -> Dict[str, float]:
    """
    Fetch Bitcoin network statistics from CoinGecko.
    
    Returns:
        dict: {
            "btc_price_usd": float,
            "difficulty": float,
            "market_cap_usd": float,
            "total_volume_usd": float,
            "block_reward": float
        }
    """
    try:
        cg = CoinGeckoAPI()
        bitcoin_data = cg.get_coin_by_id('bitcoin', localization=False)
        
        btc_price = bitcoin_data['market_data']['current_price']['usd']
        market_cap = bitcoin_data['market_data']['market_cap']['usd']
        total_volume = bitcoin_data['market_data']['total_volume']['usd']
        
        logger.info(f"Fetched network stats - Price: ${btc_price:,.2f}, Market Cap: ${market_cap:,.0f}")
        
        return {
            "btc_price_usd": btc_price,
            "difficulty": config.NETWORK_DIFFICULTY,  # CoinGecko doesn't provide this
            "market_cap_usd": market_cap,
            "total_volume_usd": total_volume,
            "block_reward": config.BLOCK_REWARD_BTC
        }
    except Exception as e:
        logger.warning(f"Failed to fetch network stats: {e}. Using fallback values.")
        return {
            "btc_price_usd": config.BTC_PRICE_USD,
            "difficulty": config.NETWORK_DIFFICULTY,
            "market_cap_usd": 0,
            "total_volume_usd": 0,
            "block_reward": config.BLOCK_REWARD_BTC
        }


def compute_daily_btc_earnings(hashrate_th: float, difficulty: float, btc_price_usd: float) -> float:
    """
    Compute expected daily Bitcoin earnings for a given hashrate.
    
    Formula:
        daily_btc = (hashrate_th * 1e12 * 86400) / (difficulty * 2^32) * BLOCK_REWARD_BTC
        daily_usd = daily_btc * btc_price_usd
    
    Args:
        hashrate_th: Total hashrate in terahashes per second
        difficulty: Current network difficulty
        btc_price_usd: Current BTC price in USD
        
    Returns:
        float: Expected daily earnings in USD
    """
    try:
        # Convert TH/s to H/s
        hashrate_hs = hashrate_th * 1e12
        
        # Expected hashes to find one block: difficulty * 2^32
        hashes_per_block = difficulty * (2 ** 32)
        
        # Expected blocks per day
        blocks_per_day = (hashrate_hs * 86400) / hashes_per_block
        
        # Daily BTC earnings
        daily_btc = blocks_per_day * config.BLOCK_REWARD_BTC
        
        # Daily USD earnings
        daily_usd_earnings = daily_btc * btc_price_usd
        
        logger.info(f"Daily earnings: {daily_btc:.6f} BTC = ${daily_usd_earnings:,.2f}")
        
        return daily_usd_earnings
    except Exception as e:
        logger.error(f"Error computing daily earnings: {e}")
        return 0.0


def compute_hourly_btc_earnings(hashrate_th: float, difficulty: float, btc_price_usd: float) -> float:
    """
    Compute expected hourly Bitcoin earnings. Helper function.
    
    Args:
        hashrate_th: Total hashrate in terahashes per second
        difficulty: Current network difficulty
        btc_price_usd: Current BTC price in USD
        
    Returns:
        float: Expected hourly earnings in USD
    """
    daily_earnings = compute_daily_btc_earnings(hashrate_th, difficulty, btc_price_usd)
    return daily_earnings / 24


if __name__ == "__main__":
    # Test the functions
    print("\n=== Bitcoin Data Fetcher ===\n")
    
    # Fetch BTC price
    btc_price = fetch_btc_price_usd()
    print(f"Current BTC Price: ${btc_price:,.2f}\n")
    
    # Fetch network stats
    stats = fetch_network_stats()
    print("Network Statistics:")
    for key, value in stats.items():
        print(f"  {key}: {value}")
    print()
    
    # Compute daily earnings
    total_hashrate = config.MINER_HASHRATE_TH * config.NUM_MINERS
    daily_earnings = compute_daily_btc_earnings(
        hashrate_th=total_hashrate,
        difficulty=stats["difficulty"],
        btc_price_usd=stats["btc_price_usd"]
    )
    hourly_earnings = daily_earnings / 24
    
    print(f"Total Hashrate: {total_hashrate:.0f} TH/s")
    print(f"Daily Earnings: ${daily_earnings:,.2f}")
    print(f"Hourly Earnings: ${hourly_earnings:,.2f}\n")
