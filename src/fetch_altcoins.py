# src/fetch_altcoins.py
"""
Fetch and analyze mining profitability for alternative cryptocurrencies.
Supports Ethereum, Litecoin, Dogecoin, and other PoW coins as supplementary revenue streams.
"""

import logging
import pandas as pd
from typing import Dict, List
import requests
from datetime import datetime
import config

logger = logging.getLogger(__name__)

# CoinGecko API for multiple coins
COINGECKO_API = "https://api.coingecko.com/api/v3"

# Supported coins with mining parameters
MINEABLE_COINS = {
    "ethereum": {
        "id": "ethereum",
        "symbol": "eth",
        "block_time_sec": 12,
        "block_reward_native": 2.0,  # ETH per block (post-merge reference only - PoS now)
        "difficulty_adjustment": "auto",
        "active_pow": False  # Ethereum is PoS, but kept for reference
    },
    "litecoin": {
        "id": "litecoin",
        "symbol": "ltc",
        "block_time_sec": 150,
        "block_reward_native": 6.25,
        "difficulty_adjustment": "2016_blocks",
        "active_pow": True
    },
    "dogecoin": {
        "id": "dogecoin",
        "symbol": "doge",
        "block_time_sec": 60,
        "block_reward_native": 10000,
        "difficulty_adjustment": "every_block",
        "active_pow": True
    },
    "bitcoin-cash": {
        "id": "bitcoin-cash",
        "symbol": "bch",
        "block_time_sec": 600,
        "block_reward_native": 6.25,
        "difficulty_adjustment": "2016_blocks",
        "active_pow": True
    },
}


def fetch_altcoin_prices(coins: List[str] = None) -> Dict[str, Dict]:
    """
    Fetch current prices for mineable altcoins.
    
    Args:
        coins: List of coin names to fetch (default: all active PoW)
        
    Returns:
        dict mapping coin name to price data
    """
    if coins is None:
        coins = [c for c, meta in MINEABLE_COINS.items() if meta['active_pow']]
    
    try:
        ids = ",".join([MINEABLE_COINS[c]['id'] for c in coins if c in MINEABLE_COINS])
        
        url = f"{COINGECKO_API}/simple/price"
        params = {
            "ids": ids,
            "vs_currencies": "usd",
            "include_market_cap": "true",
            "include_24hr_vol": "true",
            "include_24hr_change": "true"
        }
        
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        
        data = response.json()
        
        prices = {}
        for coin in coins:
            if coin in MINEABLE_COINS:
                coin_id = MINEABLE_COINS[coin]['id']
                if coin_id in data:
                    prices[coin] = {
                        'price_usd': data[coin_id].get('usd', 0),
                        'market_cap': data[coin_id].get('usd_market_cap', 0),
                        '24h_volume': data[coin_id].get('usd_24h_vol', 0),
                        '24h_change': data[coin_id].get('usd_24h_change', 0),
                        'timestamp': datetime.utcnow().isoformat()
                    }
        
        logger.info(f"✅ Fetched prices for {len(prices)} altcoins")
        return prices
        
    except Exception as e:
        logger.error(f"Error fetching altcoin prices: {e}")
        return {}


def compute_altcoin_mining_yield(
    coin: str,
    hashrate_th: float,
    energy_cost_usd: float,
    difficulty: float = None
) -> Dict:
    """
    Compute mining profitability for a specific altcoin.
    
    Args:
        coin: Coin name (e.g., 'litecoin', 'dogecoin')
        hashrate_th: Hashrate in TH/s
        energy_cost_usd: Hourly energy cost in USD
        difficulty: Network difficulty (if None, fetch live)
        
    Returns:
        dict with profitability metrics
    """
    if coin not in MINEABLE_COINS:
        logger.warning(f"Coin {coin} not supported")
        return {}
    
    try:
        meta = MINEABLE_COINS[coin]
        
        # Skip non-PoW coins
        if not meta['active_pow']:
            logger.info(f"{coin} is not PoW, skipping")
            return {}
        
        # Fetch price if available
        prices = fetch_altcoin_prices([coin])
        if coin not in prices:
            logger.warning(f"Could not fetch price for {coin}")
            return {}
        
        price_usd = prices[coin]['price_usd']
        
        # Simplified yield calculation
        # Revenue = (hashrate * time) / difficulty * block_reward * price
        # This is a simplified version; real algorithms are more complex
        
        blocks_per_hour = 3600 / meta['block_time_sec']
        reward_per_hour = blocks_per_hour * meta['block_reward_native'] * price_usd
        
        # Rough efficiency (varies by coin ASIC efficiency)
        net_revenue_usd = reward_per_hour * (hashrate_th / 100.0)  # Normalized to 100 TH/s
        
        profit_usd = net_revenue_usd - energy_cost_usd
        profit_margin = (profit_usd / net_revenue_usd * 100) if net_revenue_usd > 0 else 0
        
        return {
            'coin': coin,
            'price_usd': price_usd,
            'hourly_revenue_usd': net_revenue_usd,
            'hourly_cost_usd': energy_cost_usd,
            'hourly_profit_usd': profit_usd,
            'profit_margin_pct': profit_margin,
            'blocks_per_hour': blocks_per_hour,
            'is_profitable': profit_usd > 0
        }
        
    except Exception as e:
        logger.error(f"Error computing {coin} mining yield: {e}")
        return {}


def recommend_optimal_coin(
    hashrate_th: float,
    energy_cost_usd: float,
    btc_profit: float
) -> Dict:
    """
    Recommend which coin to mine based on current profitability.
    
    Args:
        hashrate_th: Current hashrate in TH/s
        energy_cost_usd: Hourly energy cost
        btc_profit: Current BTC mining profit/hour
        
    Returns:
        dict with recommendation and comparison
    """
    try:
        active_coins = [c for c, m in MINEABLE_COINS.items() if m['active_pow']]
        
        recommendations = {
            'btc': btc_profit,  # BTC profit as baseline
        }
        
        for coin in active_coins:
            result = compute_altcoin_mining_yield(coin, hashrate_th, energy_cost_usd)
            if result:
                recommendations[coin] = result.get('hourly_profit_usd', 0)
        
        if not recommendations:
            return {'recommendation': 'BTC', 'reason': 'No altcoin data available'}
        
        best_coin = max(recommendations.items(), key=lambda x: x[1])[0]
        best_profit = recommendations[best_coin]
        
        if best_coin == 'btc':
            reason = f"BTC most profitable at ${btc_profit:.2f}/hr"
        else:
            profit_improvement = ((best_profit - btc_profit) / abs(btc_profit) * 100) if btc_profit != 0 else 0
            reason = f"{best_coin.upper()} is {profit_improvement:+.1f}% more profitable than BTC"
        
        return {
            'recommendation': best_coin.upper(),
            'recommended_profit': best_profit,
            'btc_profit': btc_profit,
            'reason': reason,
            'all_profits': recommendations
        }
        
    except Exception as e:
        logger.error(f"Error recommending coin: {e}")
        return {'recommendation': 'BTC', 'reason': 'Error in recommendation engine'}


if __name__ == "__main__":
    prices = fetch_altcoin_prices()
    print("Altcoin Prices:", prices)
    
    # Example: Compute LTC profitability
    ltc_yield = compute_altcoin_mining_yield('litecoin', hashrate_th=100, energy_cost_usd=1.5)
    print("\nLitecoin Yield:", ltc_yield)
    
    # Example: Get recommendation
    rec = recommend_optimal_coin(hashrate_th=100, energy_cost_usd=1.5, btc_profit=3.5)
    print("\nRecommendation:", rec)
