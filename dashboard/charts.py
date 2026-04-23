# dashboard/charts.py
"""
Plotly chart components for the dashboard.
All charts are encapsulated as functions returning go.Figure objects.
"""

import logging
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from src.utils import decision_to_color
import config

logger = logging.getLogger(__name__)


def plot_profitability_timeline(df: pd.DataFrame, height: int = 400) -> go.Figure:
    """
    Plot hourly mining profitability with decision regions.
    
    Args:
        df: DataFrame with columns: datetime, profit_usd, decision
        height: Chart height in pixels
        
    Returns:
        go.Figure: Plotly figure
    """
    try:
        if df.empty:
            return go.Figure().add_annotation(text="No data available")
        
        fig = go.Figure()
        
        # Add profitability line
        fig.add_trace(go.Scatter(
            x=df['datetime'],
            y=df['profit_usd'],
            mode='lines',
            name='Hourly Profit',
            line=dict(color='#1f77b4', width=2),
            fill='tozeroy',
            fillcolor='rgba(31, 119, 180, 0.2)'
        ))
        
        # Add break-even line
        fig.add_hline(y=0, line_dash="dash", line_color="gray", opacity=0.5)
        
        # Add minimum profit threshold line
        fig.add_hline(
            y=config.MIN_PROFIT_MARGIN_USD,
            line_dash="dot",
            line_color="orange",
            annotation_text=f"Min Threshold: ${config.MIN_PROFIT_MARGIN_USD}",
            annotation_position="right"
        )
        
        # Add decision background colors
        for decision, group in df.groupby('decision'):
            color = decision_to_color(decision)
            for _, row in group.iterrows():
                fig.add_vrect(
                    x0=row['datetime'],
                    x1=row['datetime'] + pd.Timedelta(hours=1),
                    fillcolor=color,
                    opacity=0.1,
                    layer="below",
                    line_width=0
                )
        
        fig.update_layout(
            title="⛏️ Hourly Mining Profitability Forecast",
            xaxis_title="Time (UTC)",
            yaxis_title="Profit (USD)",
            hovermode='x unified',
            height=height,
            template="plotly_white",
            showlegend=True
        )
        
        return fig
        
    except Exception as e:
        logger.error(f"Error creating profitability chart: {e}")
        return go.Figure().add_annotation(text=f"Error: {str(e)}")


def plot_decision_heatmap(df: pd.DataFrame, height: int = 400) -> go.Figure:
    """
    Create heatmap of profitability by day of week and hour of day.
    
    Args:
        df: DataFrame with datetime and profit_usd columns
        height: Chart height in pixels
        
    Returns:
        go.Figure: Plotly heatmap figure
    """
    try:
        if df.empty:
            return go.Figure().add_annotation(text="No data available")
        
        df = df.copy()
        df['datetime'] = pd.to_datetime(df['datetime'])
        df['day_of_week'] = df['datetime'].dt.day_name()
        df['hour'] = df['datetime'].dt.hour
        
        # Pivot for heatmap
        heatmap_data = df.pivot_table(
            values='profit_usd',
            index='day_of_week',
            columns='hour',
            aggfunc='mean'
        )
        
        # Reorder days of week
        day_order = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
        heatmap_data = heatmap_data.reindex([d for d in day_order if d in heatmap_data.index])
        
        fig = go.Figure(data=go.Heatmap(
            z=heatmap_data.values,
            x=heatmap_data.columns,
            y=heatmap_data.index,
            colorscale='RdYlGn',
            zmid=0,
            hoverongaps=False
        ))
        
        fig.update_layout(
            title="📅 Profitability by Day & Hour",
            xaxis_title="Hour of Day (UTC)",
            yaxis_title="Day of Week",
            height=height,
            template="plotly_white"
        )
        
        return fig
        
    except Exception as e:
        logger.error(f"Error creating heatmap: {e}")
        return go.Figure().add_annotation(text=f"Error: {str(e)}")


def plot_energy_vs_revenue(df: pd.DataFrame, height: int = 400) -> go.Figure:
    """
    Show revenue, energy cost, and profit side-by-side.
    
    Args:
        df: DataFrame with net_revenue_usd, energy_cost_usd, profit_usd columns
        height: Chart height in pixels
        
    Returns:
        go.Figure: Plotly figure
    """
    try:
        if df.empty:
            return go.Figure().add_annotation(text="No data available")
        
        fig = make_subplots(specs=[[{"secondary_y": True}]])
        
        # Add revenue bar
        fig.add_trace(
            go.Bar(
                x=df['datetime'],
                y=df['net_revenue_usd'],
                name='Revenue',
                marker_color='#2ca02c',
                opacity=0.7
            ),
            secondary_y=False
        )
        
        # Add energy cost bar
        fig.add_trace(
            go.Bar(
                x=df['datetime'],
                y=df['energy_cost_usd'],
                name='Energy Cost',
                marker_color='#d62728',
                opacity=0.7
            ),
            secondary_y=False
        )
        
        # Add profit line on secondary axis
        fig.add_trace(
            go.Scatter(
                x=df['datetime'],
                y=df['profit_usd'],
                name='Profit',
                line=dict(color='#1f77b4', width=3),
                mode='lines+markers'
            ),
            secondary_y=True
        )
        
        fig.update_layout(
            title="💰 Revenue vs Energy Cost",
            xaxis_title="Time (UTC)",
            barmode='group',
            hovermode='x unified',
            height=height,
            template="plotly_white"
        )
        
        fig.update_yaxes(title_text="USD", secondary_y=False)
        fig.update_yaxes(title_text="Profit (USD)", secondary_y=True)
        
        return fig
        
    except Exception as e:
        logger.error(f"Error creating revenue chart: {e}")
        return go.Figure().add_annotation(text=f"Error: {str(e)}")


def plot_renewable_vs_decision(df: pd.DataFrame, height: int = 400) -> go.Figure:
    """
    Scatter plot showing relationship between renewable score and profitability.
    Points colored by decision (GO/NO-GO/CAUTION).
    
    Args:
        df: DataFrame with renewable_score, profit_usd, decision columns
        height: Chart height in pixels
        
    Returns:
        go.Figure: Plotly figure
    """
    try:
        if df.empty:
            return go.Figure().add_annotation(text="No data available")
        
        fig = go.Figure()
        
        # Plot points by decision
        for decision in ['GO', 'NO-GO', 'CAUTION']:
            mask = df['decision'] == decision
            color = decision_to_color(decision)
            
            fig.add_trace(go.Scatter(
                x=df[mask]['renewable_score'],
                y=df[mask]['profit_usd'],
                mode='markers',
                name=decision,
                marker=dict(size=8, color=color, opacity=0.6),
                text=df[mask]['datetime'],
                hovertemplate='<b>%{fullData.name}</b><br>Renewable: %{x:.2f}<br>Profit: $%{y:.2f}<br>%{text}<extra></extra>'
            ))
        
        # Add trend line
        try:
            z = np.polyfit(df['renewable_score'], df['profit_usd'], 2)
            p = np.poly1d(z)
            x_trend = np.linspace(df['renewable_score'].min(), df['renewable_score'].max(), 100)
            y_trend = p(x_trend)
            
            fig.add_trace(go.Scatter(
                x=x_trend,
                y=y_trend,
                mode='lines',
                name='Trend',
                line=dict(color='gray', dash='dash')
            ))
        except:
            pass
        
        fig.update_layout(
            title="🌿 Renewable Availability vs Profitability",
            xaxis_title="Renewable Score (0-1)",
            yaxis_title="Profit (USD/hr)",
            hovermode='closest',
            height=height,
            template="plotly_white"
        )
        
        return fig
        
    except Exception as e:
        logger.error(f"Error creating renewable chart: {e}")
        return go.Figure().add_annotation(text=f"Error: {str(e)}")


def plot_backtest_cumulative_profit(df: pd.DataFrame, height: int = 400) -> go.Figure:
    """
    Plot cumulative profit over time with decision regions.
    
    Args:
        df: DataFrame with datetime, profit_usd, decision columns
        height: Chart height in pixels
        
    Returns:
        go.Figure: Plotly figure
    """
    try:
        if df.empty or 'cumulative_profit_usd' not in df.columns:
            return go.Figure().add_annotation(text="No data available")
        
        fig = go.Figure()
        
        # Add cumulative profit area
        fig.add_trace(go.Scatter(
            x=df['datetime'],
            y=df['cumulative_profit_usd'],
            fill='tozeroy',
            name='Cumulative Profit',
            line=dict(color='#1f77b4', width=2),
            fillcolor='rgba(31, 119, 180, 0.3)'
        ))
        
        # Add zero line
        fig.add_hline(y=0, line_dash="dash", line_color="gray", opacity=0.5)
        
        # Shade GO/NO-GO regions
        for decision, group in df.groupby('decision'):
            color = decision_to_color(decision)
            for _, row in group.iterrows():
                fig.add_vrect(
                    x0=row['datetime'],
                    x1=row['datetime'] + pd.Timedelta(hours=1),
                    fillcolor=color,
                    opacity=0.05,
                    layer="below",
                    line_width=0
                )
        
        fig.update_layout(
            title="📈 30-Day Backtest: Cumulative Profit",
            xaxis_title="Date (UTC)",
            yaxis_title="Cumulative Profit (USD)",
            hovermode='x unified',
            height=height,
            template="plotly_white"
        )
        
        return fig
        
    except Exception as e:
        logger.error(f"Error creating cumulative profit chart: {e}")
        return go.Figure().add_annotation(text=f"Error: {str(e)}")


def plot_decision_distribution(decisions_df: pd.DataFrame, height: int = 300) -> go.Figure:
    """
    Pie chart showing distribution of decisions.
    
    Args:
        decisions_df: DataFrame with decision column
        height: Chart height in pixels
        
    Returns:
        go.Figure: Plotly pie chart
    """
    try:
        if decisions_df.empty:
            return go.Figure().add_annotation(text="No data available")
        
        decision_counts = decisions_df['decision'].value_counts()
        colors = [decision_to_color(dec) for dec in decision_counts.index]
        
        fig = go.Figure(data=[go.Pie(
            labels=decision_counts.index,
            values=decision_counts.values,
            marker=dict(colors=colors),
            textposition='inside',
            textinfo='label+percent'
        )])
        
        fig.update_layout(
            title="🎯 Decision Distribution",
            height=height,
            template="plotly_white"
        )
        
        return fig
        
    except Exception as e:
        logger.error(f"Error creating decision distribution chart: {e}")
        return go.Figure().add_annotation(text=f"Error: {str(e)}")
