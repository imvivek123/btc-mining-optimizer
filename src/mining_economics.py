# src/mining_economics.py
"""
Core financial engine for mining profitability calculations.
Computes revenue, costs, and profit margins for each hour of operation.
"""

import logging
import pandas as pd
from typing import Dict
import config
from src.fetch_btc import compute_daily_btc_earnings
from src.fetch_energy_price import get_effective_energy_cost

logger = logging.getLogger(__name__)


def compute_hourly_economics(btc_stats: dict, energy_price_row: pd.Series, renewable_score: float) -> Dict:
    """
    Compute hourly mining economics: revenue, costs, and profit.
    
    Args:
        btc_stats: Dict with 'btc_price_usd' and 'difficulty'
        energy_price_row: pd.Series with 'price_jpy_kwh'
        renewable_score: Current renewable availability (0-1)
        
    Returns:
        dict with keys:
            - gross_revenue_usd: Before pool fees
            - net_revenue_usd: After pool fees
            - energy_cost_usd: Hourly energy cost
            - profit_usd: Net profit
            - profit_margin_pct: Profit margin percentage
            - efficiency_ratio: Revenue / Cost ratio
            - effective_cost_usd_kwh: Cost per kWh after renewable discount
            - renewable_discount_applied: Whether discount was applied
    """
    try:
        # --- Revenue Calculation ---
        
        # Total hashrate
        total_hashrate_th = config.MINER_HASHRATE_TH * config.NUM_MINERS
        
        # Daily earnings in USD
        daily_earnings_usd = compute_daily_btc_earnings(
            hashrate_th=total_hashrate_th,
            difficulty=btc_stats.get('difficulty', config.NETWORK_DIFFICULTY),
            btc_price_usd=btc_stats.get('btc_price_usd', config.BTC_PRICE_USD)
        )
        
        # Hourly gross revenue
        gross_revenue_usd = daily_earnings_usd / 24
        
        # Apply pool fee
        net_revenue_usd = gross_revenue_usd * (1 - config.POOL_FEE_PERCENT / 100)
        
        # --- Cost Calculation ---
        
        # Get spot price
        price_jpy_kwh = energy_price_row.get('price_jpy_kwh', config.ELECTRICITY_COST_JPY_KWH)
        
        # Apply renewable discount
        effective_cost_usd_kwh = get_effective_energy_cost(
            price_jpy_kwh=price_jpy_kwh,
            renewable_score=renewable_score
        )
        
        # Check if discount was applied
        renewable_discount_applied = renewable_score >= config.RENEWABLE_AVAILABILITY_THRESHOLD
        
        # Total power consumption
        total_power_kw = config.MINER_POWER_KW * config.NUM_MINERS
        
        # Hourly energy cost
        hourly_energy_cost_usd = total_power_kw * effective_cost_usd_kwh
        
        # --- Profitability ---
        
        # Profit calculation
        profit_usd = net_revenue_usd - hourly_energy_cost_usd
        
        # Profit margin percentage
        if net_revenue_usd > 0:
            profit_margin_pct = (profit_usd / net_revenue_usd) * 100
        else:
            profit_margin_pct = 0.0
        
        # Efficiency ratio
        if hourly_energy_cost_usd > 0:
            efficiency_ratio = net_revenue_usd / hourly_energy_cost_usd
        else:
            efficiency_ratio = 0.0
        
        result = {
            "gross_revenue_usd": gross_revenue_usd,
            "net_revenue_usd": net_revenue_usd,
            "energy_cost_usd": hourly_energy_cost_usd,
            "profit_usd": profit_usd,
            "profit_margin_pct": profit_margin_pct,
            "efficiency_ratio": efficiency_ratio,
            "effective_cost_usd_kwh": effective_cost_usd_kwh,
            "renewable_discount_applied": renewable_discount_applied,
            "total_hashrate_th": total_hashrate_th,
            "total_power_kw": total_power_kw
        }
        
        return result
        
    except Exception as e:
        logger.error(f"Error computing hourly economics: {e}")
        return {
            "gross_revenue_usd": 0.0,
            "net_revenue_usd": 0.0,
            "energy_cost_usd": 0.0,
            "profit_usd": 0.0,
            "profit_margin_pct": 0.0,
            "efficiency_ratio": 0.0,
            "effective_cost_usd_kwh": 0.0,
            "renewable_discount_applied": False,
            "total_hashrate_th": 0.0,
            "total_power_kw": 0.0
        }


def compute_breakeven_btc_price(energy_cost_usd_kwh: float, daily_btc_at_1usd: float = None) -> float:
    """
    Calculate the BTC price at which mining breaks even (profit = 0).
    
    At breakeven: Revenue = Daily Energy Cost
    
    Args:
        energy_cost_usd_kwh: Energy cost in USD/kWh
        daily_btc_at_1usd: Daily BTC produced if 1 BTC = $1 USD (for scaling)
        
    Returns:
        float: Breakeven BTC price in USD
    """
    try:
        # Total power consumption (kW)
        total_power_kw = config.MINER_POWER_KW * config.NUM_MINERS
        
        # Daily energy cost in USD
        daily_energy_cost_usd = total_power_kw * 24 * energy_cost_usd_kwh
        
        # Daily BTC production (at $1/BTC)
        total_hashrate_th = config.MINER_HASHRATE_TH * config.NUM_MINERS
        
        if daily_btc_at_1usd is None:
            daily_btc_at_1usd = compute_daily_btc_earnings(
                hashrate_th=total_hashrate_th,
                difficulty=config.NETWORK_DIFFICULTY,
                btc_price_usd=1.0  # Normalized
            )
        
        # Breakeven BTC price (accounting for pool fee)
        if daily_btc_at_1usd > 0:
            pool_fee_factor = (1 - config.POOL_FEE_PERCENT / 100)
            breakeven_price = daily_energy_cost_usd / (daily_btc_at_1usd * pool_fee_factor)
        else:
            breakeven_price = float('inf')
        
        logger.info(f"Breakeven BTC price: ${breakeven_price:,.2f}")
        
        return breakeven_price
        
    except Exception as e:
        logger.error(f"Error computing breakeven price: {e}")
        return float('inf')


def summarize_economics_dataframe(df: pd.DataFrame) -> Dict:
    """
    Generate summary statistics from an economics results dataframe.
    
    Args:
        df: DataFrame with economics results (output from compute_hourly_economics applied to all rows)
        
    Returns:
        dict: Summary statistics
    """
    if df.empty:
        return {}
    
    profitable_hours = (df['profit_usd'] > 0).sum()
    
    return {
        "total_hours": len(df),
        "profitable_hours": profitable_hours,
        "pct_profitable": (profitable_hours / len(df)) * 100 if len(df) > 0 else 0,
        "total_profit_usd": df['profit_usd'].sum(),
        "total_revenue_usd": df['net_revenue_usd'].sum(),
        "total_energy_cost_usd": df['energy_cost_usd'].sum(),
        "avg_profit_per_hour": df['profit_usd'].mean(),
        "max_profit_hour": df['profit_usd'].max(),
        "min_profit_hour": df['profit_usd'].min(),
        "avg_efficiency_ratio": df['efficiency_ratio'].mean(),
        "hours_with_renewable_discount": (df['renewable_discount_applied']).sum(),
    }


if __name__ == "__main__":
    # Test the functions
    print("\n=== Mining Economics Calculator ===\n")
    
    # Create test data
    btc_stats = {
        "btc_price_usd": 67000,
        "difficulty": config.NETWORK_DIFFICULTY
    }
    
    energy_price_row = pd.Series({
        "price_jpy_kwh": 15.0
    })
    
    renewable_score = 0.75
    
    # Compute economics
    econ = compute_hourly_economics(btc_stats, energy_price_row, renewable_score)
    
    print("Hourly Economics:")
    print(f"  Gross Revenue:         ${econ['gross_revenue_usd']:>8.2f}")
    print(f"  Pool Fee (2%):         ${econ['gross_revenue_usd'] - econ['net_revenue_usd']:>8.2f}")
    print(f"  Net Revenue:           ${econ['net_revenue_usd']:>8.2f}")
    print(f"  Energy Cost:           ${econ['energy_cost_usd']:>8.2f}")
    print(f"  Profit (Loss):         ${econ['profit_usd']:>8.2f}")
    print(f"  Profit Margin:         {econ['profit_margin_pct']:>8.1f}%")
    print(f"  Efficiency Ratio:      {econ['efficiency_ratio']:>8.2f}x")
    print(f"  Renewable Discount:    {econ['renewable_discount_applied']}")
    print()
    
    # Compute breakeven
    breakeven = compute_breakeven_btc_price(econ['effective_cost_usd_kwh'])
    print(f"Breakeven BTC Price: ${breakeven:,.2f}")
    print(f"Current Price: ${btc_stats['btc_price_usd']:,.2f}")
    print(f"Margin to Breakeven: {((btc_stats['btc_price_usd'] - breakeven) / breakeven * 100):>6.1f}%")
