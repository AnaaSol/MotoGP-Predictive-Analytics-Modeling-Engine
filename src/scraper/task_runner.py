import asyncio
import httpx
import numpy as np
from pathlib import Path
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import AsyncSessionLocal, engine
from src.scraper.pdf_parser import MotoGPLineParser
from src.models.models import LapTelemetry, LapSector, Rider, RaceSession, Circuit

class MotoGPTaskRunner:
    def __init__(self):
        self.parser = MotoGPLineParser()
        self.tmp_dir = Path("./data/raw/pdfs")
        self.tmp_dir.mkdir(parents=True, exist_ok=True)

    def filter_clean_air_laps(self, lap_data: list, threshold_z: float = 1.8) -> list:
        """Filter laps to identify clean air vs traffic."""
        times = [d['adj_time'] for d in lap_data if d['adj_time'] is not None]
        if len(times) < 5:
            for d in lap_data:
                d['is_clean_air'] = True
            return lap_data
        
        mean_pace = np.mean(times)
        std_pace = np.std(times)
        for lap in lap_data:
            if lap['adj_time']:
                z_score = (lap['adj_time'] - mean_pace) / (std_pace + 1e-6)
                lap['is_clean_air'] = z_score < threshold_z
            else:
                lap['is_clean_air'] = False
        return lap_data

    async def _get_or_create_rider(self, db: AsyncSession, name: str) -> int:
        """Get or create a rider in the database."""
        result = await db.execute(select(Rider).where(Rider.name == name))
        rider = result.scalar_one_or_none()
        if not rider:
            rider = Rider(name=name, bike_manufacturer="Unknown")
            db.add(rider)
            await db.flush()
        return rider.id

    async def run_ingestion(self, pdf_url: str, session_id: int, total_laps: int, debug: bool = True):
        """
        Run the complete ingestion pipeline.
        
        Args:
            pdf_url: URL to the PDF file
            session_id: Database session ID
            total_laps: Total number of laps in the race
            debug: Enable detailed logging
        """
        if not pdf_url or not pdf_url.startswith("http"):
            print(f"❌ Skipping ingestion: Invalid URL provided '{pdf_url}'")
            return

        local_path = self.tmp_dir / f"session_{session_id}.pdf"
        
        # Download PDF
        async with httpx.AsyncClient() as client:
            print(f"📥 Downloading PDF from: {pdf_url}")
            try:
                response = await client.get(pdf_url, timeout=30.0)
                response.raise_for_status()
            except Exception as e:
                print(f"❌ Failed to download PDF: {e}")
                return
            
            with open(local_path, "wb") as f:
                f.write(response.content)
            print(f"✓ PDF downloaded successfully ({len(response.content)} bytes)")

        # Parse PDF
        print(f"\n🔍 Parsing PDF data...")
        raw_results = self.parser.parse_pdf_analysis(str(local_path), total_laps, debug=debug)
        
        if not raw_results:
            print(f"\n❌ No data parsed from PDF.")
            print(f"   The PDF structure might be different than expected.")
            return
        
        print(f"\n✓ Successfully extracted {len(raw_results)} lap records")

        # Save to database
        print(f"\n💾 Saving to database...")
        async with AsyncSessionLocal() as db:
            rider_names = set(d['rider'] for d in raw_results)
            print(f"📊 Processing {len(rider_names)} riders...\n")
            
            for name in sorted(rider_names):
                rider_id = await self._get_or_create_rider(db, name)
                rider_laps = [d for d in raw_results if d['rider'] == name]
                processed_laps = self.filter_clean_air_laps(rider_laps)
                
                print(f"  ✓ {name}: {len(processed_laps)} laps processed")
                
                for data in processed_laps:
                    lap_entry = LapTelemetry(
                        rider_id=rider_id,
                        session_id=session_id,
                        lap_number=data['lap'],
                        lap_time_raw=data['raw_time']
                    )
                    db.add(lap_entry)
                    await db.flush()
                    
                    # Add sector times
                    for idx, s_time in enumerate(data['sectors'], 1):
                        s_val = self.parser.convert_time_to_seconds(s_time)
                        if s_val:
                            db.add(LapSector(
                                lap_id=lap_entry.id,
                                sector_number=idx,
                                sector_time=s_val
                            ))
            
            await db.commit()
            print(f"\n✓ Ingestion complete for session {session_id}")

async def main():
    """Main entry point."""
    # Ensure database tables exist
    print("🔄 Initializing database schema...")
    async with engine.begin() as conn:
        await conn.run_sync(Rider.metadata.create_all)

    # Ensure required foreign keys exist (Circuit & Session)
    async with AsyncSessionLocal() as db:
        # 1. Create Circuit if not exists
        circuit_res = await db.execute(select(Circuit).where(Circuit.name == "Valencia"))
        circuit = circuit_res.scalar_one_or_none()
        if not circuit:
            circuit = Circuit(name="Valencia", length_km=4.0, total_laps=27, heavy_braking_zones=9)
            db.add(circuit)
            await db.flush()
            print("✓ Created dummy Circuit: Valencia")

        # 2. Create Session if not exists
        session_res = await db.execute(select(RaceSession).where(RaceSession.id == 1))
        session = session_res.scalar_one_or_none()
        if not session:
            # Force ID=1 to match the run_ingestion call
            session = RaceSession(id=1, circuit_id=circuit.id, session_type="Race", track_temp=25.0, air_temp=22.0)
            db.add(session)
            await db.commit()
            print("✓ Created dummy RaceSession (ID: 1)")

    runner = MotoGPTaskRunner()
    url = "https://resources.motogp.com/files/results/2023/VAL/MotoGP/RAC/Analysis.pdf"
    await runner.run_ingestion(url, session_id=1, total_laps=27, debug=True)

if __name__ == "__main__":
    asyncio.run(main())