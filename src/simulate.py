# src/simulate.py
"""
Run historical backtests of the mining decision engine.
Simulates past N days of mining decisions and computes profitability.
"""

import logging
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import config
from src.fetch_btc import fetch_btc_price_usd, fetch_network_stats
from src.fetch_energy_price import generate_jepx_prices
from src.fetch_renewable import fetch_renewable_availability
from src.mining_economics import compute_hourly_economics
from src.decision_engine import make_decision, get_decision_summary

logger = logging.getLogger(__name__)


def run_backtest(days: int = 30, location: tuple = None) -> dict:
    """
    Run a historical backtest of the decision engine over the past N days.
    
    For each hour in the historical period:
    1. Fetch/simulate BTC price (with ±5% random variation from current)
    2. Generate energy prices for that hour
    3. Fetch renewable availability
    4. Compute economics
    5. Make decision
    
    Args:
        days: Number of days to backtest (default 30)
        location: Tuple of (latitude, longitude) for renewable data
                 (default: Tokyo from config)
        
    Returns:
        dict with keys:
            - results_df: Full DataFrame of all hourly decisions and economics
            - summary: Summary statistics dict
    """
    try:
        if location is None:
            location = (config.LOCATION_LATITUDE, config.LOCATION_LONGITUDE)
        
        logger.info(f"Starting backtest for {days} days...")
        
        # Generate date range (looking back)
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)
        
        start_str = start_date.strftime('%Y-%m-%d')
        end_str = end_date.strftime('%Y-%m-%d')
        
        print(f"\n📊 Running {days}-day backtest from {start_str} to {end_str}\n")
        
        # Fetch data for full period
        logger.info("Fetching energy prices...")
        energy_prices_df = generate_jepx_prices(start_str, end_str)
        
        logger.info("Fetching renewable availability...")
        renewable_df = fetch_renewable_availability(
            latitude=location[0],
            longitude=location[1],
            days=days + 1
        )
        
        # Get current BTC stats as baseline
        logger.info("Fetching current BTC stats...")
        current_btc_stats = fetch_network_stats()
        base_btc_price = current_btc_stats['btc_price_usd']
        
        results = []
        
        # Iterate through each hour
        hourly_dates = pd.date_range(start=start_date, end=end_date, freq='H')
        
        for idx, hour_dt in enumerate(hourly_dates):
            try:
                # Simulate historical BTC price with random variation
                price_variation = np.random.normal(0, 0.05)  # ±5% standard deviation
                simulated_btc_price = base_btc_price * (1 + price_variation)
                
                btc_stats = {
                    'btc_price_usd': simulated_btc_price,
                    'difficulty': current_btc_stats['difficulty']
                }
                
                # Get corresponding energy price row
                energy_row = energy_prices_df.iloc[idx % len(energy_prices_df)]
                
                # Get corresponding renewable score
                if idx < len(renewable_df):
                    renewable_score = renewable_df.iloc[idx]['renewable_score']
                else:
                    renewable_score = renewable_df.iloc[idx % len(renewable_df)]['renewable_score']
                
                # Compute economics
                economics = compute_hourly_economics(btc_stats, energy_row, renewable_score)
                
                # Make decision
                decision = make_decision(
                    economics=economics,
                    renewable_score=renewable_score,
                    btc_price_usd=simulated_btc_price,
                    timestamp=hour_dt
                )
                
                # Build result row
                result_row = {
                    'datetime': hour_dt,
                    'btc_price_usd': simulated_btc_price,
                    'energy_price_jpy_kwh': energy_row['price_jpy_kwh'],
                    'renewable_score': renewable_score,
                    'gross_revenue_usd': economics['gross_revenue_usd'],
                    'net_revenue_usd': economics['net_revenue_usd'],
                    'energy_cost_usd': economics['energy_cost_usd'],
                    'profit_usd': economics['profit_usd'],
                    'profit_margin_pct': economics['profit_margin_pct'],
                    'efficiency_ratio': economics['efficiency_ratio'],
                    'effective_cost_usd_kwh': economics['effective_cost_usd_kwh'],
                    'renewable_discount_applied': economics['renewable_discount_applied'],
                    'decision': decision['decision'],
                    'confidence_score': decision['confidence_score'],
                    'reason': decision['reason']
                }
                
                results.append(result_row)
                
                # Progress indicator
                if (idx + 1) % (7 * 24) == 0:  # Every week
                    logger.info(f"Processed {idx + 1} hours ({(idx + 1) / 24:.0f} days)")
                
            except Exception as e:
                logger.error(f"Error processing hour {hour_dt}: {e}")
                continue
        
        # Convert results to DataFrame
        results_df = pd.DataFrame(results)
        
        # Calculate cumulative profit
        if not results_df.empty:
            results_df['cumulative_profit_usd'] = results_df['profit_usd'].cumsum()
        
        # Generate summary
        summary = get_decision_summary(results_df)
        summary['total_profit_usd'] = results_df['profit_usd'].sum()
        summary['cumulative_profit_usd'] = results_df['cumulative_profit_usd'].iloc[-1] if not results_df.empty else 0
        summary['best_mining_hour'] = results_df.loc[results_df['profit_usd'].idxmax(), 'datetime'] if not results_df.empty else None
        summary['worst_mining_hour'] = results_df.loc[results_df['profit_usd'].idxmin(), 'datetime'] if not results_df.empty else None
        summary['total_renewable_hours'] = (results_df['renewable_score'] > config.RENEWABLE_AVAILABILITY_THRESHOLD).sum()
        
        logger.info(f"Backtest complete. Total profit: ${summary['total_profit_usd']:,.2f}")
        
        return {
            "results_df": results_df,
            "summary": summary
        }
        
    except Exception as e:
        logger.error(f"Error running backtest: {e}")
        return {
            "results_df": pd.DataFrame(),
            "summary": {}
        }


def export_backtest_csv(results_df: pd.DataFrame, path: str = "data/processed/backtest.csv") -> bool:
    """
    Export backtest results to CSV file.
    
    Args:
        results_df: DataFrame with backtest results
        path: Output file path
        
    Returns:
        bool: True if successful
    """
    try:
        results_df.to_csv(path, index=False)
        logger.info(f"Exported backtest results to {path}")
        return True
    except Exception as e:
        logger.error(f"Error exporting backtest: {e}")
        return False


def get_backtest_summary(results_df: pd.DataFrame) -> str:
    """
    Generate human-readable backtest summary.
    
    Args:
        results_df: DataFrame with backtest results
        
    Returns:
        str: Formatted summary text
    """
    if results_df.empty:
        return "No backtest results available"
    
    lines = [
        "\n" + "="*60,
        "⛏️  BACKTEST SUMMARY",
        "="*60,
        f"Period: {results_df['datetime'].min().strftime('%Y-%m-%d')} to {results_df['datetime'].max().strftime('%Y-%m-%d')}",
        f"Total Hours Analyzed: {len(results_df)}",
        "",
        "DECISION BREAKDOWN:",
        f"  GO hours: {(results_df['decision'] == 'GO').sum()} ({(results_df['decision'] == 'GO').sum() / len(results_df) * 100:.1f}%)",
        f"  NO-GO hours: {(results_df['decision'] == 'NO-GO').sum()} ({(results_df['decision'] == 'NO-GO').sum() / len(results_df) * 100:.1f}%)",
        f"  CAUTION hours: {(results_df['decision'] == 'CAUTION').sum()} ({(results_df['decision'] == 'CAUTION').sum() / len(results_df) * 100:.1f}%)",
        "",
        "PROFITABILITY:",
        f"  Total Profit: ${results_df['profit_usd'].sum():,.2f}",
        f"  Cumulative Profit: ${results_df['cumulative_profit_usd'].iloc[-1]:,.2f}",
        f"  Avg Profit/Hour: ${results_df['profit_usd'].mean():,.2f}",
        f"  Best Hour: ${results_df['profit_usd'].max():,.2f}",
        f"  Worst Hour: ${results_df['profit_usd'].min():,.2f}",
        "",
        "RENEWABLE:",
        f"  Hours with Renewable Discount: {(results_df['renewable_discount_applied']).sum()}",
        f"  Avg Renewable Score: {results_df['renewable_score'].mean():.3f}",
        "",
        f"Avg BTC Price: ${results_df['btc_price_usd'].mean():,.2f}",
        f"Avg Energy Cost: ${results_df['effective_cost_usd_kwh'].mean():.4f}/kWh",
        "="*60 + "\n"
    ]
    
    return "\n".join(lines)


if __name__ == "__main__":
    # Run a 7-day backtest
    print("\n⛏️  Bitcoin Mining Backtest Simulator\n")
    
    backtest_results = run_backtest(days=7)
    
    results_df = backtest_results['results_df']
    summary = backtest_results['summary']
    
    # Print summary
    if not results_df.empty:
        print(get_backtest_summary(results_df))
        
        # Export to CSV
        export_backtest_csv(results_df)
        
        # Show first few rows
        print("First 5 hours of backtest:")
        print(results_df.head().to_string(index=False))
    else:
        print("No results to display.")
