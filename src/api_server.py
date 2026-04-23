# src/api_server.py
"""
FastAPI REST server for the Bitcoin Mining Decision Engine.
Exposes all core functionality via REST endpoints for external integrations.
"""

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Optional, List, Dict
from datetime import datetime, timedelta
import logging

import config
from src.fetch_btc import fetch_btc_price_usd, fetch_network_stats
from src.fetch_energy_price import generate_jepx_prices, get_effective_energy_cost
from src.fetch_renewable import fetch_renewable_availability
from src.mining_economics import compute_hourly_economics
from src.decision_engine import make_decision, optimize_schedule
from src.simulate import run_backtest
from src.fetch_jepx_live import fetch_jepx_live_prices
from src.fetch_altcoins import fetch_altcoin_prices, recommend_optimal_coin
from src.demand_response import simulate_grid_demand, calculate_dr_incentive, generate_dr_forecast
from src.multi_location_optimizer import compare_all_locations, recommend_location_distribution
from src.carbon_credits import compute_hourly_carbon_credit, simulate_annual_carbon_impact

logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(
    title="⛏️ Bitcoin Mining Decision Engine API",
    description="REST API for mining profitability optimization",
    version="2.0.0"
)

# CORS middleware for browser access
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Request/Response models
class MiningDecisionRequest(BaseModel):
    location: Optional[str] = "Tokyo"
    num_miners: Optional[int] = config.NUM_MINERS
    min_profit_usd: Optional[float] = config.MIN_PROFIT_MARGIN_USD

class BacktestRequest(BaseModel):
    days: Optional[int] = 30
    location: Optional[str] = "Tokyo"
    num_miners: Optional[int] = config.NUM_MINERS

class LocationComparisonRequest(BaseModel):
    num_miners: Optional[int] = config.NUM_MINERS

class AltcoinAnalysisRequest(BaseModel):
    coins: Optional[List[str]] = None

class DemandResponseRequest(BaseModel):
    hours: Optional[int] = 24

class CarbonAnalysisRequest(BaseModel):
    location: Optional[str] = "Japan"
    days: Optional[int] = 365


# Health check
@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "version": "2.0.0"
    }


# Bitcoin mining endpoints
@app.get("/btc/price")
async def get_btc_price():
    """Get current BTC price and network statistics."""
    try:
        btc_price = fetch_btc_price_usd()
        network_stats = fetch_network_stats()
        
        return {
            "btc_price_usd": btc_price,
            "network_difficulty": network_stats.get('difficulty'),
            "btc_dominance": network_stats.get('dominance'),
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/mining/decision")
async def get_mining_decision(request: MiningDecisionRequest):
    """Get current GO/NO-GO mining decision."""
    try:
        btc_price = fetch_btc_price_usd()
        network_stats = fetch_network_stats()
        
        # Get energy and renewable data
        from src.fetch_energy_price import generate_jepx_prices
        prices_df = generate_jepx_prices(
            (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d'),
            datetime.now().strftime('%Y-%m-%d')
        )
        
        if prices_df.empty:
            raise ValueError("Could not fetch energy prices")
        
        current_price = prices_df.iloc[-1]['price_jpy_kwh']
        
        # Get renewable data
        location_coords = config.LOCATIONS.get(request.location, 
                                               {"lat": config.LOCATION_LATITUDE, 
                                                "lon": config.LOCATION_LONGITUDE})
        renewable_data = fetch_renewable_availability(
            location_coords['lat'],
            location_coords['lon'],
            days=1
        )
        
        renewable_score = renewable_data['renewable_score'].mean() if not renewable_data.empty else 0.3
        
        # Compute economics
        energy_row = pd.Series({'price_jpy_kwh': current_price})
        btc_stats = {
            'btc_price_usd': btc_price,
            'difficulty': network_stats.get('difficulty', config.NETWORK_DIFFICULTY)
        }
        
        econ = compute_hourly_economics(btc_stats, energy_row, renewable_score)
        
        # Make decision
        decision = make_decision(econ, renewable_score, btc_price)
        
        return {
            "decision": decision['decision'],
            "confidence": decision['confidence_score'],
            "reason": decision['reason'],
            "btc_price_usd": btc_price,
            "hourly_profit_usd": econ.get('profit_usd'),
            "renewable_score": renewable_score,
            "timestamp": datetime.utcnow().isoformat(),
            "location": request.location
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/mining/forecast")
async def get_mining_forecast(request: MiningDecisionRequest, hours: int = Query(24, ge=1, le=168)):
    """Get N-hour mining profitability forecast."""
    try:
        btc_price = fetch_btc_price_usd()
        network_stats = fetch_network_stats()
        
        # Generate prices for forecast period
        end_date = datetime.now() + timedelta(hours=hours)
        prices_df = generate_jepx_prices(
            datetime.now().strftime('%Y-%m-%d'),
            end_date.strftime('%Y-%m-%d')
        )
        
        # Generate forecast data
        from src.fetch_energy_price import get_effective_energy_cost
        forecasts = []
        
        for i in range(hours):
            ts = datetime.now() + timedelta(hours=i)
            hour_price = prices_df.iloc[i]['price_jpy_kwh'] if i < len(prices_df) else prices_df.iloc[-1]['price_jpy_kwh']
            
            # Simplified renewable forecast (sine pattern)
            renewable_score = 0.5 + 0.3 * np.sin(2 * np.pi * i / 24)
            renewable_score = max(0, min(1, renewable_score))
            
            energy_row = pd.Series({'price_jpy_kwh': hour_price})
            btc_stats = {
                'btc_price_usd': btc_price,
                'difficulty': network_stats.get('difficulty', config.NETWORK_DIFFICULTY)
            }
            
            econ = compute_hourly_economics(btc_stats, energy_row, renewable_score)
            
            forecasts.append({
                'hour': ts.isoformat(),
                'profit_usd': econ.get('profit_usd'),
                'energy_price_jpy': hour_price,
                'renewable_score': renewable_score
            })
        
        return {
            "forecast_hours": hours,
            "forecasts": forecasts,
            "best_hour": max(forecasts, key=lambda x: x['profit_usd'])['hour'],
            "location": request.location,
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/mining/backtest")
async def run_mining_backtest(request: BacktestRequest):
    """Run historical backtest simulation."""
    try:
        result = run_backtest(days=request.days)
        
        results_df = result['results_df']
        summary = result['summary']
        
        return {
            "days": request.days,
            "total_profit_usd": summary.get('total_profit_usd'),
            "avg_daily_profit_usd": summary.get('avg_daily_profit_usd'),
            "win_rate_pct": summary.get('go_pct'),
            "best_day_profit_usd": summary.get('best_day_profit'),
            "worst_day_profit_usd": summary.get('worst_day_profit'),
            "summary": summary,
            "location": request.location,
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# Energy endpoints
@app.get("/energy/jepx")
async def get_jepx_prices(days: int = Query(7, ge=1, le=30)):
    """Get real JEPX spot prices."""
    try:
        prices_df = fetch_jepx_live_prices(days=days)
        
        return {
            "days": days,
            "price_range": {
                "min_jpy": prices_df['price_jpy_kwh'].min(),
                "max_jpy": prices_df['price_jpy_kwh'].max(),
                "mean_jpy": prices_df['price_jpy_kwh'].mean()
            },
            "data_points": len(prices_df),
            "is_real_data": prices_df.get('is_real_data', [False])[0],
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/energy/demand-response")
async def get_dr_forecast(hours: int = Query(24, ge=1, le=168)):
    """Get demand response forecast."""
    try:
        forecast = generate_dr_forecast(hours)
        
        return {
            "forecast_hours": hours,
            "current_dr_level": forecast.iloc[-1]['dr_level_name'] if not forecast.empty else "Normal",
            "price_adjustments": forecast[['dr_level_name', 'price_change_pct']].to_dict('records')[:hours],
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# Altcoin endpoints
@app.post("/coins/prices")
async def get_altcoin_prices(request: AltcoinAnalysisRequest):
    """Get current prices for mineable altcoins."""
    try:
        prices = fetch_altcoin_prices(request.coins)
        
        return {
            "coins": prices,
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/coins/recommendation")
async def get_coin_recommendation(btc_profit: float = Query(3.5)):
    """Get recommendation for which coin to mine."""
    try:
        recommendation = recommend_optimal_coin(
            hashrate_th=config.MINER_HASHRATE_TH * config.NUM_MINERS,
            energy_cost_usd=1.5,
            btc_profit=btc_profit
        )
        
        return recommendation
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# Location endpoints
@app.post("/locations/compare")
async def compare_locations_api(request: LocationComparisonRequest):
    """Compare mining profitability across all locations."""
    try:
        btc_price = fetch_btc_price_usd()
        network_stats = fetch_network_stats()
        
        btc_stats = {
            'btc_price_usd': btc_price,
            'difficulty': network_stats.get('difficulty', config.NETWORK_DIFFICULTY)
        }
        
        comparison_df = compare_all_locations(btc_stats)
        
        return {
            "locations": comparison_df[['location', 'hourly_profit_usd', 'renewable_score', 'latency_ms']].to_dict('records'),
            "best_location": comparison_df.iloc[0]['location'] if not comparison_df.empty else None,
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/locations/optimization")
async def optimize_locations(request: LocationComparisonRequest):
    """Get optimal hashrate distribution across locations."""
    try:
        btc_price = fetch_btc_price_usd()
        network_stats = fetch_network_stats()
        
        btc_stats = {
            'btc_price_usd': btc_price,
            'difficulty': network_stats.get('difficulty', config.NETWORK_DIFFICULTY)
        }
        
        total_hashrate = config.MINER_HASHRATE_TH * request.num_miners
        recommendation = recommend_location_distribution(btc_stats, total_hashrate)
        
        return recommendation
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# Carbon endpoints
@app.post("/carbon/credits")
async def get_carbon_credits(request: CarbonAnalysisRequest):
    """Calculate carbon credits earned."""
    try:
        annual = simulate_annual_carbon_impact(
            power_kw=config.MINER_POWER_KW * config.NUM_MINERS,
            annual_renewable_avg=0.55,
            location=request.location
        )
        
        return {
            "location": request.location,
            "annual_co2_tonnes": annual['total_co2_tonnes'],
            "annual_credits_usd": annual['total_credits_earned_usd'],
            "renewable_percentage": annual['renewable_percentage'],
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# API documentation
@app.get("/")
async def root():
    """API documentation."""
    return {
        "title": "⛏️ Bitcoin Mining Decision Engine API",
        "version": "2.0.0",
        "endpoints": {
            "health": "/health",
            "btc": "/btc/price",
            "mining": {
                "decision": "POST /mining/decision",
                "forecast": "POST /mining/forecast",
                "backtest": "POST /mining/backtest"
            },
            "energy": {
                "jepx": "/energy/jepx",
                "demand_response": "/energy/demand-response"
            },
            "coins": {
                "prices": "POST /coins/prices",
                "recommendation": "POST /coins/recommendation"
            },
            "locations": {
                "compare": "POST /locations/compare",
                "optimize": "POST /locations/optimization"
            },
            "carbon": {
                "credits": "POST /carbon/credits"
            }
        },
        "docs": "/docs",
        "redoc": "/redoc"
    }


# Error handlers
@app.exception_handler(Exception)
async def general_exception_handler(request, exc):
    """Handle unexpected errors."""
    logger.error(f"Unexpected error: {exc}")
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"}
    )


if __name__ == "__main__":
    import uvicorn
    import pandas as pd
    
    logger.info("Starting Bitcoin Mining Decision Engine API...")
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
        log_level="info"
    )
