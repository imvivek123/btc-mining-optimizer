# src/fetch_renewable.py
"""
Fetch renewable energy availability (solar and wind) from Open-Meteo API.
No authentication required — free tier allows up to 100 requests per day.
"""

import logging
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import openmeteo_requests
import requests_cache
import retry_requests
import config

logger = logging.getLogger(__name__)


def _setup_openmeteo_session():
    """
    Set up Open-Meteo API session with caching and retry logic.
    
    Returns:
        OpenMeteoSession: Configured session
    """
    # Setup the Open-Meteo API client with cache and retry on error
    cache_session = requests_cache.CachedSession('.cache', expire_after=3600)
    retry_session = retry_requests.Retry(retries=5, backoff_factor=0.2)
    openmeteo = openmeteo_requests.Client(session=cache_session, retry_session=retry_session)
    
    return openmeteo


def fetch_renewable_availability(latitude: float, longitude: float, days: int = 7) -> pd.DataFrame:
    """
    Fetch solar irradiance and wind speed from Open-Meteo API.
    Compute a composite renewable availability score (0-1).
    
    Parameters:
    - solar_norm = shortwave_radiation / 800 (max plausible), clipped 0-1
    - wind_norm = windspeed_10m / 15 m/s, clipped 0-1
    - cloud_penalty = cloudcover / 100
    - renewable_score = 0.6 * solar_norm + 0.4 * wind_norm - 0.1 * cloud_penalty, clipped 0-1
    
    Args:
        latitude: Location latitude (e.g., 35.6762 for Tokyo)
        longitude: Location longitude (e.g., 139.6503 for Tokyo)
        days: Number of days to forecast (default 7)
        
    Returns:
        pd.DataFrame with columns:
            - datetime (UTC)
            - shortwave_radiation (W/m²)
            - windspeed_10m (m/s)
            - cloudcover (%)
            - renewable_score (0-1)
    """
    try:
        openmeteo = _setup_openmeteo_session()
        
        # Calculate date range
        now = datetime.utcnow()
        start_date = now.strftime('%Y-%m-%d')
        end_date = (now + timedelta(days=days)).strftime('%Y-%m-%d')
        
        logger.info(f"Fetching renewable data for ({latitude}, {longitude}) from {start_date} to {end_date}")
        
        # Make Open-Meteo API request
        url = "https://api.open-meteo.com/v1/forecast"
        params = {
            "latitude": latitude,
            "longitude": longitude,
            "start_date": start_date,
            "end_date": end_date,
            "hourly": [
                "shortwave_radiation",
                "windspeed_10m",
                "cloudcover",
                "precipitation"
            ],
            "temperature_unit": "Celsius",
            "models": "best_match"
        }
        
        responses = openmeteo.weather_api(url, params=params)
        response = responses[0]
        
        logger.info(f"API Response: lat={response.Latitude()}, lon={response.Longitude()}, timezone={response.Timezone()}")
        
        # Process hourly data
        hourly = response.Hourly()
        hourly_data = {
            "datetime": pd.date_range(
                start=pd.Timestamp(hourly.Time(), tz="UTC"),
                end=pd.Timestamp(hourly.TimeEnd(), tz="UTC"),
                freq=pd.Timedelta(seconds=hourly.Interval()),
                inclusive="left"
            ),
            "shortwave_radiation": hourly.Variables(0).ValuesAsNumpy(),
            "windspeed_10m": hourly.Variables(1).ValuesAsNumpy(),
            "cloudcover": hourly.Variables(2).ValuesAsNumpy(),
            "precipitation": hourly.Variables(3).ValuesAsNumpy()
        }
        
        df = pd.DataFrame(hourly_data)
        
        # Compute renewable availability score
        df['solar_norm'] = np.clip(df['shortwave_radiation'] / 800.0, 0, 1)
        df['wind_norm'] = np.clip(df['windspeed_10m'] / 15.0, 0, 1)
        df['cloud_penalty'] = df['cloudcover'] / 100.0
        
        df['renewable_score'] = (
            0.6 * df['solar_norm'] +
            0.4 * df['wind_norm'] -
            0.1 * df['cloud_penalty']
        )
        df['renewable_score'] = np.clip(df['renewable_score'], 0, 1)
        
        # Keep only necessary columns
        df = df[['datetime', 'shortwave_radiation', 'windspeed_10m', 'cloudcover', 'renewable_score']]
        
        logger.info(f"Fetched {len(df)} hourly records. Renewable score range: {df['renewable_score'].min():.3f} - {df['renewable_score'].max():.3f}")
        
        return df
        
    except Exception as e:
        logger.error(f"Error fetching renewable data from Open-Meteo: {e}")
        return pd.DataFrame()


def fetch_renewable_multiple_locations(locations: dict, days: int = 7) -> dict:
    """
    Fetch renewable availability for multiple locations.
    
    Args:
        locations: Dict mapping location names to {lat, lon}
        days: Number of days to forecast
        
    Returns:
        dict mapping location names to DataFrames
    """
    results = {}
    
    for location_name, coords in locations.items():
        logger.info(f"Fetching renewable data for {location_name}...")
        df = fetch_renewable_availability(coords['lat'], coords['lon'], days)
        results[location_name] = df
    
    return results


def get_renewable_summary(df: pd.DataFrame) -> dict:
    """
    Generate summary statistics for renewable data.
    
    Args:
        df: DataFrame with renewable_score column
        
    Returns:
        dict: Summary statistics
    """
    if df.empty:
        return {}
    
    return {
        "mean_score": df['renewable_score'].mean(),
        "min_score": df['renewable_score'].min(),
        "max_score": df['renewable_score'].max(),
        "std_score": df['renewable_score'].std(),
        "hours_good_solar": (df['solar_norm'] > 0.5).sum(),
        "hours_good_wind": (df['wind_norm'] > 0.5).sum(),
        "hours_high_renewables": (df['renewable_score'] > 0.7).sum(),
    }


if __name__ == "__main__":
    # Test the functions
    print("\n=== Renewable Energy Availability Fetcher ===\n")
    
    # Fetch data for Tokyo
    print("Fetching renewable data for Tokyo (7 days)...\n")
    df = fetch_renewable_availability(
        latitude=config.LOCATION_LATITUDE,
        longitude=config.LOCATION_LONGITUDE,
        days=7
    )
    
    if not df.empty:
        print(f"Retrieved {len(df)} hours of data\n")
        
        # Show summary
        summary = get_renewable_summary(df)
        print("Renewable Summary:")
        for key, value in summary.items():
            print(f"  {key}: {value}")
        print()
        
        # Show sample rows
        print("Sample data (first 10 hours):")
        print(df.head(10).to_string(index=False))
        print()
        
        # Show best and worst hours
        best_idx = df['renewable_score'].idxmax()
        worst_idx = df['renewable_score'].idxmin()
        
        print(f"Best hour: {df.loc[best_idx, 'datetime']} (score: {df.loc[best_idx, 'renewable_score']:.3f})")
        print(f"Worst hour: {df.loc[worst_idx, 'datetime']} (score: {df.loc[worst_idx, 'renewable_score']:.3f})")
    else:
        print("Failed to fetch renewable data.")
