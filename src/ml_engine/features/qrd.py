import asyncio
import pandas as pd
import numpy as np
from sqlalchemy import select
from src.core.database import AsyncSessionLocal
from src.models.models import LapTelemetry, Rider
from src.scraper.engine import MotoGPScraper

class QRDAnalyzer:
    def __init__(self):
        self.engine = MotoGPScraper()

    async def calculate_qrd_scores(self, session_id: int, total_laps: int):
        async with AsyncSessionLocal() as db:
            # Fetch raw lap telemetry joined with rider names
            query = select(
                Rider.name, 
                LapTelemetry.lap_number, 
                LapTelemetry.lap_time_raw
            ).join(LapTelemetry).where(LapTelemetry.session_id == session_id)
            
            result = await db.execute(query)
            df = pd.DataFrame(result.all(), columns=['rider', 'lap', 'raw_time'])

        if df.empty:
            print("⚠️ Database empty. Run task_runner.py first.")
            return

        # Step 1: Fuel Normalization
        # We apply the engine's formula to get a fair comparison across all laps
        df['adj_time'] = df.apply(
            lambda x: self.engine.calculate_fuel_adjusted_time(x['raw_time'], x['lap'], total_laps), 
            axis=1
        )

        qrd_results = []
        for rider, group in df.groupby('rider'):
            # Step 2: Identify "The Floor" (Best Normalized Lap)
            # This represents the rider's maximum theoretical pace in this race session
            best_lap_adj = group['adj_time'].min()

            # Step 3: Calculate "Average Execution" (Mean Pace)
            # We use the median here to minimize the impact of early-lap chaos
            avg_pace_adj = group['adj_time'].median()

            # Step 4: The QRD Calculation
            # Formula: Delta = Average Race Pace - Peak Potential
            qrd_delta = avg_pace_adj - best_lap_adj

            qrd_results.append({
                "Rider": rider,
                "Best Adj Lap": round(best_lap_adj, 3),
                "Avg Race Pace": round(avg_pace_adj, 3),
                "QRD Score": round(qrd_delta, 4)
            })

        return pd.DataFrame(qrd_results).sort_values(by="QRD Score")

async def main():
    analyzer = QRDAnalyzer()
    print("🏁 Calculating QRD (Quali-to-Race Delta) for Valencia 2023...")
    
    # Valencia 2023 was 27 laps
    results_df = await analyzer.calculate_qrd_scores(session_id=1, total_laps=27)
    
    if results_df is not None:
        print("\n" + "="*65)
        print(results_df.to_string(index=False))
        print("="*65)
        print("\nInterpretation: Lower QRD = Higher Pace Sustainability.")

if __name__ == "__main__":
    asyncio.run(main())