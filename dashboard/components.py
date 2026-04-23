# dashboard/components.py
"""
Reusable UI components for the Streamlit dashboard.
KPI cards, decision banners, tables, and other widgets.
"""

import streamlit as st
import pandas as pd
from src.utils import format_usd, format_percent, decision_to_emoji, decision_to_color


def show_decision_banner(decision_dict: dict):
    """
    Show a large colored banner with the current mining decision.
    
    Args:
        decision_dict: Dict output from decision_engine.make_decision()
    """
    decision = decision_dict.get('decision', 'UNKNOWN')
    confidence = decision_dict.get('confidence_score', 0)
    reason = decision_dict.get('reason', 'No reason provided')
    profit = decision_dict.get('profit_usd', 0)
    renewable = decision_dict.get('renewable_score', 0)
    
    # Choose color based on decision
    color_map = {
        'GO': '#00AA00',
        'NO-GO': '#FF0000',
        'CAUTION': '#FFAA00'
    }
    
    emoji_map = {
        'GO': '✅',
        'NO-GO': '❌',
        'CAUTION': '⚠️'
    }
    
    color = color_map.get(decision, '#808080')
    emoji = emoji_map.get(decision, '')
    
    # Display banner
    st.markdown(
        f"""
        <div style="
            background-color: {color};
            padding: 20px;
            border-radius: 10px;
            text-align: center;
            color: white;
            font-size: 32px;
            margin-bottom: 20px;
            opacity: 0.9;
        ">
            <h1>{emoji} {decision}</h1>
            <p style="font-size: 18px; margin: 10px 0;">
                Confidence: <strong>{confidence:.0%}</strong>
            </p>
            <p style="font-size: 16px; margin: 5px 0; font-style: italic;">
                {reason}
            </p>
            <p style="font-size: 14px; margin-top: 10px;">
                Profit: <strong>{format_usd(profit)}/hr</strong> | 
                Renewable: <strong>{renewable:.0%}</strong>
            </p>
        </div>
        """,
        unsafe_allow_html=True
    )


def show_kpi_row(current_price: float, hourly_profit: float, 
                 energy_cost: float, renewable_score: float):
    """
    Display a row of 4 KPI cards.
    
    Args:
        current_price: Current BTC price in USD
        hourly_profit: Current hourly profit in USD
        energy_cost: Current energy cost in USD/kWh
        renewable_score: Current renewable availability (0-1)
    """
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("💰 BTC Price", f"${current_price:,.0f}")
    
    with col2:
        color = "off" if hourly_profit < 0 else "inverse"
        st.metric("⛏️ Hourly Profit", format_usd(hourly_profit), delta=f"{hourly_profit:.2f}", delta_color=color if hourly_profit >= 0 else "off")
    
    with col3:
        st.metric("⚡ Energy Cost", f"${energy_cost:.4f}/kWh")
    
    with col4:
        st.metric("🌿 Renewable Score", f"{renewable_score:.0%}", delta_color="off")


def show_forecast_table(df: pd.DataFrame, max_rows: int = 10):
    """
    Display a formatted table of forecast data.
    
    Args:
        df: DataFrame with forecast results
        max_rows: Maximum rows to display
    """
    if df.empty:
        st.warning("No forecast data available")
        return
    
    # Select display columns
    display_cols = [
        'datetime', 'btc_price_usd', 'energy_price_jpy_kwh', 
        'renewable_score', 'profit_usd', 'decision', 'confidence_score'
    ]
    
    display_df = df[display_cols].head(max_rows).copy()
    
    # Format columns
    display_df['datetime'] = display_df['datetime'].dt.strftime('%Y-%m-%d %H:%M')
    display_df['btc_price_usd'] = display_df['btc_price_usd'].apply(lambda x: f"${x:,.0f}")
    display_df['energy_price_jpy_kwh'] = display_df['energy_price_jpy_kwh'].apply(lambda x: f"¥{x:.2f}")
    display_df['renewable_score'] = display_df['renewable_score'].apply(lambda x: f"{x:.0%}")
    display_df['profit_usd'] = display_df['profit_usd'].apply(lambda x: f"${x:.2f}")
    display_df['confidence_score'] = display_df['confidence_score'].apply(lambda x: f"{x:.0%}")
    
    # Rename for display
    display_df.columns = [
        'Time (UTC)', 'BTC Price', 'Energy (¥/kWh)', 
        'Renewable', 'Profit', 'Decision', 'Confidence'
    ]
    
    st.dataframe(display_df, use_container_width=True, hide_index=True)


def show_optimal_schedule_table(schedule_df: pd.DataFrame):
    """
    Display optimal mining sessions.
    
    Args:
        schedule_df: DataFrame with mining sessions (output from optimize_schedule)
    """
    if schedule_df.empty:
        st.info("No optimal sessions found")
        return
    
    display_df = schedule_df.copy()
    display_df['session_start'] = display_df['session_start'].dt.strftime('%Y-%m-%d %H:%M')
    display_df['session_end'] = display_df['session_end'].dt.strftime('%Y-%m-%d %H:%M')
    display_df['expected_profit_usd'] = display_df['expected_profit_usd'].apply(lambda x: format_usd(x))
    display_df['avg_confidence'] = display_df['avg_confidence'].apply(lambda x: f"{x:.0%}")
    display_df['avg_renewable_score'] = display_df['avg_renewable_score'].apply(lambda x: f"{x:.0%}")
    display_df['avg_profit_per_hour'] = display_df['avg_profit_per_hour'].apply(lambda x: format_usd(x))
    
    display_df.columns = [
        'Start', 'End', 'Duration (hrs)', 'Total Profit', 
        'Avg Confidence', 'Avg Renewable', 'Profit/hr'
    ]
    
    st.dataframe(display_df, use_container_width=True, hide_index=True)


def show_backtest_metrics(summary: dict):
    """
    Display backtest summary metrics.
    
    Args:
        summary: Summary dict from simulate.get_backtest_summary()
    """
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.metric(
            "Total Profit",
            format_usd(summary.get('total_profit_usd', 0)),
            delta=f"{summary.get('pct_go', 0):.0f}% GO hours"
        )
    
    with col2:
        st.metric(
            "Mining Hours",
            summary.get('go_hours', 0),
            delta=f"of {summary.get('total_hours', 0)} hours"
        )
    
    with col3:
        st.metric(
            "Avg Hourly",
            format_usd(summary.get('avg_profit_per_hour', 0)),
            delta=f"Best: {format_usd(summary.get('max_profit_hour', 0))}"
        )


def show_info_box(title: str, content: str, icon: str = "ℹ️"):
    """
    Display an informational box with custom styling.
    
    Args:
        title: Box title
        content: Box content (markdown)
        icon: Icon emoji
    """
    st.info(f"**{icon} {title}**  \n{content}")


def show_warning_box(title: str, content: str):
    """Display a warning box."""
    st.warning(f"**⚠️ {title}**  \n{content}")


def show_success_box(title: str, content: str):
    """Display a success box."""
    st.success(f"**✅ {title}**  \n{content}")


def show_error_box(title: str, content: str):
    """Display an error box."""
    st.error(f"**❌ {title}**  \n{content}")
