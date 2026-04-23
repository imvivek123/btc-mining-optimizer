# src/decision_engine.py
"""
Decision engine for GO / NO-GO mining decisions.
Computes confidence scores and determines optimal mining windows.
"""

import logging
import pandas as pd
import numpy as np
from datetime import datetime
from typing import Dict, List
import config

logger = logging.getLogger(__name__)


def make_decision(economics: dict, renewable_score: float, btc_price_usd: float, timestamp: datetime = None) -> Dict:
    """
    Make a GO / NO-GO mining decision based on profitability and renewable availability.
    
    Decision Rules (evaluated in order):
    1. If profit < 0: NO-GO (unprofitable)
    2. If profit < MIN_PROFIT_MARGIN_USD: NO-GO (below threshold)
    3. If renewable_score < 0.1: CAUTION (low renewable availability)
    4. If confidence_score >= CONFIDENCE_THRESHOLD: GO
    5. Else: CAUTION (marginal profitability)
    
    Confidence Score:
        confidence = 0.5 * profit_signal + 0.3 * renewable_signal + 0.2 * margin_signal
        
    Where:
        - profit_signal = min(profit_usd / 10.0, 1.0)
        - renewable_signal = renewable_score
        - margin_signal = min(profit_margin_pct / 50.0, 1.0)
    
    Args:
        economics: Dict output from compute_hourly_economics
        renewable_score: Renewable availability (0-1)
        btc_price_usd: Current BTC price
        timestamp: Timestamp for this decision (default: now)
        
    Returns:
        dict with keys:
            - decision: "GO", "NO-GO", or "CAUTION"
            - confidence_score: 0.0 - 1.0
            - reason: Explanation of decision
            - profit_usd: Hourly profit
            - renewable_score: Renewable availability
            - btc_price_usd: BTC price used
            - timestamp: Decision timestamp
    """
    try:
        if timestamp is None:
            timestamp = datetime.utcnow()
        
        # Extract economics data
        profit_usd = economics.get('profit_usd', 0.0)
        profit_margin_pct = economics.get('profit_margin_pct', 0.0)
        
        # Compute confidence signals
        profit_signal = min(max(profit_usd / 10.0, 0), 1.0)
        renewable_signal = renewable_score
        margin_signal = min(max(profit_margin_pct / 50.0, 0), 1.0)
        
        # Weighted confidence score
        confidence_score = (0.5 * profit_signal + 
                           0.3 * renewable_signal + 
                           0.2 * margin_signal)
        
        confidence_score = np.clip(confidence_score, 0.0, 1.0)
        
        # Decision logic
        if profit_usd < 0:
            decision = "NO-GO"
            reason = "Unprofitable at current energy price"
        elif profit_usd < config.MIN_PROFIT_MARGIN_USD:
            decision = "NO-GO"
            reason = f"Profit below minimum threshold (${profit_usd:.2f} < ${config.MIN_PROFIT_MARGIN_USD:.2f})"
        elif renewable_score < 0.1:
            decision = "CAUTION"
            reason = "Low renewable availability — grid carbon intensity high"
        elif confidence_score >= config.CONFIDENCE_THRESHOLD:
            decision = "GO"
            reason = "Profitable with good renewable availability"
        else:
            decision = "CAUTION"
            reason = "Marginal profitability — monitor closely"
        
        result = {
            "decision": decision,
            "confidence_score": confidence_score,
            "reason": reason,
            "profit_usd": profit_usd,
            "renewable_score": renewable_score,
            "btc_price_usd": btc_price_usd,
            "timestamp": timestamp,
            "profit_signal": profit_signal,
            "renewable_signal": renewable_signal,
            "margin_signal": margin_signal
        }
        
        logger.info(f"{decision} | Profit: ${profit_usd:.2f} | Renewable: {renewable_score:.2f} | Confidence: {confidence_score:.2f}")
        
        return result
        
    except Exception as e:
        logger.error(f"Error making decision: {e}")
        return {
            "decision": "NO-GO",
            "confidence_score": 0.0,
            "reason": f"Error in decision logic: {str(e)}",
            "profit_usd": 0.0,
            "renewable_score": 0.0,
            "btc_price_usd": 0.0,
            "timestamp": timestamp or datetime.utcnow()
        }


def optimize_schedule(forecast_df: pd.DataFrame) -> pd.DataFrame:
    """
    Analyze forecast dataframe and extract optimal mining sessions.
    Group consecutive GO hours into sessions and rank by profitability.
    
    Args:
        forecast_df: DataFrame with columns: decision, profit_usd, renewable_score, datetime
        
    Returns:
        pd.DataFrame with columns:
            - session_start: Start datetime
            - session_end: End datetime
            - duration_hours: Length of session
            - expected_profit_usd: Total profit for session
            - avg_confidence: Average confidence score
            - avg_renewable_score: Average renewable score
            - avg_profit_per_hour: Average hourly profit
    """
    try:
        if forecast_df.empty:
            logger.warning("Empty forecast dataframe provided to optimizer")
            return pd.DataFrame()
        
        # Filter for GO decisions only
        go_hours = forecast_df[forecast_df['decision'] == 'GO'].copy()
        
        if go_hours.empty:
            logger.info("No GO hours found in forecast")
            return pd.DataFrame()
        
        # Group consecutive hours
        go_hours['datetime'] = pd.to_datetime(go_hours['datetime'])
        go_hours = go_hours.sort_values('datetime')
        
        # Identify session boundaries
        go_hours['time_diff'] = go_hours['datetime'].diff()
        # New session if gap > 1 hour
        go_hours['session_id'] = (go_hours['time_diff'] > pd.Timedelta(hours=1)).cumsum()
        
        # Aggregate by session
        sessions = []
        for session_id, group in go_hours.groupby('session_id'):
            session = {
                'session_start': group['datetime'].min(),
                'session_end': group['datetime'].max(),
                'duration_hours': len(group),
                'expected_profit_usd': group['profit_usd'].sum(),
                'avg_confidence': group.get('confidence_score', group.get('profit_usd', pd.Series([0]))).mean(),
                'avg_renewable_score': group['renewable_score'].mean(),
                'avg_profit_per_hour': group['profit_usd'].mean()
            }
            sessions.append(session)
        
        # Convert to DataFrame and sort by profit (descending)
        sessions_df = pd.DataFrame(sessions)
        sessions_df = sessions_df.sort_values('expected_profit_usd', ascending=False)
        
        logger.info(f"Optimizer found {len(sessions_df)} mining sessions")
        if not sessions_df.empty:
            logger.info(f"Best session: ${sessions_df['expected_profit_usd'].iloc[0]:.2f} profit")
        
        return sessions_df
        
    except Exception as e:
        logger.error(f"Error optimizing schedule: {e}")
        return pd.DataFrame()


def get_decision_summary(decisions_df: pd.DataFrame) -> Dict:
    """
    Generate summary statistics from a decisions dataframe.
    
    Args:
        decisions_df: DataFrame with decision results
        
    Returns:
        dict: Summary statistics
    """
    if decisions_df.empty:
        return {}
    
    go_count = (decisions_df['decision'] == 'GO').sum()
    nogo_count = (decisions_df['decision'] == 'NO-GO').sum()
    caution_count = (decisions_df['decision'] == 'CAUTION').sum()
    
    return {
        "total_hours": len(decisions_df),
        "go_hours": go_count,
        "nogo_hours": nogo_count,
        "caution_hours": caution_count,
        "pct_go": (go_count / len(decisions_df)) * 100 if len(decisions_df) > 0 else 0,
        "total_profit_usd": decisions_df['profit_usd'].sum(),
        "avg_profit_per_hour": decisions_df['profit_usd'].mean(),
        "max_profit_hour": decisions_df['profit_usd'].max(),
        "avg_confidence": decisions_df['confidence_score'].mean(),
        "avg_renewable": decisions_df['renewable_score'].mean()
    }


if __name__ == "__main__":
    # Test the functions
    print("\n=== Decision Engine ===\n")
    
    # Create test decisions
    test_decisions = []
    
    scenarios = [
        {"profit": 5.0, "renewable": 0.8, "desc": "High profit, high renewable"},
        {"profit": 1.5, "renewable": 0.7, "desc": "Medium profit, good renewable"},
        {"profit": 0.2, "renewable": 0.5, "desc": "Low profit, medium renewable"},
        {"profit": -0.5, "renewable": 0.3, "desc": "Loss, low renewable"},
        {"profit": 2.0, "renewable": 0.05, "desc": "Good profit, very low renewable"},
    ]
    
    for scenario in scenarios:
        economics = {
            "profit_usd": scenario["profit"],
            "profit_margin_pct": scenario["profit"] * 20  # Simplified
        }
        
        decision = make_decision(
            economics=economics,
            renewable_score=scenario["renewable"],
            btc_price_usd=67000,
            timestamp=datetime.utcnow()
        )
        
        test_decisions.append(decision)
        
        print(f"Scenario: {scenario['desc']}")
        print(f"  Decision: {decision['decision']}")
        print(f"  Confidence: {decision['confidence_score']:.2f}")
        print(f"  Reason: {decision['reason']}")
        print()
