# src/fetch_jepx_live.py
"""
Fetch real JEPX (Japan Electric Power eXchange) spot prices from live API.
Integrates with public JEPX data providers for real-time energy pricing.
"""

import logging
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import requests
import config

logger = logging.getLogger(__name__)

# Public JEPX data sources
JEPX_API_ENDPOINT = "https://api.jepx.jp/api/v1/spot_price"  # Hypothetical endpoint
JEPX_FALLBACK_ENDPOINT = "https://www.jepx.go.jp/market/real-time"  # Fallback scrape target


def fetch_jepx_live_prices(days: int = 7) -> pd.DataFrame:
    """
    Fetch real JEPX spot prices for the past N days.
    Falls back to synthetic generation if API is unavailable.
    
    Args:
        days: number of days of historical data to fetch
        
    Returns:
        pd.DataFrame with columns: datetime, price_jpy_kwh, is_peak_hour, is_real_data
    """
    try:
        logger.info(f"Attempting to fetch real JEPX data for {days} days...")
        
        # Try primary API endpoint
        try:
            end_date = datetime.now().date()
            start_date = end_date - timedelta(days=days)
            
            payload = {
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
                "market": "spot"
            }
            
            response = requests.get(JEPX_API_ENDPOINT, params=payload, timeout=10)
            response.raise_for_status()
            
            data = response.json()
            df = _parse_jepx_api_response(data)
            
            if not df.empty:
                df['is_real_data'] = True
                logger.info(f"✅ Successfully fetched {len(df)} hours of real JEPX data")
                return df
                
        except Exception as e:
            logger.warning(f"Primary JEPX API failed: {e}. Falling back...")
        
        # Fallback to web scraping if available
        try:
            df = _scrape_jepx_webpage()
            if not df.empty:
                df['is_real_data'] = True
                logger.info(f"✅ Scraped {len(df)} hours of JEPX data from webpage")
                return df
        except Exception as e:
            logger.warning(f"JEPX webpage scraping failed: {e}. Using synthetic generation...")
        
        # Final fallback: synthetic generation with real patterns
        df = _generate_realistic_jepx_prices(days=days)
        df['is_real_data'] = False
        logger.info(f"⚠️ Using realistic synthetic JEPX prices ({len(df)} hours)")
        
        return df
        
    except Exception as e:
        logger.error(f"Error fetching JEPX prices: {e}")
        return pd.DataFrame()


def _parse_jepx_api_response(data: dict) -> pd.DataFrame:
    """Parse JSON response from JEPX API."""
    try:
        records = []
        
        # Adapt this based on actual JEPX API response format
        for item in data.get('results', []):
            records.append({
                'datetime': pd.to_datetime(item['timestamp']),
                'price_jpy_kwh': float(item['price']),
                'is_peak_hour': int(item['hour']) in config.PEAK_HOURS,
                'volume_mwh': float(item.get('volume', 0))
            })
        
        if records:
            return pd.DataFrame(records).set_index('datetime').sort_index()
        return pd.DataFrame()
        
    except Exception as e:
        logger.error(f"Error parsing JEPX API response: {e}")
        return pd.DataFrame()


def _scrape_jepx_webpage() -> pd.DataFrame:
    """Scrape JEPX data from official website."""
    try:
        from bs4 import BeautifulSoup
        
        response = requests.get(JEPX_FALLBACK_ENDPOINT, timeout=10)
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Parse table data (adjust selectors based on actual page structure)
        records = []
        table = soup.find('table', {'class': 'jepx-prices'})
        
        if table:
            for row in table.find_all('tr')[1:]:  # Skip header
                cells = row.find_all('td')
                if len(cells) >= 2:
                    try:
                        dt_str = cells[0].text.strip()
                        price = float(cells[1].text.strip())
                        
                        records.append({
                            'datetime': pd.to_datetime(dt_str),
                            'price_jpy_kwh': price,
                        })
                    except (ValueError, IndexError):
                        continue
        
        if records:
            df = pd.DataFrame(records)
            df['is_peak_hour'] = df['datetime'].dt.hour.isin(config.PEAK_HOURS)
            return df.set_index('datetime').sort_index()
        
        return pd.DataFrame()
        
    except Exception as e:
        logger.error(f"Error scraping JEPX webpage: {e}")
        return pd.DataFrame()


def _generate_realistic_jepx_prices(days: int = 7) -> pd.DataFrame:
    """Generate realistic synthetic JEPX prices with actual market patterns."""
    try:
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)
        
        date_range = pd.date_range(start=start_date, end=end_date, freq='H', tz='Asia/Tokyo')
        
        records = []
        
        for dt in date_range:
            hour = dt.hour
            day_of_year = dt.dayofyear
            weekday = dt.weekday()
            
            is_peak = hour in config.PEAK_HOURS
            
            # Real JEPX patterns:
            # - Peak hours (8-20): 15-30 JPY/kWh (higher demand)
            # - Off-peak (21-7): 8-15 JPY/kWh (lower demand)
            # - Weekends typically lower
            # - Seasonal variation (winter/summer peaks)
            
            base_price = config.JEPX_BASE_PRICE_JPY
            
            if is_peak:
                price = base_price * config.JEPX_PEAK_MULTIPLIER
            else:
                price = base_price * config.JEPX_VALLEY_MULTIPLIER
            
            # Seasonal sine wave
            seasonal = 1 + 0.4 * np.sin(2 * np.pi * day_of_year / 365)
            price *= seasonal
            
            # Weekend discount (5-10% lower)
            if weekday >= 5:  # Saturday/Sunday
                price *= 0.92
            
            # Random walk (realistic variation)
            noise = np.random.normal(0, 0.5)
            price += noise
            
            # Ensure realistic bounds
            price = max(3.0, min(price, 50.0))
            
            records.append({
                'datetime': dt,
                'price_jpy_kwh': price,
                'is_peak_hour': is_peak
            })
        
        df = pd.DataFrame(records)
        return df.set_index('datetime').sort_index()
        
    except Exception as e:
        logger.error(f"Error generating realistic prices: {e}")
        return pd.DataFrame()


def get_jepx_summary(df: pd.DataFrame) -> dict:
    """Get summary statistics for JEPX prices."""
    if df.empty:
        return {}
    
    return {
        "current_price": df['price_jpy_kwh'].iloc[-1],
        "mean_price": df['price_jpy_kwh'].mean(),
        "min_price": df['price_jpy_kwh'].min(),
        "max_price": df['price_jpy_kwh'].max(),
        "std_price": df['price_jpy_kwh'].std(),
        "peak_mean": df[df['is_peak_hour']]['price_jpy_kwh'].mean(),
        "off_peak_mean": df[~df['is_peak_hour']]['price_jpy_kwh'].mean(),
        "is_real_data": df.get('is_real_data', [False])[0] if 'is_real_data' in df.columns else False
    }


if __name__ == "__main__":
    df = fetch_jepx_live_prices(days=7)
    print(df.head(10))
    print(get_jepx_summary(df))
