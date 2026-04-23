# config.py
"""
Global configuration and tunable parameters for the Bitcoin Mining Profitability Simulator.
All constants are centralized here — no hardcoded values elsewhere.
"""

# --- Mining Hardware ---
MINER_HASHRATE_TH = 100           # Terahashes per second (e.g. Antminer S19 Pro = 110 TH/s)
MINER_POWER_KW = 3.25             # Power consumption in kilowatts
NUM_MINERS = 10                   # Number of mining units in the container

# --- Economics ---
ELECTRICITY_COST_JPY_KWH = 15.0  # Base grid electricity cost (JPY/kWh)
RENEWABLE_DISCOUNT = 0.4          # Renewable surplus energy is 40% cheaper
JPY_TO_USD = 0.0067               # Exchange rate (update as needed)
POOL_FEE_PERCENT = 2.0            # Mining pool fee (%)

# --- Bitcoin Network (fetched live, these are fallback defaults) ---
BTC_PRICE_USD = 65000             # Fallback BTC price if API fails
NETWORK_DIFFICULTY = 83.15e12     # Fallback network difficulty
BLOCK_REWARD_BTC = 3.125          # Post-halving block reward (2024)
BLOCKS_PER_DAY = 144              # ~10 min per block (86400 seconds / 600 seconds per block)

# --- Decision Engine Thresholds ---
MIN_PROFIT_MARGIN_USD = 0.5       # Minimum hourly profit to trigger GO (USD)
RENEWABLE_AVAILABILITY_THRESHOLD = 0.35  # Min renewable score (0-1) to get discount
CONFIDENCE_THRESHOLD = 0.65       # Min confidence score to output GO decision

# --- Simulation ---
SIMULATION_DAYS = 30              # Days of historical simulation
LOCATION_LATITUDE = 35.6762       # Tokyo, Japan
LOCATION_LONGITUDE = 139.6503

# --- Energy Price Model (JEPX synthetic) ---
JEPX_BASE_PRICE_JPY = 12.0       # Base spot price JPY/kWh
JEPX_PEAK_MULTIPLIER = 2.5       # Peak hours price multiplier
JEPX_VALLEY_MULTIPLIER = 0.6     # Off-peak price multiplier
PEAK_HOURS = list(range(8, 21))   # 08:00 – 20:00 JST (includes 8 and 20 but not 21)

# --- Location Presets (for dashboard) ---
LOCATIONS = {
    "Tokyo": {"lat": 35.6762, "lon": 139.6503},
    "Osaka": {"lat": 34.6937, "lon": 135.5024},
    "Fukuoka": {"lat": 33.5904, "lon": 130.4017},
    "Sapporo": {"lat": 43.0642, "lon": 141.3469},
}
