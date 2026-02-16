import asyncio
import numpy as np
import pandas as pd
from sklearn.linear_model import LinearRegression
from sqlalchemy import select
from src.core.database import AsyncSessionLocal
from src.models.models import LapTelemetry, Rider

class DegradationAnalyzer:
    def __init__(self):
        self.model = LinearRegression()

    async def calculate_all_slopes(self, session_id: int):
        """Fetches telemetry and calculates Beta_1 for every rider."""
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
                print("⚠️ No data found in the database.")
                return

            # Load into Pandas for analysis
            df = pd.DataFrame(rows, columns=['rider', 'lap', 'time'])
            
            analysis_results = []

            for rider_name, group in df.groupby('rider'):
                if len(group) < 3: continue # Need at least 3 points for a trend

                # Prepare X (Lap Number) and y (Raw Time)
                X = group['lap'].values.reshape(-1, 1)
                y = group['time'].values

                # Fit the Linear Regression
                self.model.fit(X, y)
                
                beta_1 = self.model.coef_[0] # The Slope
                r_squared = self.model.score(X, y) # Reliability

                analysis_results.append({
                    "Rider": rider_name,
                    "Beta_1 (s/lap)": round(beta_1, 4),
                    "R² (Consistency)": round(r_squared, 4),
                    "Samples": len(group)
                })

            return pd.DataFrame(analysis_results).sort_values(by="Beta_1 (s/lap)")

async def main():
    analyzer = DegradationAnalyzer()
    print("📊 Calculating Positive Slopes for Session 1...")
    
    results_df = await analyzer.calculate_all_slopes(session_id=1)
    
    if results_df is not None:
        print("\n" + "="*50)
        print(results_df.to_string(index=False))
        print("="*50)
        print("\nA lower Beta_1 indicates superior tire management.")

if __name__ == "__main__":
    asyncio.run(main())