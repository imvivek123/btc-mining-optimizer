# dashboard/app.py
"""
Main Streamlit dashboard for the Bitcoin Mining Decision Engine.
Displays real-time mining decisions, profitability forecasts, and optimization schedules.
"""

import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
from src.fetch_btc import fetch_btc_price_usd, fetch_network_stats, compute_daily_btc_earnings
from src.fetch_energy_price import generate_jepx_prices, get_effective_energy_cost
from src.fetch_renewable import fetch_renewable_availability
from src.mining_economics import compute_hourly_economics
from src.decision_engine import make_decision, optimize_schedule, get_decision_summary
from src.simulate import run_backtest, get_backtest_summary
from src.utils import format_usd, format_power, format_hashrate, setup_logging
from dashboard.charts import (
    plot_profitability_timeline, plot_decision_heatmap, plot_energy_vs_revenue,
    plot_renewable_vs_decision, plot_backtest_cumulative_profit, plot_decision_distribution
)
from dashboard.components import (
    show_decision_banner, show_kpi_row, show_forecast_table, show_optimal_schedule_table,
    show_backtest_metrics, show_info_box, show_warning_box
)

# Set up logging
setup_logging()

# Page config
st.set_page_config(
    page_title="⛏️ Mining Decision Engine",
    layout="wide",
    page_icon="⛏️",
    initial_sidebar_state="expanded"
)

# Custom CSS
st.markdown("""
<style>
    .main { padding-top: 2rem; }
    .metric-box { 
        background-color: #f0f2f6;
        padding: 1rem;
        border-radius: 0.5rem;
        margin: 0.5rem 0;
    }
</style>
""", unsafe_allow_html=True)


def get_location_coords(location_name: str) -> tuple:
    """Get latitude and longitude for a location."""
    return (
        config.LOCATIONS[location_name]['lat'],
        config.LOCATIONS[location_name]['lon']
    )


def main():
    """Main dashboard application."""
    
    # --- SIDEBAR ---
    st.sidebar.title("⚙️ Configuration")
    
    # Location selector
    location = st.sidebar.selectbox(
        "📍 Location",
        list(config.LOCATIONS.keys()),
        help="Select mining location for renewable availability data"
    )
    
    location_coords = get_location_coords(location)
    
    # Number of miners
    num_miners = st.sidebar.slider(
        "⛏️ Number of Miners",
        min_value=1,
        max_value=50,
        value=config.NUM_MINERS,
        step=1,
        help="Number of mining containers in operation"
    )
    
    # Temporarily update config
    original_miners = config.NUM_MINERS
    config.NUM_MINERS = num_miners
    
    # Min profit threshold
    min_profit = st.sidebar.slider(
        "💰 Min Profit Threshold (USD/hr)",
        min_value=0.1,
        max_value=5.0,
        value=config.MIN_PROFIT_MARGIN_USD,
        step=0.1,
        help="Minimum hourly profit required for GO decision"
    )
    config.MIN_PROFIT_MARGIN_USD = min_profit
    
    st.sidebar.divider()
    
    # Action buttons
    st.sidebar.subheader("📊 Actions")
    
    run_live = st.sidebar.button(
        "🔄 Run Live Analysis",
        help="Fetch current data and make real-time decision",
        use_container_width=True
    )
    
    run_forecast = st.sidebar.button(
        "📈 Run 7-Day Forecast",
        help="Generate profitability forecast for next 7 days",
        use_container_width=True
    )
    
    run_backtest_btn = st.sidebar.button(
        "📅 Run 30-Day Backtest",
        help="Historical simulation for past 30 days",
        use_container_width=True
    )
    
    st.sidebar.divider()
    
    # Info section
    st.sidebar.subheader("ℹ️ About This App")
    st.sidebar.caption(
        """
        Agile Energy X Mining Decision Engine™
        
        Determines optimal times to run Bitcoin mining based on:
        - Real-time BTC price & network difficulty
        - Japan energy spot prices (JEPX)
        - Solar/wind renewable availability
        - Mining hardware profitability
        
        **Data Sources:**
        - CoinGecko (free tier)
        - Open-Meteo API (free tier)
        - Synthetic JEPX model
        """
    )
    
    # --- MAIN CONTENT ---
    
    st.title("⛏️ Bitcoin Mining Profitability Decision Engine")
    
    st.markdown("""
    **Agile Energy X's MW2MH Model** — Mine only when it's economically optimal.
    Real-time analysis of BTC prices, energy costs, and renewable availability.
    """)
    
    # --- LIVE ANALYSIS ---
    if run_live:
        st.subheader("🔴 LIVE DECISION")
        
        with st.spinner("⏳ Fetching live data..."):
            try:
                # Fetch live data
                btc_stats = fetch_network_stats()
                btc_price = btc_stats['btc_price_usd']
                
                # Get current hour's energy price
                end_date = datetime.now().strftime('%Y-%m-%d')
                start_date = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
                energy_df = generate_jepx_prices(start_date, end_date)
                current_energy_row = energy_df.iloc[-1]
                
                # Get renewable data
                renewable_df = fetch_renewable_availability(
                    latitude=location_coords[0],
                    longitude=location_coords[1],
                    days=1
                )
                current_renewable = renewable_df.iloc[-1]['renewable_score'] if not renewable_df.empty else 0.5
                
                # Compute economics
                economics = compute_hourly_economics(btc_stats, current_energy_row, current_renewable)
                
                # Make decision
                decision = make_decision(
                    economics=economics,
                    renewable_score=current_renewable,
                    btc_price_usd=btc_price,
                    timestamp=datetime.utcnow()
                )
                
                # Display decision banner
                show_decision_banner(decision)
                
                # Display KPIs
                show_kpi_row(
                    current_price=btc_price,
                    hourly_profit=economics['profit_usd'],
                    energy_cost=economics['effective_cost_usd_kwh'],
                    renewable_score=current_renewable
                )
                
                # Detailed metrics
                col1, col2, col3, col4 = st.columns(4)
                with col1:
                    st.metric("Gross Revenue", format_usd(economics['gross_revenue_usd']))
                with col2:
                    st.metric("Energy Cost", format_usd(economics['energy_cost_usd']))
                with col3:
                    st.metric("Pool Fee (2%)", format_usd(economics['gross_revenue_usd'] - economics['net_revenue_usd']))
                with col4:
                    st.metric("Profit Margin", f"{economics['profit_margin_pct']:.1f}%")
                
                # Hardware info
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric("Total Hashrate", format_hashrate(economics['total_hashrate_th']))
                with col2:
                    st.metric("Total Power", format_power(economics['total_power_kw']))
                with col3:
                    st.metric("Renewable Discount", "✅ Applied" if economics['renewable_discount_applied'] else "❌ Not Applied")
                
            except Exception as e:
                st.error(f"Error fetching live data: {str(e)}")
        
        st.divider()
    
    # --- FORECAST ---
    if run_forecast:
        st.subheader("📈 7-Day Profitability Forecast")
        
        with st.spinner("⏳ Generating 7-day forecast..."):
            try:
                # Generate forecast data
                end_date = datetime.now()
                start_date = end_date - timedelta(days=7)
                
                start_str = start_date.strftime('%Y-%m-%d')
                end_str = end_date.strftime('%Y-%m-%d')
                
                # Fetch data
                btc_stats = fetch_network_stats()
                energy_df = generate_jepx_prices(start_str, end_str)
                renewable_df = fetch_renewable_availability(
                    latitude=location_coords[0],
                    longitude=location_coords[1],
                    days=7
                )
                
                # Compute forecast
                forecast_results = []
                for idx, energy_row in energy_df.iterrows():
                    renewable_score = renewable_df.iloc[idx % len(renewable_df)]['renewable_score']
                    
                    economics = compute_hourly_economics(btc_stats, energy_row, renewable_score)
                    decision = make_decision(
                        economics=economics,
                        renewable_score=renewable_score,
                        btc_price_usd=btc_stats['btc_price_usd'],
                        timestamp=energy_row.get('datetime', datetime.utcnow())
                    )
                    
                    forecast_results.append({
                        'datetime': energy_row.get('datetime', datetime.utcnow()),
                        'btc_price_usd': btc_stats['btc_price_usd'],
                        'energy_price_jpy_kwh': energy_row.get('price_jpy_kwh', 0),
                        'renewable_score': renewable_score,
                        'gross_revenue_usd': economics['gross_revenue_usd'],
                        'net_revenue_usd': economics['net_revenue_usd'],
                        'energy_cost_usd': economics['energy_cost_usd'],
                        'profit_usd': economics['profit_usd'],
                        'profit_margin_pct': economics['profit_margin_pct'],
                        'efficiency_ratio': economics['efficiency_ratio'],
                        'renewable_discount_applied': economics['renewable_discount_applied'],
                        'decision': decision['decision'],
                        'confidence_score': decision['confidence_score'],
                        'reason': decision['reason']
                    })
                
                forecast_df = pd.DataFrame(forecast_results)
                
                # Create tabs for forecast views
                tab1, tab2, tab3, tab4, tab5 = st.tabs([
                    "📊 Profitability Timeline",
                    "📅 Heatmap",
                    "💰 Revenue vs Cost",
                    "🌿 Renewable Analysis",
                    "📋 Forecast Table"
                ])
                
                with tab1:
                    st.plotly_chart(plot_profitability_timeline(forecast_df), use_container_width=True)
                
                with tab2:
                    st.plotly_chart(plot_decision_heatmap(forecast_df), use_container_width=True)
                
                with tab3:
                    st.plotly_chart(plot_energy_vs_revenue(forecast_df), use_container_width=True)
                
                with tab4:
                    st.plotly_chart(plot_renewable_vs_decision(forecast_df), use_container_width=True)
                
                with tab5:
                    show_forecast_table(forecast_df, max_rows=20)
                
                # Optimal schedule
                st.subheader("📅 Optimal Mining Schedule")
                optimal_schedule = optimize_schedule(forecast_df)
                show_optimal_schedule_table(optimal_schedule)
                
            except Exception as e:
                st.error(f"Error generating forecast: {str(e)}")
        
        st.divider()
    
    # --- BACKTEST ---
    if run_backtest_btn:
        st.subheader("📊 30-Day Historical Backtest")
        
        with st.spinner("⏳ Running 30-day backtest (this may take a moment)..."):
            try:
                backtest_data = run_backtest(days=30, location=location_coords)
                results_df = backtest_data['results_df']
                summary = backtest_data['summary']
                
                if not results_df.empty:
                    # Display summary metrics
                    show_backtest_metrics(summary)
                    
                    st.divider()
                    
                    # Charts
                    tab1, tab2, tab3, tab4 = st.tabs([
                        "📈 Cumulative Profit",
                        "📊 Decision Distribution",
                        "📅 Profit Heatmap",
                        "📋 Summary Stats"
                    ])
                    
                    with tab1:
                        st.plotly_chart(plot_backtest_cumulative_profit(results_df), use_container_width=True)
                    
                    with tab2:
                        st.plotly_chart(plot_decision_distribution(results_df), use_container_width=True)
                    
                    with tab3:
                        st.plotly_chart(plot_decision_heatmap(results_df), use_container_width=True)
                    
                    with tab4:
                        # Display detailed summary
                        summary_text = get_backtest_summary(results_df)
                        st.code(summary_text, language="plaintext")
                    
                    # Detailed results table
                    st.subheader("📋 Detailed Backtest Results")
                    show_forecast_table(results_df, max_rows=50)
                    
                else:
                    st.warning("No backtest results available")
                    
            except Exception as e:
                st.error(f"Error running backtest: {str(e)}")
        
        st.divider()
    
    # --- FOOTER ---
    st.divider()
    
    col1, col2, col3 = st.columns(3)
    with col1:
        st.caption("🌱 Powered by renewable energy optimization")
    with col2:
        st.caption(f"📍 Location: {location}")
    with col3:
        st.caption(f"⏰ Last update: {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}")
    
    # Restore original config
    config.NUM_MINERS = original_miners


if __name__ == "__main__":
    main()
