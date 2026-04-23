# src/demand_forecasting.py
"""
Machine learning demand forecasting for energy prices and mining profitability.
Uses time-series forecasting to predict future prices and profitability.
"""

import logging
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, Tuple
import config

logger = logging.getLogger(__name__)

try:
    from sklearn.preprocessing import StandardScaler
    from sklearn.ensemble import RandomForestRegressor, GradientBoostingRegressor
    from sklearn.linear_model import LinearRegression
    SKLEARN_AVAILABLE = True
except ImportError:
    SKLEARN_AVAILABLE = False
    logger.warning("scikit-learn not available, using fallback forecasting")


class TimeSeriesPredictor:
    """Simple time-series forecaster using ML models."""
    
    def __init__(self, horizon_hours: int = 24):
        self.horizon_hours = horizon_hours
        self.model = None
        self.scaler = StandardScaler() if SKLEARN_AVAILABLE else None
        self.trained = False
        
    def prepare_features(self, price_series: pd.Series) -> np.ndarray:
        """Convert price series to ML features."""
        features = []
        
        for i in range(len(price_series) - 24, len(price_series)):
            if i >= 0:
                # Lagged features (previous 24 hours)
                lagged_prices = price_series.iloc[max(0, i-24):i].values
                
                # Hour of day
                hour_of_day = (i % 24) / 24.0
                
                # Rolling statistics
                rolling_mean = np.mean(lagged_prices[-12:]) if len(lagged_prices) >= 12 else np.mean(lagged_prices)
                rolling_std = np.std(lagged_prices[-12:]) if len(lagged_prices) >= 12 else 0
                
                # Trend
                trend = lagged_prices[-1] - lagged_prices[0] if len(lagged_prices) > 0 else 0
                
                feature_vector = [
                    hour_of_day,
                    rolling_mean,
                    rolling_std,
                    trend,
                    np.min(lagged_prices) if len(lagged_prices) > 0 else 0,
                    np.max(lagged_prices) if len(lagged_prices) > 0 else 0,
                ]
                
                features.append(feature_vector)
        
        return np.array(features) if features else np.array([]).reshape(0, 6)
    
    def train(self, historical_prices: pd.DataFrame):
        """Train forecasting model on historical data."""
        if not SKLEARN_AVAILABLE:
            logger.warning("scikit-learn not available, using fallback forecasting")
            return
        
        try:
            if len(historical_prices) < 48:
                logger.warning("Insufficient historical data for training")
                return
            
            # Prepare data
            price_series = historical_prices['price_jpy_kwh']
            features = self.prepare_features(price_series)
            
            # Targets (next hour's price)
            targets = []
            for i in range(len(price_series) - 24, len(price_series) - 1):
                if i + 1 < len(price_series):
                    targets.append(price_series.iloc[i + 1])
            
            if len(features) == 0 or len(targets) == 0:
                logger.warning("Failed to prepare training data")
                return
            
            # Ensure same length
            min_len = min(len(features), len(targets))
            features = features[:min_len]
            targets = np.array(targets[:min_len])
            
            # Scale features
            self.scaler.fit(features)
            features_scaled = self.scaler.transform(features)
            
            # Train ensemble model
            self.model = GradientBoostingRegressor(
                n_estimators=50,
                learning_rate=0.1,
                max_depth=5,
                random_state=42
            )
            self.model.fit(features_scaled, targets)
            self.trained = True
            
            logger.info(f"✅ Trained forecasting model on {len(historical_prices)} hours of data")
            
        except Exception as e:
            logger.error(f"Error training model: {e}")
            self.trained = False
    
    def forecast(self, historical_prices: pd.DataFrame, hours: int) -> np.ndarray:
        """Forecast next N hours of prices."""
        try:
            if not self.trained or self.model is None:
                logger.warning("Model not trained, using fallback forecast")
                return self._fallback_forecast(historical_prices, hours)
            
            price_series = historical_prices['price_jpy_kwh'].copy()
            forecasts = []
            
            for hour in range(hours):
                # Prepare features for next hour
                features = self.prepare_features(price_series)
                
                if len(features) == 0:
                    forecasts.append(price_series.iloc[-1])
                    continue
                
                # Get last feature vector
                last_features = features[-1:].reshape(1, -1)
                last_features_scaled = self.scaler.transform(last_features)
                
                # Predict
                next_price = self.model.predict(last_features_scaled)[0]
                next_price = max(1.0, next_price)  # Ensure positive
                
                forecasts.append(next_price)
                
                # Update series for next iteration
                new_row = pd.Series({
                    'price_jpy_kwh': next_price,
                    'is_peak_hour': (datetime.now() + timedelta(hours=hour+1)).hour in config.PEAK_HOURS
                })
                price_series = pd.concat([price_series, pd.Series([next_price])])
            
            return np.array(forecasts)
            
        except Exception as e:
            logger.error(f"Error in forecast: {e}")
            return self._fallback_forecast(historical_prices, hours)
    
    def _fallback_forecast(self, historical_prices: pd.DataFrame, hours: int) -> np.ndarray:
        """Fallback naive forecasting (exponential smoothing approximation)."""
        try:
            prices = historical_prices['price_jpy_kwh'].values
            
            if len(prices) == 0:
                return np.array([config.JEPX_BASE_PRICE_JPY] * hours)
            
            # Simple exponential smoothing
            alpha = 0.2
            forecasts = []
            
            last_price = prices[-1]
            last_trend = prices[-1] - prices[-24] if len(prices) >= 24 else 0
            
            for i in range(hours):
                hour_of_day = (datetime.now() + timedelta(hours=i)).hour
                
                # Peak/valley adjustment
                if hour_of_day in config.PEAK_HOURS:
                    peak_mult = config.JEPX_PEAK_MULTIPLIER
                else:
                    peak_mult = config.JEPX_VALLEY_MULTIPLIER
                
                # Simple forecast
                seasonal = peak_mult / config.JEPX_PEAK_MULTIPLIER
                base = config.JEPX_BASE_PRICE_JPY
                
                forecast = base * seasonal + last_trend * 0.1 + np.random.normal(0, 0.5)
                forecast = max(1.0, forecast)
                
                forecasts.append(forecast)
                last_price = forecast
            
            return np.array(forecasts)
            
        except Exception as e:
            logger.error(f"Error in fallback forecast: {e}")
            return np.array([config.JEPX_BASE_PRICE_JPY] * hours)


class ProfitabilityForecaster:
    """Forecast mining profitability using ML."""
    
    def __init__(self):
        self.price_predictor = TimeSeriesPredictor(horizon_hours=24)
        self.trained = False
    
    def train(self, historical_data: pd.DataFrame):
        """Train forecasters."""
        try:
            self.price_predictor.train(historical_data)
            self.trained = True
            logger.info("✅ Trained profitability forecaster")
        except Exception as e:
            logger.error(f"Error training profitability forecaster: {e}")
    
    def forecast_profitability(
        self,
        historical_prices: pd.DataFrame,
        btc_stats: Dict,
        hours: int = 24
    ) -> pd.DataFrame:
        """Forecast hourly profitability for next N hours."""
        try:
            # Forecast energy prices
            price_forecasts = self.price_predictor.forecast(historical_prices, hours)
            
            # Rough profitability estimation
            btc_price = btc_stats.get('btc_price_usd', config.BTC_PRICE_USD)
            
            # Base revenue (simplified)
            hashrate_th = config.MINER_HASHRATE_TH * config.NUM_MINERS
            base_revenue_per_hour = (hashrate_th / 100) * btc_price * 0.1  # Rough estimate
            
            forecasts = []
            for i, price_jpy in enumerate(price_forecasts):
                hour_dt = datetime.now() + timedelta(hours=i)
                
                # Convert price to USD
                cost_usd = price_jpy * config.JPY_TO_USD
                
                # Estimate renewable score (sine pattern)
                renewable = 0.5 + 0.3 * np.sin(2 * np.pi * i / 24)
                renewable = max(0, min(1, renewable))
                
                # Apply renewable discount
                if renewable >= config.RENEWABLE_AVAILABILITY_THRESHOLD:
                    cost_usd *= (1 - config.RENEWABLE_DISCOUNT)
                
                # Estimate hourly cost
                miner_power_kw = config.MINER_POWER_KW * config.NUM_MINERS
                hourly_cost = cost_usd * miner_power_kw
                
                # Profit
                profit = base_revenue_per_hour - hourly_cost
                
                forecast = {
                    'hour': hour_dt.isoformat(),
                    'forecast_price_jpy': price_jpy,
                    'forecast_cost_usd': hourly_cost,
                    'forecast_revenue_usd': base_revenue_per_hour,
                    'forecast_profit_usd': profit,
                    'renewable_score': renewable,
                    'is_peak_hour': hour_dt.hour in config.PEAK_HOURS,
                    'confidence': 0.7 if i < 12 else (0.5 if i < 24 else 0.3),  # Less confident further out
                }
                
                forecasts.append(forecast)
            
            df = pd.DataFrame(forecasts)
            logger.info(f"Generated {hours}-hour profitability forecast")
            
            return df
            
        except Exception as e:
            logger.error(f"Error forecasting profitability: {e}")
            return pd.DataFrame()


def get_forecast_summary(forecast_df: pd.DataFrame) -> Dict:
    """Summarize forecast data."""
    if forecast_df.empty:
        return {}
    
    return {
        'avg_hourly_profit_usd': forecast_df['forecast_profit_usd'].mean(),
        'best_hour': forecast_df.loc[forecast_df['forecast_profit_usd'].idxmax()]['hour'],
        'worst_hour': forecast_df.loc[forecast_df['forecast_profit_usd'].idxmin()]['hour'],
        'profitable_hours': len(forecast_df[forecast_df['forecast_profit_usd'] > 0]),
        'total_forecast_profit_usd': forecast_df['forecast_profit_usd'].sum(),
        'avg_renewable_score': forecast_df['renewable_score'].mean(),
    }


if __name__ == "__main__":
    from src.fetch_energy_price import generate_jepx_prices
    
    # Generate historical data
    start_date = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')
    end_date = datetime.now().strftime('%Y-%m-%d')
    
    historical = generate_jepx_prices(start_date, end_date)
    print(f"Loaded {len(historical)} hours of historical prices")
    
    # Train and forecast
    predictor = TimeSeriesPredictor()
    predictor.train(historical)
    
    forecast = predictor.forecast(historical, hours=24)
    print(f"\n24-hour Price Forecast:")
    for i, price in enumerate(forecast):
        print(f"  Hour {i+1}: {price:.2f} JPY/kWh")
