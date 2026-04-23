# src/grid_balancing.py
"""
Grid balancing optimization and revenue tracking.
Tracks when mining operations participate in grid stabilization and generate revenue.
"""

import logging
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List
import config

logger = logging.getLogger(__name__)

# Grid balancing services definition
GRID_SERVICES = {
    "frequency_regulation": {
        "name": "Frequency Regulation (FFR)",
        "description": "Rapid load adjustment to stabilize grid frequency",
        "response_time_ms": 100,
        "payment_jpy_per_mwh": 5000,
        "min_duration_hours": 0.25,
        "availability_requirement": 0.95,  # Must be available 95% of time
    },
    "demand_flexibility": {
        "name": "Demand Flexibility",
        "description": "Voluntary load reduction during peak periods",
        "response_time_ms": 3600000,  # 1 hour notice
        "payment_jpy_per_mwh": 2000,
        "min_duration_hours": 1,
        "availability_requirement": 0.80,
    },
    "ramping_service": {
        "name": "Ramping Service",
        "description": "Gradual load changes to match renewable generation",
        "response_time_ms": 600000,  # 10 minutes
        "payment_jpy_per_mwh": 3000,
        "min_duration_hours": 0.5,
        "availability_requirement": 0.85,
    },
    "blackstart": {
        "name": "Blackstart (Emergency Reserve)",
        "description": "Ability to reduce load to help restore grid after outage",
        "response_time_ms": 30000,  # 30 seconds
        "payment_jpy_per_mwh": 8000,  # Higher pay for emergency service
        "min_duration_hours": 0.083,  # 5 minutes minimum
        "availability_requirement": 0.99,
    },
}


def check_grid_balance_status() -> Dict:
    """
    Check current grid balance status (frequency, voltage, renewable penetration).
    In real implementation, would connect to grid operator API.
    """
    try:
        now = datetime.utcnow()
        hour = now.hour
        
        # Simulate realistic grid metrics
        # Baseline frequency 50 Hz (Japan)
        expected_frequency = 50.0
        
        # Add variability based on renewable penetration
        renewable_penetration = 0.4 + 0.2 * np.sin(2 * np.pi * hour / 24)  # 20-60%
        
        # Higher renewable = more frequency volatility
        frequency_deviation = (renewable_penetration - 0.3) * np.random.normal(0, 0.15)
        current_frequency = expected_frequency + frequency_deviation
        current_frequency = np.clip(current_frequency, 49.7, 50.3)
        
        # Voltage (380-420 kV typical)
        expected_voltage = 400.0
        voltage_deviation = np.random.normal(0, 3)
        current_voltage = expected_voltage + voltage_deviation
        
        # Grid stress level (0-1)
        if renewable_penetration > 0.6:
            stress = 0.7
        elif renewable_penetration > 0.4:
            stress = 0.5
        else:
            stress = 0.3
        
        stress += np.random.normal(0, 0.1)
        stress = np.clip(stress, 0, 1)
        
        return {
            'frequency_hz': current_frequency,
            'frequency_deviation_hz': current_frequency - expected_frequency,
            'voltage_kv': current_voltage,
            'renewable_penetration': renewable_penetration,
            'grid_stress_level': stress,  # 0=stable, 1=emergency
            'timestamp': now.isoformat(),
            'needs_balancing': stress > 0.6,
            'needs_frequency_support': abs(current_frequency - expected_frequency) > 0.1,
        }
        
    except Exception as e:
        logger.error(f"Error checking grid status: {e}")
        return {}


def identify_available_services(grid_status: Dict) -> List[str]:
    """
    Determine which grid services are needed based on current grid status.
    
    Args:
        grid_status: Dict from check_grid_balance_status()
        
    Returns:
        List of available service names
    """
    try:
        services = []
        
        # Frequency regulation needed if deviation > 0.05 Hz
        if abs(grid_status.get('frequency_deviation_hz', 0)) > 0.05:
            services.append('frequency_regulation')
        
        # Demand flexibility needed if stress is moderate-high
        if grid_status.get('grid_stress_level', 0) > 0.5:
            services.append('demand_flexibility')
        
        # Ramping service if renewable penetration is high
        if grid_status.get('renewable_penetration', 0) > 0.5:
            services.append('ramping_service')
        
        # Blackstart available if grid is stressed
        if grid_status.get('grid_stress_level', 0) > 0.7:
            services.append('blackstart')
        
        return services
        
    except Exception as e:
        logger.error(f"Error identifying services: {e}")
        return []


def calculate_balancing_revenue(
    service_name: str,
    duration_hours: float,
    power_mw: float,
    availability_achieved: float = 0.95
) -> Dict:
    """
    Calculate revenue from providing grid balancing service.
    
    Args:
        service_name: Name of service from GRID_SERVICES
        duration_hours: How long service was provided
        power_mw: Power capacity available
        availability_achieved: Actual availability (0-1)
        
    Returns:
        dict with revenue details
    """
    try:
        if service_name not in GRID_SERVICES:
            logger.warning(f"Unknown service: {service_name}")
            return {}
        
        service = GRID_SERVICES[service_name]
        
        # Check minimum service requirements
        if duration_hours < service['min_duration_hours']:
            logger.debug(f"Service {service_name} below minimum duration")
            return {
                'service': service_name,
                'revenue_jpy': 0,
                'reason': f"Duration {duration_hours:.2f}h below minimum {service['min_duration_hours']}h"
            }
        
        if availability_achieved < service['availability_requirement']:
            logger.debug(f"Service {service_name} below availability requirement")
            return {
                'service': service_name,
                'revenue_jpy': 0,
                'availability_achieved': availability_achieved,
                'reason': f"Availability {availability_achieved:.1%} below requirement {service['availability_requirement']:.1%}"
            }
        
        # Calculate base revenue
        energy_mwh = power_mw * duration_hours
        base_revenue_jpy = energy_mwh * service['payment_jpy_per_mwh']
        
        # Apply availability multiplier (no payment if below requirement)
        availability_multiplier = max(0, (availability_achieved - service['availability_requirement'] * 0.9) / (1 - service['availability_requirement'] * 0.9))
        
        revenue_jpy = base_revenue_jpy * availability_multiplier
        revenue_usd = revenue_jpy * config.JPY_TO_USD
        
        return {
            'service': service_name,
            'service_name': service['name'],
            'duration_hours': duration_hours,
            'energy_mwh': energy_mwh,
            'power_mw': power_mw,
            'availability_achieved': availability_achieved,
            'base_payment_jpy_per_mwh': service['payment_jpy_per_mwh'],
            'revenue_jpy': revenue_jpy,
            'revenue_usd': revenue_usd,
            'response_time_required_ms': service['response_time_ms'],
        }
        
    except Exception as e:
        logger.error(f"Error calculating balancing revenue: {e}")
        return {}


def simulate_grid_balancing_opportunity(
    power_mw: float,
    hours: int = 24,
    risk_profile: str = "moderate"  # conservative, moderate, aggressive
) -> Dict:
    """
    Simulate potential grid balancing revenue for next N hours.
    
    Args:
        power_mw: Power capacity available for balancing
        hours: Hours to simulate
        risk_profile: Risk tolerance for service commitments
        
    Returns:
        dict with revenue projections
    """
    try:
        total_revenue_jpy = 0
        total_revenue_usd = 0
        opportunities = []
        
        for hour in range(hours):
            now = datetime.utcnow() + timedelta(hours=hour)
            
            # Simulate grid status for this hour
            grid_status = check_grid_balance_status()
            services = identify_available_services(grid_status)
            
            if services:
                # Random service selection based on risk profile
                risk_multiplier = {
                    "conservative": 0.7,
                    "moderate": 0.9,
                    "aggressive": 1.0
                }.get(risk_profile, 0.9)
                
                service = services[int(np.random.randint(0, len(services)))]
                
                # Random availability (usually high for mining ops)
                availability = 0.9 + np.random.normal(0, 0.05)
                availability = np.clip(availability, 0.7, 0.99)
                
                # Random duration (usually 15-120 minutes)
                duration_hours = np.random.uniform(0.25, 2.0)
                
                revenue = calculate_balancing_revenue(
                    service,
                    duration_hours * risk_multiplier,
                    power_mw,
                    availability
                )
                
                if revenue.get('revenue_jpy', 0) > 0:
                    total_revenue_jpy += revenue['revenue_jpy']
                    total_revenue_usd += revenue['revenue_usd']
                    
                    opportunities.append({
                        'hour': hour,
                        'timestamp': now.isoformat(),
                        'service': service,
                        'revenue_usd': revenue['revenue_usd']
                    })
        
        return {
            'hours_simulated': hours,
            'total_revenue_usd': total_revenue_usd,
            'total_revenue_jpy': total_revenue_jpy,
            'avg_hourly_revenue_usd': total_revenue_usd / hours if hours > 0 else 0,
            'monthly_revenue_usd': total_revenue_usd / hours * 24 * 30 if hours > 0 else 0,
            'annual_revenue_usd': total_revenue_usd / hours * 24 * 365 if hours > 0 else 0,
            'opportunities_count': len(opportunities),
            'opportunities': opportunities[:10],  # Show first 10
            'risk_profile': risk_profile,
        }
        
    except Exception as e:
        logger.error(f"Error simulating balancing opportunity: {e}")
        return {}


def get_grid_balancing_roi(
    mining_power_mw: float,
    mining_hourly_profit_usd: float
) -> Dict:
    """
    Compare mining revenue vs grid balancing revenue.
    
    Args:
        mining_power_mw: Mining power capacity
        mining_hourly_profit_usd: Current hourly mining profit
        
    Returns:
        dict with ROI comparison
    """
    try:
        # Current mining annual revenue
        mining_annual_usd = mining_hourly_profit_usd * 24 * 365
        
        # Potential grid balancing (moderate profile)
        balancing = simulate_grid_balancing_opportunity(
            power_mw=mining_power_mw,
            hours=168,  # 1 week simulation
            risk_profile="moderate"
        )
        
        balancing_annual_usd = balancing.get('annual_revenue_usd', 0)
        
        # Total revenue
        total_annual_usd = mining_annual_usd + balancing_annual_usd
        
        # Percentage contribution
        mining_pct = (mining_annual_usd / total_annual_usd * 100) if total_annual_usd > 0 else 100
        balancing_pct = (balancing_annual_usd / total_annual_usd * 100) if total_annual_usd > 0 else 0
        
        return {
            'mining_annual_usd': mining_annual_usd,
            'balancing_annual_usd': balancing_annual_usd,
            'total_annual_usd': total_annual_usd,
            'mining_revenue_pct': mining_pct,
            'balancing_revenue_pct': balancing_pct,
            'revenue_improvement_pct': (balancing_annual_usd / mining_annual_usd * 100) if mining_annual_usd > 0 else 0,
            'recommendation': "Consider balancing services" if balancing_pct > 5 else "Focus on mining",
        }
        
    except Exception as e:
        logger.error(f"Error calculating ROI: {e}")
        return {}


def generate_balancing_schedule(hours: int = 24) -> pd.DataFrame:
    """Generate recommended grid balancing schedule."""
    try:
        schedule = []
        
        for hour in range(hours):
            now = datetime.utcnow() + timedelta(hours=hour)
            
            grid_status = check_grid_balance_status()
            services = identify_available_services(grid_status)
            
            primary_service = services[0] if services else None
            
            schedule.append({
                'hour': hour,
                'timestamp': now.isoformat(),
                'hour_of_day': now.hour,
                'recommended_service': primary_service,
                'grid_stress': grid_status.get('grid_stress_level', 0),
                'frequency_deviation': grid_status.get('frequency_deviation_hz', 0),
                'renewable_penetration': grid_status.get('renewable_penetration', 0),
                'action': 'PROVIDE SERVICE' if primary_service else 'MINE NORMALLY'
            })
        
        return pd.DataFrame(schedule)
        
    except Exception as e:
        logger.error(f"Error generating schedule: {e}")
        return pd.DataFrame()


if __name__ == "__main__":
    # Test grid balancing
    grid_status = check_grid_balance_status()
    print("Grid Status:", grid_status)
    
    services = identify_available_services(grid_status)
    print("Available Services:", services)
    
    # Calculate revenue
    if services:
        revenue = calculate_balancing_revenue(
            services[0],
            duration_hours=1.0,
            power_mw=3.25,
            availability_achieved=0.95
        )
        print("\nRevenue:", revenue)
    
    # Full ROI analysis
    roi = get_grid_balancing_roi(mining_power_mw=32.5, mining_hourly_profit_usd=3.5)
    print("\nROI Analysis:", roi)
