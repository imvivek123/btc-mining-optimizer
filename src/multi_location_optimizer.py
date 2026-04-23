# src/multi_location_optimizer.py
"""
Multi-location mining optimizer - determines optimal mining locations.
Compares profitability across multiple cities/regions to maximize ROI.
"""

import logging
import pandas as pd
import numpy as np
from typing import Dict, List, Tuple
from datetime import datetime, timedelta
import config
from src.fetch_energy_price import get_effective_energy_cost
from src.fetch_renewable import fetch_renewable_availability
from src.mining_economics import compute_hourly_economics
from src.decision_engine import make_decision

logger = logging.getLogger(__name__)

# Location library with energy and renewable data
LOCATION_PROFILES = {
    "Tokyo": {
        "lat": 35.6762,
        "lon": 139.6503,
        "base_energy_cost_jpy": 15.0,
        "solar_capacity_mw": 1200,
        "wind_capacity_mw": 800,
        "cooling_factor": 1.15,  # City heat effect
        "fiber_latency_ms": 5,
        "facility_rent_usd_per_kw_month": 0.12,
    },
    "Osaka": {
        "lat": 34.6937,
        "lon": 135.5024,
        "base_energy_cost_jpy": 14.5,
        "solar_capacity_mw": 900,
        "wind_capacity_mw": 600,
        "cooling_factor": 1.20,
        "fiber_latency_ms": 8,
        "facility_rent_usd_per_kw_month": 0.10,
    },
    "Hokkaido": {
        "lat": 43.0642,
        "lon": 141.3469,
        "base_energy_cost_jpy": 13.0,  # Cheaper (hydro)
        "solar_capacity_mw": 2000,
        "wind_capacity_mw": 3500,  # Strong winds
        "cooling_factor": 0.95,  # Natural cooling
        "fiber_latency_ms": 25,
        "facility_rent_usd_per_kw_month": 0.08,
    },
    "Fukuoka": {
        "lat": 33.5904,
        "lon": 130.4017,
        "base_energy_cost_jpy": 14.8,
        "solar_capacity_mw": 1100,
        "wind_capacity_mw": 1200,
        "cooling_factor": 1.10,
        "fiber_latency_ms": 12,
        "facility_rent_usd_per_kw_month": 0.09,
    },
}


def evaluate_location_profitability(
    location_name: str,
    btc_stats: dict,
    hashrate_th: float = config.MINER_HASHRATE_TH * config.NUM_MINERS,
    num_units: int = config.NUM_MINERS
) -> Dict:
    """
    Evaluate mining profitability at a specific location.
    
    Args:
        location_name: Location key from LOCATION_PROFILES
        btc_stats: Dict with btc_price_usd and difficulty
        hashrate_th: Total hashrate in TH/s
        num_units: Number of mining units
        
    Returns:
        dict with profitability metrics for the location
    """
    try:
        if location_name not in LOCATION_PROFILES:
            logger.warning(f"Location {location_name} not found")
            return {}
        
        profile = LOCATION_PROFILES[location_name]
        
        # Get renewable availability for this location
        renewable_data = fetch_renewable_availability(
            latitude=profile['lat'],
            longitude=profile['lon'],
            days=1
        )
        
        if renewable_data.empty:
            renewable_score = 0.3
        else:
            renewable_score = renewable_data['renewable_score'].mean()
        
        # Simulate energy cost with location multiplier
        base_cost = profile['base_energy_cost_jpy']
        # Adjust for cooling (heat effect increases cost)
        adjusted_cost = base_cost * profile['cooling_factor']
        
        # Create mock energy price row
        energy_row = pd.Series({'price_jpy_kwh': adjusted_cost})
        
        # Compute economics
        econ = compute_hourly_economics(btc_stats, energy_row, renewable_score)
        
        # Add facility costs
        miner_power_kw = config.MINER_POWER_KW * num_units
        facility_cost_usd_month = miner_power_kw * profile['facility_rent_usd_per_kw_month']
        facility_cost_usd_hour = facility_cost_usd_month / (30 * 24)  # Amortize
        
        total_profit_usd = econ.get('profit_usd', 0) - facility_cost_usd_hour
        
        # Network latency advantage (lower = faster blocks)
        latency_score = 1 - (profile['fiber_latency_ms'] / 50.0)  # Normalize 0-1
        
        return {
            'location': location_name,
            'renewable_score': renewable_score,
            'base_energy_cost_jpy': base_cost,
            'adjusted_energy_cost_jpy': adjusted_cost,
            'hourly_profit_usd': total_profit_usd,
            'hourly_revenue_usd': econ.get('gross_revenue_usd', 0),
            'hourly_cost_usd': econ.get('energy_cost_usd', 0) + facility_cost_usd_hour,
            'profit_margin_pct': (total_profit_usd / econ.get('gross_revenue_usd', 1) * 100) if econ.get('gross_revenue_usd', 0) > 0 else 0,
            'monthly_profit_usd': total_profit_usd * 24 * 30,
            'annual_profit_usd': total_profit_usd * 24 * 365,
            'renewable_capacity_mw': profile['solar_capacity_mw'] + profile['wind_capacity_mw'],
            'latency_ms': profile['fiber_latency_ms'],
            'latency_score': latency_score,
            'cooling_factor': profile['cooling_factor'],
        }
        
    except Exception as e:
        logger.error(f"Error evaluating {location_name}: {e}")
        return {}


def compare_all_locations(btc_stats: dict) -> pd.DataFrame:
    """
    Compare profitability across all available locations.
    
    Args:
        btc_stats: Dict with btc_price_usd and difficulty
        
    Returns:
        pd.DataFrame with location rankings
    """
    try:
        results = []
        
        for location in LOCATION_PROFILES.keys():
            eval_result = evaluate_location_profitability(location, btc_stats)
            if eval_result:
                results.append(eval_result)
        
        df = pd.DataFrame(results)
        df = df.sort_values('hourly_profit_usd', ascending=False)
        
        logger.info(f"Location comparison:\n{df[['location', 'hourly_profit_usd', 'renewable_score', 'latency_ms']].to_string()}")
        
        return df
        
    except Exception as e:
        logger.error(f"Error comparing locations: {e}")
        return pd.DataFrame()


def recommend_location_distribution(
    btc_stats: dict,
    total_hashrate_th: float
) -> Dict:
    """
    Recommend optimal hashrate distribution across locations.
    Allocates mining power based on profitability, redundancy, and resilience.
    
    Args:
        btc_stats: Dict with btc_price_usd and difficulty
        total_hashrate_th: Total hashrate available
        
    Returns:
        dict with distribution recommendations
    """
    try:
        df = compare_all_locations(btc_stats)
        
        if df.empty:
            return {'error': 'No locations available'}
        
        # Scoring: 50% profitability + 30% renewable + 20% latency
        df['score'] = (
            0.5 * (df['hourly_profit_usd'] / df['hourly_profit_usd'].max()) +
            0.3 * (df['renewable_score']) +
            0.2 * (df['latency_score'])
        )
        
        df['allocation_pct'] = df['score'] / df['score'].sum() * 100
        df['allocated_hashrate_th'] = df['allocation_pct'] / 100 * total_hashrate_th
        
        # Ensure minimum allocation (at least 10% for redundancy)
        min_allocation_th = total_hashrate_th * 0.1
        df['allocated_hashrate_th'] = df['allocated_hashrate_th'].clip(lower=min_allocation_th * 0.5)
        
        # Normalize to total
        df['allocated_hashrate_th'] = df['allocated_hashrate_th'] / df['allocated_hashrate_th'].sum() * total_hashrate_th
        
        recommendations = {}
        total_expected_profit = 0
        
        for _, row in df.iterrows():
            allocation = {
                'location': row['location'],
                'allocated_hashrate_th': row['allocated_hashrate_th'],
                'allocation_pct': row['allocation_pct'],
                'expected_hourly_profit': row['hourly_profit_usd'] * (row['allocated_hashrate_th'] / (config.MINER_HASHRATE_TH * config.NUM_MINERS)),
                'renewable_score': row['renewable_score'],
                'latency_ms': row['latency_ms'],
                'reason': f"{row['allocation_pct']:.1f}% allocated for optimal profitability and redundancy"
            }
            recommendations[row['location']] = allocation
            total_expected_profit += allocation['expected_hourly_profit']
        
        return {
            'recommendations': recommendations,
            'total_allocated_hashrate_th': total_hashrate_th,
            'expected_total_hourly_profit_usd': total_expected_profit,
            'expected_annual_profit_usd': total_expected_profit * 24 * 365,
            'summary': f"Distributed {total_hashrate_th:.1f} TH/s across {len(df)} locations for ${total_expected_profit:.2f}/hr profit"
        }
        
    except Exception as e:
        logger.error(f"Error recommending location distribution: {e}")
        return {'error': str(e)}


def get_location_stats() -> pd.DataFrame:
    """Get summary statistics for all locations."""
    data = []
    for name, profile in LOCATION_PROFILES.items():
        data.append({
            'location': name,
            'renewable_capacity_mw': profile['solar_capacity_mw'] + profile['wind_capacity_mw'],
            'base_energy_cost_jpy': profile['base_energy_cost_jpy'],
            'facility_rent_usd_per_kw_month': profile['facility_rent_usd_per_kw_month'],
            'latency_ms': profile['fiber_latency_ms'],
            'cooling_multiplier': profile['cooling_factor'],
        })
    return pd.DataFrame(data)


if __name__ == "__main__":
    import sys
    sys.path.insert(0, '/home/user/bitcoin')
    from src.fetch_btc import fetch_btc_price_usd, fetch_network_stats
    
    btc_stats = {
        'btc_price_usd': 65000,
        'difficulty': config.NETWORK_DIFFICULTY
    }
    
    # Compare locations
    comparison = compare_all_locations(btc_stats)
    print(comparison)
    
    # Get recommendation
    rec = recommend_location_distribution(btc_stats, total_hashrate_th=1000)
    print("\nRecommendation:", rec)
