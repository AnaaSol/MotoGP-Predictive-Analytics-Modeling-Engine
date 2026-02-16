import pdfplumber
import re
from typing import List, Dict, Optional, Tuple
from src.scraper.engine import MotoGPScraper

class MotoGPLineParser:
    def __init__(self):
        self.engine = MotoGPScraper()

    def _convert_time_to_seconds(self, time_str: str) -> Optional[float]:
        """Convert time string (MM'SS.sss) to seconds."""
        if not time_str:
            return None
        t = str(time_str).strip().replace('*', '').replace('T', '').replace('P', '').strip()
        try:
            if "'" in t:
                parts = t.split("'")
                if len(parts) != 2:
                    return None
                m = int(parts[0])
                s = float(parts[1])
                return m * 60 + s
            return float(t)
        except (ValueError, IndexError):
            return None

    def convert_time_to_seconds(self, time_str: str) -> Optional[float]:
        """Public wrapper for time conversion."""
        return self._convert_time_to_seconds(time_str)

    def _extract_rider_info_from_text(self, text: str) -> Optional[Dict]:
        """
        Extract rider info from text block like:
        "1st 1 Francesco BAGNAIA DUCATI ITA"
        or
        "2nd 49 Fabio DI GIANNANTON DUCATI ITA"
        
        Returns: {"name": "FirstName LASTNAME", "position": "1st", "number": 49}
        """
        # Pattern: position number FirstName LASTNAME MAKE COUNTRY
        # "1st 1 Francesco BAGNAIA DUCATI ITA"
        match = re.search(
            r"(\d+(?:st|nd|rd|th))\s+(\d+)\s+([A-Z][a-zàáâäæèéêëìíîïòóôöœùúûüÿ\s\-]+)\s+([A-Z\s\-]+)\s+([A-Z]{3})",
            text
        )
        if match:
            position = match.group(1)
            number = int(match.group(2))
            first_name = match.group(3).strip()
            make = match.group(4).strip()
            country = match.group(5)
            
            # Split first_name and last_name
            parts = first_name.split()
            if len(parts) >= 2:
                last_name = ' '.join(parts[1:])
                first_name = parts[0]
            else:
                last_name = ''
            
            full_name = f"{first_name} {last_name}".strip()
            
            return {
                "name": full_name,
                "position": position,
                "number": number,
                "country": country,
                "make": make
            }
        
        return None

    def _parse_lap_line(self, line: str) -> Optional[Dict]:
        """
        Parse a lap data line like:
        "8   1'30.590  20.267 24.303 21.725 24.295 321.3"
        
        Returns: {"lap": 8, "time": "1'30.590", "sectors": ["20.267", "24.303", "21.725", "24.295"], "speed": "321.3"}
        """
        # Clean and split by whitespace
        parts = line.split()
        
        if len(parts) < 7:  # Need at least: lap, time, T1, T2, T3, T4, speed
            return None
        
        try:
            lap_num = int(parts[0])
            lap_time = parts[1]
            
            # Validate time format (should have ')
            if "'" not in lap_time:
                return None
            
            # Sectors are typically 4-5 numbers (T1, T2, T3, T4, sometimes more)
            sectors = parts[2:6]  # T1, T2, T3, T4
            
            # Speed is the last column (sometimes there's more data)
            speed = parts[-1] if len(parts) > 6 else None
            
            return {
                "lap": lap_num,
                "time": lap_time,
                "sectors": sectors,
                "speed": speed
            }
        except (ValueError, IndexError):
            return None

    def parse_pdf_analysis(self, pdf_path: str, total_laps: int, debug: bool = False) -> List[Dict]:
        """
        Parse MotoGP PDF by extracting text and parsing line-by-line.
        The PDF has a specific format with rider headers followed by lap data.
        """
        extracted_data = []
        
        try:
            with pdfplumber.open(pdf_path) as pdf:
                if debug:
                    print(f"📄 PDF has {len(pdf.pages)} pages\n")
                
                # Combine text from all pages
                all_text = ""
                for page_num, page in enumerate(pdf.pages):
                    text = page.extract_text()
                    if text:
                        all_text += "\n" + text
                
                # Split into sections by rider headers
                # Rider headers typically look like: "1st 1 Francesco BAGNAIA DUCATI ITA"
                lines = all_text.split('\n')
                
                current_rider = None
                current_make = None
                
                for line_num, line in enumerate(lines):
                    line = line.strip()
                    
                    if not line:
                        continue
                    
                    # Check if this is a rider header line
                    rider_info = self._extract_rider_info_from_text(line)
                    if rider_info:
                        current_rider = rider_info["name"]
                        current_make = rider_info["make"]
                        if debug:
                            print(f"✓ Found rider: {current_rider} ({rider_info['position']}) - {current_make}")
                        continue
                    
                    # Skip certain header/footer lines
                    if any(x in line for x in ["Lap Time T1 T2 T3 T4 Speed", "Runs=", "Run #", 
                                                "Circuit", "Results", "Analysis", "GRAN PREMIO",
                                                "Tyre", "Front", "Rear", "New Tyre", "unfinished",
                                                "Valid laps", "Full laps", "Total laps", "Fastest Lap"]):
                        continue
                    
                    # Try to parse as lap data
                    lap_data = self._parse_lap_line(line)
                    if lap_data and current_rider:
                        raw_time = self._convert_time_to_seconds(lap_data["time"])
                        
                        if raw_time:
                            adj_time = self.engine.calculate_fuel_adjusted_time(
                                raw_time, lap_data["lap"], total_laps
                            )
                            
                            extracted_data.append({
                                "rider": current_rider,
                                "lap": lap_data["lap"],
                                "raw_time": raw_time,
                                "adj_time": adj_time,
                                "sectors": lap_data["sectors"][:4]
                            })
                        
                        if debug and len(extracted_data) % 50 == 0:
                            print(f"  Processed {len(extracted_data)} laps...")
                
                if debug:
                    print(f"\n{'='*70}")
                    print(f"EXTRACTION COMPLETE")
                    print(f"{'='*70}")
                    print(f"✓ Successfully extracted {len(extracted_data)} total lap records")
                    unique_riders = set(entry['rider'] for entry in extracted_data)
                    print(f"✓ From {len(unique_riders)} unique riders:")
                    for rider in sorted(unique_riders):
                        rider_laps = len([e for e in extracted_data if e['rider'] == rider])
                        print(f"  - {rider}: {rider_laps} laps")
        
        except Exception as e:
            print(f"❌ Error parsing PDF: {e}")
            import traceback
            traceback.print_exc()
            return []
        
        if not extracted_data:
            print("⚠️  No data extracted. This might indicate:")
            print("   - Rider header format doesn't match expected pattern")
            print("   - Lap data format is different than expected")
            print("   - Try running with debug=True to see what's happening")
        
        return extracted_data