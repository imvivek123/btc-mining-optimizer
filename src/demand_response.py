# src/demand_response.py
"""
Demand response pricing model for grid load management.
Tracks when grid operators pay miners to reduce or increase load for grid stability.
"""

import logging
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict
import config

logger = logging.getLogger(__name__)

# DR pricing tiers
DR_TIERS = {
    "level_0": {"name": "Normal", "price_adder_jpy": 0, "demand_reduction": 0},
    "level_1": {"name": "Moderate DR", "price_adder_jpy": -2, "demand_reduction": 0.1},
    "level_2": {"name": "Heavy DR", "price_adder_jpy": -5, "demand_reduction": 0.25},
    "level_3": {"name": "Critical DR", "price_adder_jpy": -10, "demand_reduction": 0.5},
    "level_minus_1": {"name": "Off-peak Incentive", "price_adder_jpy": 3, "demand_reduction": -0.3},  # Pay miners to use power
}


def simulate_grid_demand(timestamp: datetime, historical_avg: float = 100) -> Dict:
    """
    Simulate grid demand levels (as % of capacity).
    More realistic simulation would connect to grid operator data.
    
    Args:
        timestamp: Current time
        historical_avg: Average grid demand percentage (0-100)
        
    Returns:
        dict with demand metrics
    """
    try:
        hour = timestamp.hour
        day_of_week = timestamp.weekday()
        
        # Typical patterns:
        # Peak demand: 08:00-20:00 on weekdays
        # Off-peak: 21:00-07:00 and weekends
        
        base_demand = historical_avg
        
        # Hour factor
        if 8 <= hour <= 20:
            hour_factor = 1.1  # 10% higher during peak
        else:
            hour_factor = 0.7  # 30% lower off-peak
        
        # Weekday/weekend factor
        if day_of_week < 5:  # Weekday
            day_factor = 1.05
        else:  # Weekend
            day_factor = 0.9
        
        # Add daily variation (sine wave for realistic fluctuation)
        day_of_year = timestamp.dayofyear
        seasonal = 1 + 0.15 * np.sin(2 * np.pi * day_of_year / 365)
        
        # Random component
        random_factor = 1 + np.random.normal(0, 0.03)
        
        current_demand = base_demand * hour_factor * day_factor * seasonal * random_factor
        current_demand = np.clip(current_demand, 30, 120)  # Reasonable bounds
        
        # Relative to capacity (0-100%)
        demand_pct = current_demand % 100 if current_demand != 0 else 50
        
        return {
            'timestamp': timestamp,
            'demand_pct': demand_pct,
            'capacity_mw': 1000,  # Example national/regional capacity
            'current_mw': demand_pct * 10,  # Scaled for illustration
            'forecast_2h_pct': demand_pct * 1.05 + np.random.normal(0, 2),  # 2-hour forecast
        }
        
    except Exception as e:
        logger.error(f"Error simulating grid demand: {e}")
        return {}


def get_dr_level(demand_pct: float) -> str:
    """
    Determine demand response level based on grid demand percentage.
    
    Args:
        demand_pct: Grid demand as percentage of capacity (0-100)
        
    Returns:
        DR level string
    """
    if demand_pct < 60:
        return "level_minus_1"  # Low demand - incentivize more load
    elif demand_pct < 75:
        return "level_0"  # Normal
    elif demand_pct < 85:
        return "level_1"  # Moderate DR
    elif demand_pct < 95:
        return "level_2"  # Heavy DR
    else:
        return "level_3"  # Critical DR


def calculate_dr_incentive(
    base_price_jpy: float,
    demand_pct: float
) -> Dict:
    """
    Calculate demand response incentive (price adder/subtractor).
    
    Args:
        base_price_jpy: Base JEPX spot price
        demand_pct: Current grid demand percentage
        
    Returns:
        dict with adjusted pricing and incentive details
    """
    try:
        dr_level = get_dr_level(demand_pct)
        tier = DR_TIERS[dr_level]
        
        adjusted_price = base_price_jpy + tier['price_adder_jpy']
        adjusted_price = max(adjusted_price, 1.0)  # Ensure positive
        
        price_change_pct = ((adjusted_price - base_price_jpy) / base_price_jpy * 100) if base_price_jpy > 0 else 0
        
        return {
            'dr_level': dr_level,
            'dr_level_name': tier['name'],
            'base_price_jpy': base_price_jpy,
            'adjusted_price_jpy': adjusted_price,
            'price_change_pct': price_change_pct,
            'demand_reduction_target': tier['demand_reduction'],  # Miner should reduce load by this %
            'demand_pct': demand_pct,
            'is_incentivized': tier['price_adder_jpy'] > 0,  # True = grid pays miners to use power
            'is_disincentivized': tier['price_adder_jpy'] < 0,  # True = grid discounts miners to save power
        }
        
    except Exception as e:
        logger.error(f"Error calculating DR incentive: {e}")
        return {}


def calculate_dr_revenue(
    miner_power_kw: float,
    demand_reduction: float,
    energy_price_jpy: float,
    dr_coefficient: float = 0.1  # Payment rate for DR participation
) -> float:
    """
    Calculate additional revenue from demand response participation.
    
    Args:
        miner_power_kw: Power consumption of mining operation
        demand_reduction: Percentage of load to reduce (0.0-1.0)
        energy_price_jpy: Current energy price
        dr_coefficient: Payment multiplier for DR
        
    Returns:
        DR revenue in USD/hour
    """
    try:
        # Revenue = reducible_power * dr_incentive * energy_price
        reducible_power_kw = miner_power_kw * demand_reduction
        
        # DR payment is typically 10-20% of avoided energy cost
        dr_payment_jpy = reducible_power_kw * dr_coefficient * energy_price_jpy
        
        # Convert to USD
        dr_revenue_usd = dr_payment_jpy * config.JPY_TO_USD
        
        logger.debug(f"DR revenue: {reducible_power_kw:.2f} kW × {dr_coefficient} × {energy_price_jpy:.2f} = ${dr_revenue_usd:.4f}/hr")
        
        return dr_revenue_usd
        
    except Exception as e:
        logger.error(f"Error calculating DR revenue: {e}")
        return 0.0


def generate_dr_forecast(hours: int = 24) -> pd.DataFrame:
    """
    Generate 24-hour DR forecast.
    
    Args:
        hours: Number of hours to forecast
        
    Returns:
        pd.DataFrame with hourly DR predictions
    """
    try:
        now = datetime.utcnow()
        
        records = []
        for i in range(hours):
            ts = now + timedelta(hours=i)
            
            demand = simulate_grid_demand(ts, historical_avg=70)
            dr_info = calculate_dr_incentive(config.JEPX_BASE_PRICE_JPY, demand['demand_pct'])
            
            records.append({
                'hour': ts,
                'demand_pct': demand['demand_pct'],
                'dr_level': dr_info['dr_level'],
                'dr_level_name': dr_info['dr_level_name'],
                'adjusted_price_jpy': dr_info['adjusted_price_jpy'],
                'price_change_pct': dr_info['price_change_pct'],
                'recommended_action': 'REDUCE' if dr_info['is_disincentivized'] else ('INCREASE' if dr_info['is_incentivized'] else 'NORMAL'),
            })
        
        df = pd.DataFrame(records)
        logger.info(f"Generated {hours}-hour DR forecast")
        
        return df
        
    except Exception as e:
        logger.error(f"Error generating DR forecast: {e}")
        return pd.DataFrame()


if __name__ == "__main__":
    # Test DR simulation
    now = datetime.utcnow()
    demand = simulate_grid_demand(now)
    print(f"Current demand: {demand['demand_pct']:.1f}%")
    
    dr_info = calculate_dr_incentive(config.JEPX_BASE_PRICE_JPY, demand['demand_pct'])
    print(f"DR Level: {dr_info['dr_level_name']}")
    print(f"Price adjustment: {dr_info['price_change_pct']:+.1f}%")
    
    # Forecast
    forecast = generate_dr_forecast(24)
    print(f"\n24-hour DR Forecast:\n{forecast.head(10)}")
