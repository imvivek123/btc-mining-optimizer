# src/carbon_credits.py
"""
Carbon credit revenue modeling for renewable-powered mining.
Tracks carbon offset earned through renewable energy use and creates revenue streams.
"""

import logging
import pandas as pd
from typing import Dict
from datetime import datetime
import numpy as np
import config

logger = logging.getLogger(__name__)

# Carbon intensity factors (kg CO2 per MWh)
GRID_CARBON_INTENSITY = {
    "Japan": 0.520,  # avg Japan grid carbon intensity
    "Tokyo": 0.480,  # Mix of hydro + gas
    "Hokkaido": 0.350,  # More renewable
    "Fukuoka": 0.500,
}

# Carbon credit prices
CARBON_CREDIT_PRICE_USD_PER_TONNE = 12.0  # VCS/Gold Standard credits ~$10-15/ton
RENEWABLE_PREMIUM_MULTIPLIER = 1.5  # Extra 50% for certified renewable


class CarbonTracker:
    """Track carbon emissions and credits from mining operations."""
    
    def __init__(self, location: str = "Japan"):
        self.location = location
        self.carbon_intensity = GRID_CARBON_INTENSITY.get(location, 0.520)
        self.cumulative_kwh = 0
        self.cumulative_renewable_kwh = 0
        self.cumulative_co2_kg = 0
        self.cumulative_credits_usd = 0
        
    def log_operation(
        self,
        power_kw: float,
        duration_hours: float,
        renewable_fraction: float = 0.0
    ) -> Dict:
        """
        Log mining operation and calculate carbon impact.
        
        Args:
            power_kw: Power consumption in kW
            duration_hours: Duration in hours
            renewable_fraction: Fraction of energy from renewable (0-1)
            
        Returns:
            dict with carbon metrics for this operation
        """
        try:
            # Total energy used
            energy_kwh = power_kw * duration_hours
            renewable_kwh = energy_kwh * renewable_fraction
            grid_kwh = energy_kwh * (1 - renewable_fraction)
            
            # CO2 emissions (only from grid portion)
            co2_kg = grid_kwh * self.carbon_intensity / 1000  # kg CO2
            
            # Carbon credits earned
            # - Grid energy: standard rate
            # - Renewable energy: premium rate
            grid_credits = (grid_kwh / 1000) * CARBON_CREDIT_PRICE_USD_PER_TONNE * self.carbon_intensity / 1000
            renewable_credits = (renewable_kwh / 1000) * CARBON_CREDIT_PRICE_USD_PER_TONNE * self.carbon_intensity / 1000 * RENEWABLE_PREMIUM_MULTIPLIER
            
            total_credits_usd = grid_credits + renewable_credits
            
            # Update cumulative
            self.cumulative_kwh += energy_kwh
            self.cumulative_renewable_kwh += renewable_kwh
            self.cumulative_co2_kg += co2_kg
            self.cumulative_credits_usd += total_credits_usd
            
            return {
                'timestamp': datetime.utcnow().isoformat(),
                'energy_kwh': energy_kwh,
                'renewable_kwh': renewable_kwh,
                'grid_kwh': grid_kwh,
                'co2_kg': co2_kg,
                'co2_tonnes': co2_kg / 1000,
                'grid_credits_usd': grid_credits,
                'renewable_credits_usd': renewable_credits,
                'total_credits_usd': total_credits_usd,
                'carbon_intensity': self.carbon_intensity,
                'location': self.location,
            }
            
        except Exception as e:
            logger.error(f"Error logging operation: {e}")
            return {}
    
    def get_summary(self) -> Dict:
        """Get cumulative carbon tracking summary."""
        total_energy_mwh = self.cumulative_kwh / 1000
        renewable_pct = (self.cumulative_renewable_kwh / self.cumulative_kwh * 100) if self.cumulative_kwh > 0 else 0
        
        return {
            'location': self.location,
            'total_energy_mwh': total_energy_mwh,
            'renewable_energy_mwh': self.cumulative_renewable_kwh / 1000,
            'grid_energy_mwh': (self.cumulative_kwh - self.cumulative_renewable_kwh) / 1000,
            'renewable_percentage': renewable_pct,
            'total_co2_tonnes': self.cumulative_co2_kg / 1000,
            'carbon_intensity_kg_mwh': self.carbon_intensity,
            'total_credits_earned_usd': self.cumulative_credits_usd,
            'avg_credit_per_mwh_usd': (self.cumulative_credits_usd / total_energy_mwh) if total_energy_mwh > 0 else 0,
        }


def compute_hourly_carbon_credit(
    power_kw: float,
    renewable_score: float,
    location: str = "Japan"
) -> Dict:
    """
    Compute carbon credits earned for one hour of mining.
    
    Args:
        power_kw: Power consumption
        renewable_score: Renewable availability (0-1)
        location: Mining location
        
    Returns:
        dict with hourly carbon credit details
    """
    try:
        tracker = CarbonTracker(location)
        result = tracker.log_operation(power_kw, 1.0, renewable_fraction=renewable_score)
        
        return result
        
    except Exception as e:
        logger.error(f"Error computing carbon credits: {e}")
        return {}


def calculate_carbon_offset_equivalency(co2_tonnes: float) -> Dict:
    """
    Calculate equivalency of carbon offset in real-world terms.
    
    Args:
        co2_tonnes: Amount of CO2 offset in tonnes
        
    Returns:
        dict with equivalencies
    """
    try:
        # Real-world equivalencies
        trees_planted = co2_tonnes * 44 / 20  # Avg tree sequesters 20kg CO2/year, takes 44 years
        miles_driven = co2_tonnes * 1000 / 0.41  # Avg car emits 0.41 kg CO2/mile
        homes_powered = co2_tonnes * 1000 / 4.6  # Avg home: 4.6 tonnes CO2/year
        
        return {
            'co2_tonnes': co2_tonnes,
            'equivalent_trees_annually': trees_planted,
            'equivalent_car_miles': miles_driven,
            'equivalent_homes_powered_year': homes_powered,
            'credit_value_usd': co2_tonnes * CARBON_CREDIT_PRICE_USD_PER_TONNE,
        }
        
    except Exception as e:
        logger.error(f"Error calculating equivalency: {e}")
        return {}


def simulate_annual_carbon_impact(
    power_kw: float,
    annual_renewable_avg: float = 0.5,
    location: str = "Japan"
) -> Dict:
    """
    Simulate annual carbon impact and credits for a mining operation.
    
    Args:
        power_kw: Power consumption
        annual_renewable_avg: Average renewable availability (0-1)
        location: Mining location
        
    Returns:
        dict with annual projections
    """
    try:
        tracker = CarbonTracker(location)
        
        # Simulate 365 days with varying renewable availability
        for day in range(365):
            # Renewable varies sinusoidally + random noise
            renewable_today = annual_renewable_avg + 0.3 * np.sin(2 * np.pi * day / 365) + np.random.normal(0, 0.1)
            renewable_today = np.clip(renewable_today, 0, 1)
            
            # 24 hours at this renewable level
            tracker.log_operation(power_kw, 24, renewable_fraction=renewable_today)
        
        summary = tracker.get_summary()
        equivalency = calculate_carbon_offset_equivalency(summary['total_co2_tonnes'])
        
        return {
            **summary,
            **equivalency,
            'mining_setup': {
                'power_kw': power_kw,
                'annual_renewable_average': annual_renewable_avg,
            }
        }
        
    except Exception as e:
        logger.error(f"Error simulating annual impact: {e}")
        return {}


def generate_carbon_report(tracker: CarbonTracker) -> str:
    """Generate a formatted carbon metrics report."""
    try:
        summary = tracker.get_summary()
        equiv = calculate_carbon_offset_equivalency(summary['total_co2_tonnes'])
        
        report = f"""
╔════════════════════════════════════════════════════════════╗
║         CARBON CREDIT & OFFSET REPORT                      ║
╚════════════════════════════════════════════════════════════╝

📍 Location: {summary['location']}
⚡ Energy Used: {summary['total_energy_mwh']:.1f} MWh
🌿 Renewable Energy: {summary['renewable_energy_mwh']:.1f} MWh ({summary['renewable_percentage']:.1f}%)
🏭 Grid Energy: {summary['grid_energy_mwh']:.1f} MWh

🌍 Carbon Impact:
   • CO2 Offset: {summary['total_co2_tonnes']:.2f} tonnes
   • Carbon Intensity: {summary['carbon_intensity_kg_mwh']:.3f} kg CO2/MWh

💰 Carbon Credits:
   • Credits Earned: ${summary['total_credits_earned_usd']:.2f}
   • Per MWh: ${summary['avg_credit_per_mwh_usd']:.2f}

🌳 Equivalencies:
   • Trees Planted: {equiv['equivalent_trees_annually']:.0f}
   • Car Miles Avoided: {equiv['equivalent_car_miles']:.0f}
   • Homes Powered: {equiv['equivalent_homes_powered_year']:.2f}

"""
        return report
        
    except Exception as e:
        logger.error(f"Error generating report: {e}")
        return ""


if __name__ == "__main__":
    # Test carbon tracking
    tracker = CarbonTracker("Hokkaido")
    
    # Log 30 days of operation
    for day in range(30):
        renewable = 0.6 if day % 3 == 0 else 0.3  # Vary by day
        tracker.log_operation(power_kw=3250, duration_hours=24, renewable_fraction=renewable)
    
    print(generate_carbon_report(tracker))
    
    # Annual projection
    annual = simulate_annual_carbon_impact(power_kw=3250, annual_renewable_avg=0.55, location="Hokkaido")
    print(f"\nAnnual Carbon Credits: ${annual['total_credits_earned_usd']:.2f}")
