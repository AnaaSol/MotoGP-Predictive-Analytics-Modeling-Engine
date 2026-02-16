import asyncio
import httpx
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Tuple

class MotoGPYearDownloader:
    """Download all qualifying and race results for a MotoGP season."""
    
    # 2023 Season Circuit Codes
    CIRCUITS_2023 = {
        1: ("QAT", "Qatar", "Lusail Circuit"),
        2: ("ARG", "Argentina", "Termas de Rio Hondo"),
        3: ("AME", "USA", "Circuit of The Americas"),
        4: ("ESP", "Spain", "Jerez"),
        5: ("FRA", "France", "Le Mans"),
        6: ("ITA", "Italy", "Mugello"),
        7: ("CAT", "Spain", "Barcelona-Catalunya"),
        8: ("NED", "Netherlands", "Assen"),
        9: ("GER", "Germany", "Sachsenring"),
        10: ("AUT", "Austria", "Red Bull Ring"),
        11: ("GBR", "UK", "Silverstone"),
        12: ("RSM", "San Marino", "Misano"),
        13: ("ARA", "Spain", "Aragon"),
        14: ("JPN", "Japan", "Motegi"),
        15: ("AUS", "Australia", "Phillip Island"),
        16: ("THA", "Thailand", "Buriram"),
        17: ("MYS", "Malaysia", "Sepang"),
        18: ("VAL", "Spain", "Valencia"),
    }

    def __init__(self, year: int = 2023, output_dir: str = "./data/raw/motogp_data"):
        self.year = year
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        self.qual_dir = self.output_dir / "qualifying"
        self.race_dir = self.output_dir / "race"
        
        self.qual_dir.mkdir(exist_ok=True)
        self.race_dir.mkdir(exist_ok=True)
        
        self.base_url = "https://resources.motogp.com/files/results"

    def generate_urls(self, circuit_code: str) -> Tuple[str, str]:
        """Generate qualifying and race PDF URLs for a circuit."""
        qual_url = f"{self.base_url}/{self.year}/{circuit_code}/MotoGP/Q2/Analysis.pdf"
        race_url = f"{self.base_url}/{self.year}/{circuit_code}/MotoGP/RAC/Analysis.pdf"
        return qual_url, race_url

    async def download_file(self, url: str, filepath: Path, timeout: int = 30) -> bool:
        """Download a single file with error handling."""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(url, timeout=timeout, follow_redirects=True)
                
                if response.status_code == 200:
                    filepath.write_bytes(response.content)
                    return True
                else:
                    print(f"  ❌ HTTP {response.status_code}: {url}")
                    return False
                    
        except httpx.TimeoutException:
            print(f"  ⏱️  Timeout: {url}")
            return False
        except Exception as e:
            print(f"  ❌ Error: {str(e)}")
            return False

    async def download_season(self, circuits: Dict = None) -> Dict:
        """Download all qualifying and race PDFs for the season."""
        if circuits is None:
            circuits = self.CIRCUITS_2023
        
        results = {
            "qualifying": {"success": 0, "failed": 0, "files": []},
            "race": {"success": 0, "failed": 0, "files": []},
        }

        print(f"\n{'='*80}")
        print(f"🏍️  MOTOGP {self.year} SEASON DOWNLOADER")
        print(f"{'='*80}\n")

        for round_num, (code, country, circuit_name) in circuits.items():
            print(f"Round {round_num:2d}: {country:15s} ({circuit_name:30s})")
            
            qual_url, race_url = self.generate_urls(code)
            
            # Download qualifying
            qual_file = self.qual_dir / f"R{round_num:02d}_{code}_Q2.pdf"
            print(f"  📥 Qualifying Q2...", end=" ", flush=True)
            
            if await self.download_file(qual_url, qual_file):
                print(f"✅ ({qual_file.stat().st_size:,} bytes)")
                results["qualifying"]["success"] += 1
                results["qualifying"]["files"].append({
                    "round": round_num,
                    "circuit": code,
                    "file": str(qual_file),
                    "size": qual_file.stat().st_size
                })
            else:
                print(f"❌")
                results["qualifying"]["failed"] += 1
            
            # Download race
            race_file = self.race_dir / f"R{round_num:02d}_{code}_RAC.pdf"
            print(f"  📥 Race...", end=" ", flush=True)
            
            if await self.download_file(race_url, race_file):
                print(f"✅ ({race_file.stat().st_size:,} bytes)")
                results["race"]["success"] += 1
                results["race"]["files"].append({
                    "round": round_num,
                    "circuit": code,
                    "file": str(race_file),
                    "size": race_file.stat().st_size
                })
            else:
                print(f"❌")
                results["race"]["failed"] += 1
            
            print()  # Blank line between rounds

        # Summary
        print(f"{'='*80}")
        print(f"📊 DOWNLOAD SUMMARY")
        print(f"{'='*80}")
        print(f"Qualifying Sessions:")
        print(f"  ✅ Success: {results['qualifying']['success']}")
        print(f"  ❌ Failed:  {results['qualifying']['failed']}")
        print(f"\nRace Sessions:")
        print(f"  ✅ Success: {results['race']['success']}")
        print(f"  ❌ Failed:  {results['race']['failed']}")
        print(f"\nTotal: {results['qualifying']['success'] + results['race']['success']} PDFs downloaded")
        print(f"Output: {self.output_dir}")
        print(f"{'='*80}\n")

        return results

    def list_downloaded_files(self) -> Dict:
        """List all downloaded files organized by type."""
        qual_files = sorted(self.qual_dir.glob("*.pdf"))
        race_files = sorted(self.race_dir.glob("*.pdf"))

        return {
            "qualifying": qual_files,
            "race": race_files,
            "total": len(qual_files) + len(race_files),
        }

    async def get_custom_year(self, year: int, circuits: Dict = None) -> Dict:
        """Download data for a different year."""
        self.year = year
        return await self.download_season(circuits)


async def main():
    """Main entry point."""
    # Download 2023 season
    downloader = MotoGPYearDownloader(year=2023)
    await downloader.download_season()
    
    # List what was downloaded
    print("\n📋 Downloaded Files:")
    files = downloader.list_downloaded_files()
    
    print(f"\nQualifying ({len(files['qualifying'])} files):")
    for f in files['qualifying'][:5]:  # Show first 5
        print(f"  • {f.name}")
    if len(files['qualifying']) > 5:
        print(f"  ... and {len(files['qualifying']) - 5} more")
    
    print(f"\nRace ({len(files['race'])} files):")
    for f in files['race'][:5]:  # Show first 5
        print(f"  • {f.name}")
    if len(files['race']) > 5:
        print(f"  ... and {len(files['race']) - 5} more")


if __name__ == "__main__":
    asyncio.run(main())
