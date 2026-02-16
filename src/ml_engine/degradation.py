import asyncio
import numpy as np
import pandas as pd
from sklearn.linear_model import LinearRegression
from sqlalchemy import select
from src.core.database import AsyncSessionLocal
from src.models.models import LapTelemetry, Rider

class EnhancedDegradationAnalyzer:
    def __init__(self):
        self.warmup_laps = 3  # Skip first N laps (tire warmup)
        self.model = LinearRegression()

    async def analyze_tire_degradation(self, session_id: int):
        """
        Analyzes tire degradation properly by:
        1. Separating warm-up phase from race phase
        2. Calculating two slopes: overall trend vs. degradation phase
        3. Providing better interpretation
        """
        async with AsyncSessionLocal() as db:
            # Query the database for ingested telemetry
            query = select(
                Rider.name, 
                LapTelemetry.lap_number, 
                LapTelemetry.lap_time_raw
            ).join(LapTelemetry).where(LapTelemetry.session_id == session_id)
            
            result = await db.execute(query)
            rows = result.all()

            if not rows:
                print("No data found in the database.")
                return

            # Load into Pandas for analysis
            df = pd.DataFrame(rows, columns=['rider', 'lap', 'time'])
            
            analysis_results = []

            for rider_name, group in df.groupby('rider'):
                group = group.sort_values('lap').reset_index(drop=True)
                
                if len(group) < 5:  # Need at least 5 laps for meaningful analysis
                    continue

                # Full analysis
                X_full = group['lap'].values.reshape(-1, 1)
                y_full = group['time'].values
                
                self.model.fit(X_full, y_full)
                overall_slope = self.model.coef_[0]
                overall_r2 = self.model.score(X_full, y_full)

                # Warm-up corrected analysis (skip first N laps)
                group_warmed = group[group['lap'] > self.warmup_laps]
                
                if len(group_warmed) >= 3:
                    X_warmed = group_warmed['lap'].values.reshape(-1, 1)
                    y_warmed = group_warmed['time'].values
                    
                    self.model.fit(X_warmed, y_warmed)
                    warmed_slope = self.model.coef_[0]
                    warmed_r2 = self.model.score(X_warmed, y_warmed)
                else:
                    warmed_slope = None
                    warmed_r2 = None

                # Performance metrics
                best_lap = group['time'].min()
                last_lap = group['time'].iloc[-1]
                degradation_delta = last_lap - best_lap  # How much slower the last lap

                analysis_results.append({
                    "Rider": rider_name,
                    "Laps": len(group),
                    "Best Lap": round(best_lap, 2),
                    "Last Lap": round(last_lap, 2),
                    "Δ Degrade (s)": round(degradation_delta, 3),
                    "Overall Slope": round(overall_slope, 4),
                    "Warmed Slope": round(warmed_slope, 4) if warmed_slope else "N/A",
                    "Warmed R²": round(warmed_r2, 4) if warmed_r2 else "N/A",
                })

            results_df = pd.DataFrame(analysis_results).sort_values(by="Δ Degrade (s)")
            return results_df

    async def analyze_tire_strategy(self, session_id: int):
        """
        Categorizes drivers into performance clusters:
        - Improvers: Negative slope (warming up through race)
        - Maintainers: ~0 slope (consistent pace)
        - Degraders: Positive slope (tires falling off)
        """
        async with AsyncSessionLocal() as db:
            query = select(
                Rider.name, 
                LapTelemetry.lap_number, 
                LapTelemetry.lap_time_raw
            ).join(LapTelemetry).where(LapTelemetry.session_id == session_id)
            
            result = await db.execute(query)
            rows = result.all()

            df = pd.DataFrame(rows, columns=['rider', 'lap', 'time'])
            
            strategy_results = []

            for rider_name, group in df.groupby('rider'):
                if len(group) < 3:
                    continue

                X = group['lap'].values.reshape(-1, 1)
                y = group['time'].values
                
                self.model.fit(X, y)
                slope = self.model.coef_[0]
                
                # Categorize
                if slope < -0.1:
                    category = "Improver"
                    explanation = "Warming up, finding rhythm"
                elif slope > 0.1:
                    category = "Degrader"
                    explanation = "Tires falling off or losing pace"
                else:
                    category = "Maintainer"
                    explanation = "Consistent steady pace"

                strategy_results.append({
                    "Rider": rider_name,
                    "Category": category,
                    "Slope": round(slope, 4),
                    "Explanation": explanation,
                })

            return pd.DataFrame(strategy_results).sort_values(by="Slope")

async def main():
    analyzer = EnhancedDegradationAnalyzer()
    
    print("\n" + "="*80)
    print("TIRE DEGRADATION ANALYSIS - MotoGP Valencia 2023")
    print("="*80)
    
    # Analysis 1: Degradation metrics
    print("\n TIRE DEGRADATION METRICS")
    print("-" * 80)
    results_df = await analyzer.analyze_tire_degradation(session_id=1)
    
    if results_df is not None:
        print(results_df.to_string(index=False))
        print("\nKey Insights:")
        print("   • Δ Degrade = Last Lap Time - Best Lap Time (positive = slower at end)")
        print("   • Lower Δ Degrade = Better tire management")
        print("   • Positive 'Warmed Slope' = Degradation in race phase")
    
    # Analysis 2: Strategy categories
    print("\n\nDRIVER STRATEGY CLASSIFICATION")
    print("-" * 80)
    strategy_df = await analyzer.analyze_tire_strategy(session_id=1)
    
    if strategy_df is not None:
        print(strategy_df.to_string(index=False))
    
    print("\n" + "="*80)
    print("💡 INTERPRETATION GUIDE:")
    print("="*80)
    print("""
🚀 IMPROVERS (Negative Slope):
   - Getting faster as race progresses
   - Likely explanation: Warming up tires, finding best racing line
   - Good for: Consistency, confidence building
   
📉 DEGRADERS (Positive Slope):
   - Getting slower as race progresses  
   - Likely explanation: Tire graining, fuel load, setup issues
   - Concern: May struggle in race-distance competitiveness
   
⚖️ MAINTAINERS (Neutral Slope):
   - Holding steady pace throughout
   - Ideal for: Long races, fuel management, tire preservation
   - Sign of: Smooth riding style, good tire management
   """)

if __name__ == "__main__":
    asyncio.run(main())