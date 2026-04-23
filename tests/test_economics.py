# tests/test_economics.py
"""Unit tests for mining economics and decision engine."""

import pytest
import pandas as pd
import numpy as np
from datetime import datetime
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import config
from src.mining_economics import compute_hourly_economics, compute_breakeven_btc_price
from src.decision_engine import make_decision, optimize_schedule
from src.fetch_energy_price import get_effective_energy_cost


class TestProfitability:
    """Test profitability calculations."""
    
    def test_profit_is_negative_when_energy_expensive(self):
        """When energy cost > revenue, profit should be negative."""
        # Setup: Very high energy cost
        btc_stats = {
            'btc_price_usd': 100,  # Very low BTC price
            'difficulty': config.NETWORK_DIFFICULTY
        }
        
        energy_row = pd.Series({
            'price_jpy_kwh': 1000  # Extremely high energy price
        })
        
        renewable_score = 0.0
        
        econ = compute_hourly_economics(btc_stats, energy_row, renewable_score)
        
        assert econ['profit_usd'] < 0, "Profit should be negative with expensive energy"
    
    def test_profit_is_positive_when_btc_expensive(self):
        """When BTC price is high and energy low, profit should be positive."""
        btc_stats = {
            'btc_price_usd': 100000,  # High BTC price
            'difficulty': config.NETWORK_DIFFICULTY
        }
        
        energy_row = pd.Series({
            'price_jpy_kwh': 5  # Low energy price
        })
        
        renewable_score = 0.0
        
        econ = compute_hourly_economics(btc_stats, energy_row, renewable_score)
        
        assert econ['profit_usd'] > 0, "Profit should be positive with high BTC price and low energy cost"
    
    def test_efficiency_ratio_greater_than_one_when_profitable(self):
        """Efficiency ratio should be > 1 when profitable (revenue > cost)."""
        btc_stats = {
            'btc_price_usd': 65000,
            'difficulty': config.NETWORK_DIFFICULTY
        }
        
        energy_row = pd.Series({
            'price_jpy_kwh': 12
        })
        
        renewable_score = 0.0
        
        econ = compute_hourly_economics(btc_stats, energy_row, renewable_score)
        
        if econ['profit_usd'] > 0:
            assert econ['efficiency_ratio'] > 1, "Efficiency ratio should be > 1 when profitable"


class TestRenewableDiscount:
    """Test renewable energy discount logic."""
    
    def test_renewable_discount_applied_when_high_score(self):
        """Renewable discount should be applied when score >= threshold."""
        price_jpy = 20.0
        renewable_score = 0.5  # Above threshold
        
        effective_cost = get_effective_energy_cost(price_jpy, renewable_score)
        
        # Cost should be reduced by RENEWABLE_DISCOUNT percentage
        expected_cost = price_jpy * (1 - config.RENEWABLE_DISCOUNT) * config.JPY_TO_USD
        assert effective_cost == expected_cost, "Discount should be applied"
    
    def test_renewable_discount_not_applied_when_low_score(self):
        """Renewable discount should NOT be applied when score < threshold."""
        price_jpy = 20.0
        renewable_score = 0.1  # Below threshold
        
        effective_cost = get_effective_energy_cost(price_jpy, renewable_score)
        
        # Cost should be same (no discount)
        expected_cost = price_jpy * config.JPY_TO_USD
        assert effective_cost == expected_cost, "No discount should be applied"


class TestDecisionEngine:
    """Test mining decision logic."""
    
    def test_go_decision_when_profitable_with_high_confidence(self):
        """Should return GO when profitable and renewable available."""
        economics = {
            'profit_usd': 5.0,
            'profit_margin_pct': 60.0
        }
        
        renewable_score = 0.8
        btc_price = 67000
        
        decision = make_decision(economics, renewable_score, btc_price)
        
        assert decision['decision'] == 'GO', "Should be GO when profitable and renewable available"
        assert decision['confidence_score'] >= config.CONFIDENCE_THRESHOLD
    
    def test_nogo_when_unprofitable(self):
        """Should return NO-GO when unprofitable."""
        economics = {
            'profit_usd': -0.5,
            'profit_margin_pct': -10.0
        }
        
        renewable_score = 0.8
        btc_price = 67000
        
        decision = make_decision(economics, renewable_score, btc_price)
        
        assert decision['decision'] == 'NO-GO', "Should be NO-GO when unprofitable"
    
    def test_nogo_when_below_minimum_threshold(self):
        """Should return NO-GO when profit below minimum threshold."""
        economics = {
            'profit_usd': 0.1,  # Below MIN_PROFIT_MARGIN_USD
            'profit_margin_pct': 2.0
        }
        
        renewable_score = 0.8
        btc_price = 67000
        
        decision = make_decision(economics, renewable_score, btc_price)
        
        assert decision['decision'] == 'NO-GO', "Should be NO-GO when profit below threshold"
    
    def test_caution_when_low_renewable(self):
        """Should return CAUTION when renewable score is very low."""
        economics = {
            'profit_usd': 3.0,
            'profit_margin_pct': 50.0
        }
        
        renewable_score = 0.05  # Very low
        btc_price = 67000
        
        decision = make_decision(economics, renewable_score, btc_price)
        
        assert decision['decision'] == 'CAUTION', "Should be CAUTION when renewable score is very low"
    
    def test_confidence_score_in_valid_range(self):
        """Confidence score should always be between 0 and 1."""
        test_cases = [
            ({'profit_usd': -10, 'profit_margin_pct': -100}, 0.0),
            ({'profit_usd': 0, 'profit_margin_pct': 0}, 0.5),
            ({'profit_usd': 100, 'profit_margin_pct': 100}, 1.0),
        ]
        
        for econ, _ in test_cases:
            decision = make_decision(econ, 0.5, 67000)
            assert 0 <= decision['confidence_score'] <= 1, "Confidence score must be between 0 and 1"


class TestBreakevenPrice:
    """Test breakeven price calculations."""
    
    def test_breakeven_price_is_positive(self):
        """Breakeven BTC price should always be positive."""
        energy_cost = 0.05  # USD/kWh
        breakeven = compute_breakeven_btc_price(energy_cost)
        
        assert breakeven > 0, "Breakeven price should be positive"
        assert breakeven != float('inf'), "Should not be infinite for reasonable costs"
    
    def test_higher_energy_cost_increases_breakeven(self):
        """Higher energy costs should increase breakeven BTC price."""
        breakeven_low = compute_breakeven_btc_price(0.02)
        breakeven_high = compute_breakeven_btc_price(0.10)
        
        assert breakeven_high > breakeven_low, "Higher energy cost should increase breakeven price"


class TestScheduleOptimizer:
    """Test mining schedule optimization."""
    
    def test_optimizer_returns_sorted_by_profit(self):
        """Optimizer should return sessions sorted by profit (descending)."""
        # Create mock forecast data
        dates = pd.date_range('2026-01-01', periods=24, freq='H')
        forecast_df = pd.DataFrame({
            'datetime': dates,
            'decision': ['GO'] * 24,
            'profit_usd': np.random.rand(24) * 10,
            'confidence_score': np.random.rand(24),
            'renewable_score': np.random.rand(24)
        })
        
        schedule = optimize_schedule(forecast_df)
        
        if not schedule.empty:
            # Check if sorted by profit descending
            profits = schedule['expected_profit_usd'].values
            assert all(profits[i] >= profits[i+1] for i in range(len(profits)-1)), \
                "Schedule should be sorted by profit descending"
    
    def test_optimizer_groups_consecutive_hours(self):
        """Optimizer should group consecutive GO hours into sessions."""
        # Create data with consecutive GO hours
        dates = pd.date_range('2026-01-01', periods=48, freq='H')
        decisions = ['GO'] * 12 + ['NO-GO'] * 24 + ['GO'] * 12
        
        forecast_df = pd.DataFrame({
            'datetime': dates,
            'decision': decisions,
            'profit_usd': np.ones(48) * 5,
            'confidence_score': np.ones(48) * 0.7,
            'renewable_score': np.ones(48) * 0.6
        })
        
        schedule = optimize_schedule(forecast_df)
        
        # Should have 2 sessions (first 12 GO hours + last 12 GO hours)
        assert len(schedule) == 2, "Should have 2 sessions"
        assert all(schedule['duration_hours'] == 12), "Sessions should be 12 hours each"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
