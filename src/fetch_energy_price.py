# src/fetch_energy_price.py
"""
Generate and manage Japan Electric Power eXchange (JEPX) spot price data.
Models realistic hourly electricity prices with peak/off-peak patterns and seasonal variation.
"""

import logging
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import config

logger = logging.getLogger(__name__)


def generate_jepx_prices(start_date: str, end_date: str) -> pd.DataFrame:
    """
    Generate synthetic JEPX spot prices for a date range.
    
    Pattern:
    - Peak hours (8:00-20:00 JST): higher prices (multiplied by PEAK_MULTIPLIER)
    - Off-peak hours (21:00-7:00): lower prices (multiplied by VALLEY_MULTIPLIER)
    - Seasonal sine wave: prices higher in summer/winter, lower in spring/fall
    - Random noise for realistic variation
    
    Args:
        start_date: Start date string (YYYY-MM-DD)
        end_date: End date string (YYYY-MM-DD)
        
    Returns:
        pd.DataFrame with columns: datetime, price_jpy_kwh, is_peak_hour
    """
    try:
        # Generate hourly date range in JST
        start_dt = pd.to_datetime(start_date)
        end_dt = pd.to_datetime(end_date)
        
        date_range = pd.date_range(start=start_dt, end=end_dt, freq='H', tz='Asia/Tokyo')
        
        prices = []
        peak_hours = []
        
        for dt in date_range:
            hour = dt.hour
            day_of_year = dt.dayofyear
            
            # Determine if peak hour
            is_peak = hour in config.PEAK_HOURS
            
            # Base price
            base_price = config.JEPX_BASE_PRICE_JPY
            
            # Apply peak/valley multiplier
            if is_peak:
                hourly_price = base_price * config.JEPX_PEAK_MULTIPLIER
            else:
                hourly_price = base_price * config.JEPX_VALLEY_MULTIPLIER
            
            # Add seasonal variation (sine wave)
            # Higher prices in winter (day 0, 365) and summer (day ~180)
            seasonal_factor = 1 + 0.3 * np.sin(2 * np.pi * day_of_year / 365)
            hourly_price *= seasonal_factor
            
            # Add random noise
            noise = np.random.normal(0, 0.8)
            hourly_price += noise
            
            # Ensure minimum price
            hourly_price = max(hourly_price, 3.0)
            
            prices.append(hourly_price)
            peak_hours.append(is_peak)
        
        df = pd.DataFrame({
            'datetime': date_range,
            'price_jpy_kwh': prices,
            'is_peak_hour': peak_hours
        })
        
        logger.info(f"Generated JEPX prices for {len(df)} hours ({start_date} to {end_date})")
        logger.info(f"Price range: {df['price_jpy_kwh'].min():.2f} - {df['price_jpy_kwh'].max():.2f} JPY/kWh")
        
        return df
        
    except Exception as e:
        logger.error(f"Error generating JEPX prices: {e}")
        return pd.DataFrame()


def get_effective_energy_cost(price_jpy_kwh: float, renewable_score: float) -> float:
    """
    Calculate effective energy cost in USD/kWh after applying renewable discount.
    
    If renewable_score is high enough, apply a discount on the spot price.
    Then convert from JPY to USD.
    
    Args:
        price_jpy_kwh: Spot price in JPY/kWh
        renewable_score: Current renewable availability (0.0 - 1.0)
        
    Returns:
        float: Effective cost in USD/kWh
    """
    try:
        # Apply renewable discount if score exceeds threshold
        if renewable_score >= config.RENEWABLE_AVAILABILITY_THRESHOLD:
            effective_price_jpy = price_jpy_kwh * (1 - config.RENEWABLE_DISCOUNT)
            discount_applied = True
        else:
            effective_price_jpy = price_jpy_kwh
            discount_applied = False
        
        # Convert JPY to USD
        effective_price_usd = effective_price_jpy * config.JPY_TO_USD
        
        if discount_applied:
            logger.debug(f"Renewable discount applied: {price_jpy_kwh:.2f} JPY → {effective_price_jpy:.2f} JPY = ${effective_price_usd:.4f}/kWh")
        
        return effective_price_usd
        
    except Exception as e:
        logger.error(f"Error calculating effective energy cost: {e}")
        return price_jpy_kwh * config.JPY_TO_USD


def get_price_summary(df: pd.DataFrame) -> dict:
    """
    Generate summary statistics for a price dataframe.
    
    Args:
        df: DataFrame with price_jpy_kwh column
        
    Returns:
        dict: Summary statistics
    """
    if df.empty:
        return {}
    
    return {
        "mean_price": df['price_jpy_kwh'].mean(),
        "min_price": df['price_jpy_kwh'].min(),
        "max_price": df['price_jpy_kwh'].max(),
        "std_price": df['price_jpy_kwh'].std(),
        "peak_mean": df[df['is_peak_hour']]['price_jpy_kwh'].mean(),
        "off_peak_mean": df[~df['is_peak_hour']]['price_jpy_kwh'].mean(),
    }


if __name__ == "__main__":
    # Test the functions
    print("\n=== JEPX Energy Price Generator ===\n")
    
    # Generate 7 days of prices
    start = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')
    end = datetime.now().strftime('%Y-%m-%d')
    
    prices_df = generate_jepx_prices(start, end)
    
    print(f"Generated {len(prices_df)} hourly price points\n")
    
    # Show summary
    summary = get_price_summary(prices_df)
    print("Price Summary (JPY/kWh):")
    for key, value in summary.items():
        print(f"  {key}: {value:.2f}")
    print()
    
    # Show sample rows
    print("Sample prices:")
    print(prices_df.head(10).to_string(index=False))
    print()
    
    # Test effective cost with different renewable scores
    sample_price = prices_df['price_jpy_kwh'].iloc[0]
    print(f"Sample price: {sample_price:.2f} JPY/kWh")
    
    for renewable_score in [0.2, 0.4, 0.6, 0.8]:
        effective_cost = get_effective_energy_cost(sample_price, renewable_score)
        print(f"  Renewable score {renewable_score:.1f}: ${effective_cost:.4f}/kWh")
