import asyncio
import pandas as pd
import numpy as np
from pathlib import Path
from typing import Dict, List, Tuple, Optional
from sqlalchemy import select
import matplotlib.pyplot as plt
import seaborn as sns
from src.core.database import AsyncSessionLocal
from src.models.models import LapTelemetry, Rider
from src.scraper.pdf_parser import MotoGPLineParser


class QRDAnalyzer:
    """
    QRD (Qualifying-Race Delta) Analyzer
    
    QRD = Qualifying Best Lap - Race Best Lap
    
    Positive QRD: Qualified faster than raced (driver struggled in race)
    Negative QRD: Raced faster than qualified (driver improved in race)
    Zero QRD: Perfect pace consistency between sessions
    
    This analyzer:
    - Parses qualifying and race PDFs
    - Extracts best lap times
    - Calculates QRD for each driver per round
    - Generates seasonal statistics
    - Categorizes driver types (qualifiers vs race drivers)
    - Produces visualizations
    """

    def __init__(self, 
                 qual_pdf_dir: str = "./data/raw/motogp_data/qualifying",
                 race_pdf_dir: str = "./data/raw/motogp_data/race",
                 output_dir: str = "./analysis/qrd_results"):
        
        self.qual_pdf_dir = Path(qual_pdf_dir)
        self.race_pdf_dir = Path(race_pdf_dir)
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        self.parser = MotoGPLineParser()
        self.results = {}

    async def parse_round_data(self, 
                               round_num: int,
                               circuit_code: str) -> Tuple[pd.DataFrame, pd.DataFrame]:
        """
        Parse qualifying and race PDFs for a round.
        
        Args:
            round_num: Round number (1-18)
            circuit_code: Circuit code (QAT, ARG, etc.)
        
        Returns:
            (qual_df, race_df) tuple
        """
        qual_file = self.qual_pdf_dir / f"R{round_num:02d}_{circuit_code}_Q2.pdf"
        race_file = self.race_pdf_dir / f"R{round_num:02d}_{circuit_code}_RAC.pdf"
        
        qual_df = None
        race_df = None
        
        # Parse qualifying (Q2 format)
        if qual_file.exists():
            print(f"  📄 Parsing qualifying: {qual_file.name}...", end=" ", flush=True)
            try:
                # Assuming 12-15 laps in qualifying
                qual_data = self.parser.parse_pdf_analysis(str(qual_file), total_laps=12, debug=False)
                qual_df = pd.DataFrame(qual_data)
                print(f"✅ ({len(qual_df)} records)")
            except Exception as e:
                print(f"❌ Error: {str(e)}")
        else:
            print(f"  ⚠️  Qualifying PDF not found: {qual_file.name}")
        
        # Parse race
        if race_file.exists():
            print(f"  📄 Parsing race: {race_file.name}...", end=" ", flush=True)
            try:
                # MotoGP race is typically 25-27 laps
                race_data = self.parser.parse_pdf_analysis(str(race_file), total_laps=27, debug=False)
                race_df = pd.DataFrame(race_data)
                print(f"✅ ({len(race_df)} records)")
            except Exception as e:
                print(f"❌ Error: {str(e)}")
        else:
            print(f"  ⚠️  Race PDF not found: {race_file.name}")
        
        return qual_df, race_df

    def calculate_qrd(self, 
                      qual_best: float, 
                      race_best: float) -> float:
        """Calculate QRD value."""
        return qual_best - race_best

    async def analyze_round(self, 
                           round_num: int,
                           circuit: str,
                           qual_df: Optional[pd.DataFrame],
                           race_df: Optional[pd.DataFrame]) -> Optional[pd.DataFrame]:
        """
        Analyze QRD for a single round.
        
        Args:
            round_num: Round number
            circuit: Circuit code
            qual_df: Qualifying data
            race_df: Race data
        
        Returns:
            DataFrame with QRD analysis or None if data missing
        """
        if qual_df is None or race_df is None or qual_df.empty or race_df.empty:
            print(f"  ⚠️  Skipping round {round_num} ({circuit}): Missing data")
            return None
        
        # Extract best laps
        qual_best = {}
        for rider, group in qual_df.groupby('rider'):
            qual_best[rider] = group['raw_time'].min()
        
        race_best = {}
        for rider, group in race_df.groupby('rider'):
            race_best[rider] = group['raw_time'].min()
        
        # Calculate QRD for each rider
        results = []
        for rider in qual_best.keys():
            if rider not in race_best:
                continue  # Rider didn't race
            
            qual_time = qual_best[rider]
            race_time = race_best[rider]
            qrd = self.calculate_qrd(qual_time, race_time)
            
            # Count laps
            qual_laps = len(qual_df[qual_df['rider'] == rider])
            race_laps = len(race_df[race_df['rider'] == rider])
            
            results.append({
                "Round": round_num,
                "Circuit": circuit,
                "Rider": rider,
                "Qual_Best_Lap": round(qual_time, 3),
                "Race_Best_Lap": round(race_time, 3),
                "QRD": round(qrd, 3),
                "Qual_Laps": qual_laps,
                "Race_Laps": race_laps,
                "Status": "Finished" if race_laps > 20 else "DNF",
            })
        
        return pd.DataFrame(results) if results else None

    async def analyze_season(self, 
                            circuits_dict: Dict[int, Tuple[str, str, str]]) -> pd.DataFrame:
        """
        Analyze QRD for entire season.
        
        Args:
            circuits_dict: {round_num: (code, country, name), ...}
        
        Returns:
            DataFrame with all QRD data for the season
        """
        all_results = []
        
        print("\n" + "="*80)
        print("🏍️  MOTOGP QRD (QUALIFYING-RACE DELTA) ANALYSIS")
        print("="*80 + "\n")
        
        for round_num, (code, country, name) in circuits_dict.items():
            print(f"Round {round_num:2d}: {country:15s} ({name:30s})")
            
            # Parse PDFs
            qual_df, race_df = await self.parse_round_data(round_num, code)
            
            # Analyze
            if qual_df is not None and race_df is not None:
                round_results = await self.analyze_round(
                    round_num=round_num,
                    circuit=code,
                    qual_df=qual_df,
                    race_df=race_df
                )
                
                if round_results is not None:
                    all_results.append(round_results)
                    print(f"  ✅ Analyzed {len(round_results)} riders\n")
                else:
                    print(f"  ⚠️  No results for this round\n")
            else:
                print(f"  ❌ Missing data for analysis\n")
        
        # Combine all results
        if all_results:
            return pd.concat(all_results, ignore_index=True)
        else:
            return pd.DataFrame()

    def get_season_statistics(self, qrd_df: pd.DataFrame) -> pd.DataFrame:
        """
        Calculate season-wide QRD statistics by rider.
        
        Returns:
            DataFrame with rider statistics
        """
        if qrd_df.empty:
            return pd.DataFrame()
        
        stats = []
        
        for rider, group in qrd_df.groupby('Rider'):
            stats.append({
                "Rider": rider,
                "Rounds": len(group),
                "Avg_QRD": round(group['QRD'].mean(), 3),
                "Std_QRD": round(group['QRD'].std(), 3),
                "Min_QRD": round(group['QRD'].min(), 3),
                "Max_QRD": round(group['QRD'].max(), 3),
                "Avg_Qual_Time": round(group['Qual_Best_Lap'].mean(), 3),
                "Avg_Race_Time": round(group['Race_Best_Lap'].mean(), 3),
                "Finishes": len(group[group['Status'] == 'Finished']),
                "DNFs": len(group[group['Status'] == 'DNF']),
            })
        
        return pd.DataFrame(stats).sort_values('Avg_QRD')

    def categorize_drivers(self, stats_df: pd.DataFrame) -> Dict:
        """
        Categorize drivers by their QRD performance.
        
        Returns:
            dict with driver categories
        """
        categories = {
            "🚀 Elite Race Drivers": [],      # Negative avg QRD (raced faster)
            "⚖️  Consistent Performers": [],  # Small positive QRD (0 to +0.2s)
            "🎯 Solid Performers": [],       # +0.2 to +0.5s
            "📊 Moderate Gap": [],           # +0.5 to +1.0s
            "⚠️  Quali Specialists": [],     # +1.0s+ (qualify better than race)
        }
        
        for _, row in stats_df.iterrows():
            rider = row['Rider']
            avg_qrd = row['Avg_QRD']
            std_qrd = row['Std_QRD']
            
            info = {
                "rider": rider,
                "avg_qrd": avg_qrd,
                "std_qrd": std_qrd,
                "rounds": row['Rounds'],
                "dnfs": row['DNFs'],
            }
            
            if avg_qrd < 0:
                categories["🚀 Elite Race Drivers"].append(info)
            elif avg_qrd < 0.2:
                categories["⚖️  Consistent Performers"].append(info)
            elif avg_qrd < 0.5:
                categories["🎯 Solid Performers"].append(info)
            elif avg_qrd < 1.0:
                categories["📊 Moderate Gap"].append(info)
            else:
                categories["⚠️  Quali Specialists"].append(info)
        
        # Sort by QRD within each category
        for category in categories:
            categories[category].sort(key=lambda x: x['avg_qrd'])
        
        return categories

    def print_analysis_report(self, qrd_df: pd.DataFrame, stats_df: pd.DataFrame):
        """Print formatted analysis report."""
        categories = self.categorize_drivers(stats_df)
        
        print("\n" + "="*80)
        print("📊 QRD ANALYSIS SUMMARY")
        print("="*80 + "\n")
        
        print("🔍 INTERPRETATION GUIDE:")
        print("  • QRD > 0:     Qualified faster (typical, good setup change)")
        print("  • QRD ≈ 0:     Identical pace (perfect consistency)")
        print("  • QRD < 0:     Raced faster than qualified (excellent race craft)")
        print("  • High Std:    Inconsistent performance across rounds\n")
        
        # Print categories
        for category, drivers in categories.items():
            if drivers:
                print(f"\n{category}")
                print("-" * 80)
                for d in drivers:
                    status = "✅ Consistent" if d['std_qrd'] < 0.3 else "⚠️  Variable"
                    dnf_info = f" (DNF: {d['dnfs']})" if d['dnfs'] > 0 else ""
                    print(f"  {d['rider']:<15} QRD: {d['avg_qrd']:+.3f}s (σ: {d['std_qrd']:.3f}s) "
                          f"[{d['rounds']} rounds]{dnf_info} {status}")
        
        print("\n" + "="*80)
        print("📈 SEASON STATISTICS")
        print("="*80 + "\n")
        print(f"Total rounds analyzed: {qrd_df['Round'].nunique()}")
        print(f"Total drivers: {qrd_df['Rider'].nunique()}")
        print(f"Overall avg QRD: {qrd_df['QRD'].mean():+.3f}s")
        print(f"Overall std QRD: {qrd_df['QRD'].std():.3f}s")
        print(f"Best QRD (raced fastest): {qrd_df['QRD'].min():+.3f}s")
        print(f"Worst QRD (quali advantage): {qrd_df['QRD'].max():+.3f}s\n")

    def plot_qrd_analysis(self, qrd_df: pd.DataFrame, stats_df: pd.DataFrame):
        """Create visualizations of QRD analysis."""
        if qrd_df.empty or stats_df.empty:
            print("⚠️  No data to plot")
            return
        
        # Set style
        sns.set_style("whitegrid")
        
        # Figure with subplots
        fig, axes = plt.subplots(2, 2, figsize=(16, 12))
        fig.suptitle("QRD (Qualifying-Race Delta) Analysis - 2023 MotoGP Season", 
                     fontsize=16, fontweight='bold')
        
        # 1. QRD by Rider (Bar chart)
        ax = axes[0, 0]
        stats_sorted = stats_df.sort_values('Avg_QRD')
        colors = ['green' if x < 0 else 'orange' if x < 0.5 else 'red' 
                  for x in stats_sorted['Avg_QRD']]
        ax.barh(stats_sorted['Rider'], stats_sorted['Avg_QRD'], color=colors, alpha=0.7)
        ax.axvline(x=0, color='black', linestyle='--', linewidth=2)
        ax.set_xlabel('Avg QRD (seconds)', fontweight='bold')
        ax.set_title('Average QRD by Rider (Negative = Raced Faster)', fontweight='bold')
        ax.grid(axis='x', alpha=0.3)
        
        # 2. QRD Distribution (Violin plot)
        ax = axes[0, 1]
        qrd_data = []
        rider_labels = []
        for rider, group in qrd_df.groupby('Rider'):
            qrd_data.append(group['QRD'].values)
            rider_labels.append(rider)
        
        parts = ax.violinplot(qrd_data, positions=range(len(rider_labels)), 
                              showmeans=True, showmedians=True)
        ax.set_xticks(range(len(rider_labels)))
        ax.set_xticklabels(rider_labels, rotation=45, ha='right')
        ax.axhline(y=0, color='black', linestyle='--', linewidth=2)
        ax.set_ylabel('QRD (seconds)', fontweight='bold')
        ax.set_title('QRD Distribution by Rider', fontweight='bold')
        ax.grid(axis='y', alpha=0.3)
        
        # 3. QRD vs Consistency (Scatter)
        ax = axes[1, 0]
        scatter = ax.scatter(stats_df['Std_QRD'], stats_df['Avg_QRD'], 
                            s=stats_df['Rounds']*50, alpha=0.6, c=stats_df['DNFs'], 
                            cmap='RdYlGn_r')
        
        # Add rider labels
        for _, row in stats_df.iterrows():
            ax.annotate(row['Rider'], 
                       (row['Std_QRD'], row['Avg_QRD']),
                       fontsize=8, alpha=0.7)
        
        ax.axhline(y=0, color='black', linestyle='--', linewidth=1)
        ax.set_xlabel('Std Dev QRD (Consistency)', fontweight='bold')
        ax.set_ylabel('Avg QRD (Performance)', fontweight='bold')
        ax.set_title('QRD Performance vs Consistency\n(size=rounds, color=DNFs)', 
                    fontweight='bold')
        cbar = plt.colorbar(scatter, ax=ax)
        cbar.set_label('DNF Count')
        ax.grid(alpha=0.3)
        
        # 4. QRD by Round (Line plot)
        ax = axes[1, 1]
        for rider in qrd_df['Rider'].unique():
            rider_data = qrd_df[qrd_df['Rider'] == rider].sort_values('Round')
            ax.plot(rider_data['Round'], rider_data['QRD'], 
                   marker='o', label=rider, linewidth=2, markersize=4)
        
        ax.axhline(y=0, color='black', linestyle='--', linewidth=2, alpha=0.5)
        ax.set_xlabel('Round', fontweight='bold')
        ax.set_ylabel('QRD (seconds)', fontweight='bold')
        ax.set_title('QRD Trend Across Season', fontweight='bold')
        ax.grid(alpha=0.3)
        ax.legend(bbox_to_anchor=(1.05, 1), loc='upper left', fontsize=8)
        
        plt.tight_layout()
        
        # Save
        output_file = self.output_dir / "qrd_analysis_plots.png"
        plt.savefig(output_file, dpi=300, bbox_inches='tight')
        print(f"✅ Plots saved to {output_file}\n")
        plt.close()

    def save_results(self, qrd_df: pd.DataFrame, stats_df: pd.DataFrame):
        """Save analysis results to CSV files."""
        # Save full QRD data
        qrd_file = self.output_dir / "qrd_full_results.csv"
        qrd_df.to_csv(qrd_file, index=False)
        print(f"✅ Full QRD results saved to {qrd_file}")
        
        # Save statistics
        stats_file = self.output_dir / "qrd_season_statistics.csv"
        stats_df.to_csv(stats_file, index=False)
        print(f"✅ Season statistics saved to {stats_file}")


async def main():
    """Main entry point."""
    
    # 2023 Season circuit map
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
    
    # Create analyzer
    analyzer = QRDAnalyzer()
    
    # Analyze season
    qrd_df = await analyzer.analyze_season(CIRCUITS_2023)
    
    if not qrd_df.empty:
        # Get statistics
        stats_df = analyzer.get_season_statistics(qrd_df)
        
        # Print report
        analyzer.print_analysis_report(qrd_df, stats_df)
        
        # Create visualizations
        analyzer.plot_qrd_analysis(qrd_df, stats_df)
        
        # Save results
        analyzer.save_results(qrd_df, stats_df)
        
        print("\n✅ QRD Analysis Complete!")
    else:
        print("⚠️  No QRD data to analyze")


if __name__ == "__main__":
    asyncio.run(main())