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


class ISDAnalyzer:
    """
    ISD (In-Session Sustainability Delta) Analyzer
    
    ISD = Best Lap Time - Final Lap Time (in same session)
    
    Positive ISD: Degradation (final lap slower than best) - typical
    Negative ISD: Improvement (final lap faster than best) - rare
    Small ISD (<0.3s): Excellent tire management
    Large ISD (>1.5s): Major tire/fuel issues or DNF
    
    This analyzer:
    - Parses race PDFs
    - Calculates sustainability metrics
    - Identifies tire management quality
    - Predicts DNF risk
    - Compares qualifying vs race sustainability
    - Produces detailed visualizations
    """

    def __init__(self,
                 qual_pdf_dir: str = "./data/raw/motogp_data/qualifying",
                 race_pdf_dir: str = "./data/raw/motogp_data/race",
                 output_dir: str = "./analysis/isd_results"):
        
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
        
        # Parse qualifying
        if qual_file.exists():
            try:
                qual_data = self.parser.parse_pdf_analysis(str(qual_file), total_laps=12, debug=False)
                qual_df = pd.DataFrame(qual_data)
            except Exception as e:
                print(f"  ⚠️  Error parsing qualifying: {str(e)}")
        
        # Parse race
        if race_file.exists():
            try:
                race_data = self.parser.parse_pdf_analysis(str(race_file), total_laps=27, debug=False)
                race_df = pd.DataFrame(race_data)
            except Exception as e:
                print(f"  ⚠️  Error parsing race: {str(e)}")
        
        return qual_df, race_df

    def calculate_isd_metrics(self, 
                              lap_times: pd.Series) -> Dict[str, float]:
        """
        Calculate comprehensive ISD metrics from lap times.
        
        Args:
            lap_times: Series of lap times for a rider in a session
        
        Returns:
            dict with ISD metrics
        """
        if len(lap_times) < 2:
            return None
        
        best_lap = lap_times.min()
        first_lap = lap_times.iloc[0]
        final_lap = lap_times.iloc[-1]
        avg_lap = lap_times.mean()
        
        # ISD: Best lap - Final lap (positive = degradation)
        isd = final_lap - best_lap
        
        # Find lap where best time was achieved
        lap_of_best = lap_times.idxmin()
        laps_after_best = len(lap_times) - lap_of_best - 1
        
        # Degradation rate per lap (after best lap)
        if laps_after_best > 0:
            degrade_rate = isd / laps_after_best
        else:
            degrade_rate = 0
        
        # Consistency metric (std dev of all lap times)
        consistency = lap_times.std()
        
        # Warm-up time (first lap - best lap)
        warm_up_time = first_lap - best_lap
        
        # Lap count
        total_laps = len(lap_times)
        
        return {
            "best_lap": best_lap,
            "final_lap": final_lap,
            "first_lap": first_lap,
            "avg_lap": avg_lap,
            "isd": isd,
            "lap_of_best": lap_of_best,
            "laps_after_best": laps_after_best,
            "degrade_rate": degrade_rate,
            "consistency": consistency,
            "warm_up_time": warm_up_time,
            "total_laps": total_laps,
        }

    async def analyze_session(self,
                             session_df: pd.DataFrame,
                             session_type: str = "race") -> Optional[pd.DataFrame]:
        """
        Analyze ISD for all riders in a session.
        
        Args:
            session_df: DataFrame with columns ['rider', 'lap', 'raw_time', 'adj_time']
            session_type: "race" or "qualifying"
        
        Returns:
            DataFrame with ISD metrics for all riders
        """
        if session_df is None or session_df.empty:
            return None
        
        results = []
        
        for rider, group in session_df.groupby('rider'):
            # Sort by lap number
            group = group.sort_values('lap')
            
            # Use adjusted times if available, otherwise raw times
            if 'adj_time' in group.columns:
                lap_times = group['adj_time']
            else:
                lap_times = group['raw_time']
            
            # Calculate metrics
            metrics = self.calculate_isd_metrics(lap_times)
            
            if metrics:
                results.append({
                    "Rider": rider,
                    "Best_Lap": round(metrics['best_lap'], 3),
                    "Final_Lap": round(metrics['final_lap'], 3),
                    "First_Lap": round(metrics['first_lap'], 3),
                    "Avg_Lap": round(metrics['avg_lap'], 3),
                    "ISD": round(metrics['isd'], 3),
                    "Lap_of_Best": int(metrics['lap_of_best']),
                    "Laps_After_Best": metrics['laps_after_best'],
                    "Degrade_Rate": round(metrics['degrade_rate'], 4),
                    "Consistency": round(metrics['consistency'], 3),
                    "Warm_Up_Time": round(metrics['warm_up_time'], 3),
                    "Total_Laps": metrics['total_laps'],
                    "Session_Type": session_type,
                })
        
        return pd.DataFrame(results).sort_values('ISD') if results else None

    async def analyze_round(self,
                           round_num: int,
                           circuit: str,
                           qual_df: Optional[pd.DataFrame],
                           race_df: Optional[pd.DataFrame]) -> Tuple[Optional[pd.DataFrame], Optional[pd.DataFrame]]:
        """
        Analyze ISD for both qualifying and race in a round.
        
        Args:
            round_num: Round number
            circuit: Circuit code
            qual_df: Qualifying data
            race_df: Race data
        
        Returns:
            (qual_isd_df, race_isd_df) tuple
        """
        qual_isd = None
        race_isd = None
        
        if qual_df is not None and not qual_df.empty:
            qual_isd = await self.analyze_session(qual_df, session_type="qualifying")
            if qual_isd is not None:
                qual_isd.insert(0, 'Round', round_num)
                qual_isd.insert(1, 'Circuit', circuit)
        
        if race_df is not None and not race_df.empty:
            race_isd = await self.analyze_session(race_df, session_type="race")
            if race_isd is not None:
                race_isd.insert(0, 'Round', round_num)
                race_isd.insert(1, 'Circuit', circuit)
        
        return qual_isd, race_isd

    async def analyze_season(self,
                            circuits_dict: Dict[int, Tuple[str, str, str]]) -> Tuple[pd.DataFrame, pd.DataFrame]:
        """
        Analyze ISD for entire season.
        
        Args:
            circuits_dict: {round_num: (code, country, name), ...}
        
        Returns:
            (qual_isd_all, race_isd_all) tuple with all ISD data
        """
        all_qual_results = []
        all_race_results = []
        
        print("\n" + "="*80)
        print("🏍️  MOTOGP ISD (IN-SESSION SUSTAINABILITY DELTA) ANALYSIS")
        print("="*80 + "\n")
        
        for round_num, (code, country, name) in circuits_dict.items():
            print(f"Round {round_num:2d}: {country:15s} ({name:30s})")
            
            # Parse PDFs
            qual_df, race_df = await self.parse_round_data(round_num, code)
            
            if qual_df is not None or race_df is not None:
                # Analyze
                qual_isd, race_isd = await self.analyze_round(
                    round_num=round_num,
                    circuit=code,
                    qual_df=qual_df,
                    race_df=race_df
                )
                
                if qual_isd is not None:
                    all_qual_results.append(qual_isd)
                    print(f"  ✅ Qualifying: {len(qual_isd)} riders")
                else:
                    print(f"  ⚠️  No qualifying data")
                
                if race_isd is not None:
                    all_race_results.append(race_isd)
                    print(f"  ✅ Race: {len(race_isd)} riders")
                else:
                    print(f"  ⚠️  No race data")
            else:
                print(f"  ❌ Missing PDFs")
            
            print()
        
        # Combine all results
        qual_isd_all = pd.concat(all_qual_results, ignore_index=True) if all_qual_results else pd.DataFrame()
        race_isd_all = pd.concat(all_race_results, ignore_index=True) if all_race_results else pd.DataFrame()
        
        return qual_isd_all, race_isd_all

    def get_season_statistics(self, isd_df: pd.DataFrame, session_type: str = "race") -> pd.DataFrame:
        """
        Calculate season-wide ISD statistics by rider.
        
        Args:
            isd_df: DataFrame with all ISD data
            session_type: "race" or "qualifying"
        
        Returns:
            DataFrame with rider statistics
        """
        if isd_df.empty:
            return pd.DataFrame()
        
        stats = []
        
        for rider, group in isd_df.groupby('Rider'):
            dnf_count = len(group[group['Total_Laps'] < 20])
            finished_count = len(group[group['Total_Laps'] >= 20])
            
            stats.append({
                "Rider": rider,
                "Rounds": len(group),
                "Avg_ISD": round(group['ISD'].mean(), 3),
                "Std_ISD": round(group['ISD'].std(), 3),
                "Min_ISD": round(group['ISD'].min(), 3),
                "Max_ISD": round(group['ISD'].max(), 3),
                "Avg_Best_Lap": round(group['Best_Lap'].mean(), 3),
                "Avg_Final_Lap": round(group['Final_Lap'].mean(), 3),
                "Avg_Consistency": round(group['Consistency'].mean(), 3),
                "Avg_Degrade_Rate": round(group['Degrade_Rate'].mean(), 4),
                "Avg_Laps_Completed": round(group['Total_Laps'].mean(), 1),
                "Finishes": finished_count,
                "DNFs": dnf_count,
            })
        
        return pd.DataFrame(stats).sort_values('Avg_ISD')

    def categorize_drivers(self, stats_df: pd.DataFrame) -> Dict:
        """
        Categorize drivers by their ISD performance.
        
        Returns:
            dict with driver categories and explanations
        """
        categories = {
            "🚀 Elite Sustainers": [],          # ISD < 0.3s
            "✅ Excellent Managers": [],        # ISD 0.3-0.5s
            "⚖️  Good Performers": [],         # ISD 0.5-0.8s
            "⚠️  Moderate Degraders": [],      # ISD 0.8-1.5s
            "📉 Significant Issues": [],       # ISD > 1.5s
        }
        
        for _, row in stats_df.iterrows():
            rider = row['Rider']
            avg_isd = row['Avg_ISD']
            
            info = {
                "rider": rider,
                "avg_isd": avg_isd,
                "std_isd": row['Std_ISD'],
                "rounds": row['Rounds'],
                "dnfs": row['DNFs'],
                "consistency": row['Avg_Consistency'],
            }
            
            if avg_isd < 0.3:
                categories["🚀 Elite Sustainers"].append(info)
            elif avg_isd < 0.5:
                categories["✅ Excellent Managers"].append(info)
            elif avg_isd < 0.8:
                categories["⚖️  Good Performers"].append(info)
            elif avg_isd < 1.5:
                categories["⚠️  Moderate Degraders"].append(info)
            else:
                categories["📉 Significant Issues"].append(info)
        
        # Sort by ISD within each category
        for category in categories:
            categories[category].sort(key=lambda x: x['avg_isd'])
        
        return categories

    def identify_dnf_risk(self, isd_df: pd.DataFrame) -> Dict:
        """
        Identify riders at risk of DNF based on ISD patterns.
        
        Returns:
            dict with DNF risk assessment
        """
        risk_assessment = {}
        
        for _, row in isd_df.iterrows():
            rider = row['Rider']
            
            if rider not in risk_assessment:
                risk_assessment[rider] = {
                    "early_exits": 0,
                    "high_degrade": 0,
                    "inconsistent": 0,
                    "rounds": 0,
                    "risk_score": 0,
                }
            
            # Check for early exit (DNF)
            if row['Total_Laps'] < 20:
                risk_assessment[rider]["early_exits"] += 1
            
            # Check for high degradation rate
            if row['Degrade_Rate'] > 0.15:
                risk_assessment[rider]["high_degrade"] += 1
            
            # Check for inconsistent performance
            if row['Consistency'] > 1.0:
                risk_assessment[rider]["inconsistent"] += 1
            
            risk_assessment[rider]["rounds"] += 1
        
        # Calculate risk scores
        for rider, metrics in risk_assessment.items():
            score = 0
            score += metrics["early_exits"] * 30
            score += metrics["high_degrade"] * 15
            score += metrics["inconsistent"] * 10
            
            if metrics["rounds"] > 0:
                risk_percentage = (score / (metrics["rounds"] * 100)) * 100
            else:
                risk_percentage = 0
            
            metrics["risk_score"] = risk_percentage
            metrics["risk_level"] = (
                "🔴 CRITICAL" if risk_percentage > 50 else
                "⚠️  HIGH" if risk_percentage > 30 else
                "✅ LOW"
            )
        
        return risk_assessment

    def print_analysis_report(self, 
                             race_isd_df: pd.DataFrame, 
                             race_stats_df: pd.DataFrame,
                             qual_isd_df: Optional[pd.DataFrame] = None,
                             qual_stats_df: Optional[pd.DataFrame] = None):
        """Print formatted analysis report."""
        
        print("\n" + "="*80)
        print("📊 ISD ANALYSIS SUMMARY - RACE SESSION")
        print("="*80 + "\n")
        
        print("🔍 INTERPRETATION GUIDE:")
        print("  • ISD = Best Lap - Final Lap (in same session)")
        print("  • Positive ISD: Degradation (typical, tire wear)")
        print("  • Negative ISD: Improvement (rare, gaining pace)")
        print("  • Small ISD (<0.3s): Elite tire management")
        print("  • Large ISD (>1.5s): Major issues or DNF\n")
        
        # Print race categories
        categories = self.categorize_drivers(race_stats_df)
        
        for category, drivers in categories.items():
            if drivers:
                print(f"\n{category}")
                print("-" * 80)
                for d in drivers:
                    dnf_info = f" ⚠️  DNF: {d['dnfs']}" if d['dnfs'] > 0 else ""
                    consistency = "✅ Consistent" if d['std_isd'] < 0.3 else "⚠️  Variable"
                    print(f"  {d['rider']:<15} ISD: {d['avg_isd']:+.3f}s "
                          f"(σ: {d['std_isd']:.3f}s) Consistency: {d['consistency']:.3f}s "
                          f"[{d['rounds']} rounds]{dnf_info} {consistency}")
        
        # DNF Risk Assessment
        print("\n\n🚨 DNF RISK ASSESSMENT")
        print("="*80)
        risk = self.identify_dnf_risk(race_isd_df)
        for rider in sorted(risk.keys()):
            metrics = risk[rider]
            print(f"\n{rider:15} {metrics['risk_level']}")
            print(f"  Early exits:      {metrics['early_exits']}/{metrics['rounds']}")
            print(f"  High degrade:     {metrics['high_degrade']}/{metrics['rounds']}")
            print(f"  Inconsistent:     {metrics['inconsistent']}/{metrics['rounds']}")
            print(f"  Risk Score:       {metrics['risk_score']:.1f}%")
        
        # Season Statistics
        print("\n\n" + "="*80)
        print("📈 RACE SEASON STATISTICS")
        print("="*80 + "\n")
        print(f"Total rounds analyzed: {race_isd_df['Round'].nunique()}")
        print(f"Total drivers: {race_isd_df['Rider'].nunique()}")
        print(f"Overall avg ISD: {race_isd_df['ISD'].mean():+.3f}s")
        print(f"Overall std ISD: {race_isd_df['ISD'].std():.3f}s")
        print(f"Best sustainability: {race_isd_df['ISD'].min():+.3f}s")
        print(f"Worst sustainability: {race_isd_df['ISD'].max():+.3f}s")
        print(f"Avg laps completed: {race_isd_df['Total_Laps'].mean():.1f}")
        
        # Qualifying comparison if available
        if qual_isd_df is not None and not qual_isd_df.empty:
            print("\n\n" + "="*80)
            print("📈 QUALIFYING vs RACE COMPARISON")
            print("="*80 + "\n")
            print(f"Qualifying avg ISD: {qual_isd_df['ISD'].mean():+.3f}s")
            print(f"Race avg ISD: {race_isd_df['ISD'].mean():+.3f}s")
            print(f"Difference: {(race_isd_df['ISD'].mean() - qual_isd_df['ISD'].mean()):+.3f}s")
            print("\n  → Positive diff: Riders degrade more in race (expected)")
            print("  → Negative diff: Riders sustain better in race (tire management)")

    def plot_isd_analysis(self, 
                         race_isd_df: pd.DataFrame, 
                         race_stats_df: pd.DataFrame,
                         qual_isd_df: Optional[pd.DataFrame] = None):
        """Create visualizations of ISD analysis."""
        if race_isd_df.empty or race_stats_df.empty:
            print("⚠️  No data to plot")
            return
        
        sns.set_style("whitegrid")
        
        fig, axes = plt.subplots(2, 3, figsize=(18, 12))
        fig.suptitle("ISD (In-Session Sustainability Delta) Analysis - 2023 MotoGP Season", 
                     fontsize=16, fontweight='bold')
        
        # 1. Race ISD by Rider (Bar chart)
        ax = axes[0, 0]
        stats_sorted = race_stats_df.sort_values('Avg_ISD')
        colors = ['green' if x < 0.3 else 'yellow' if x < 0.8 else 'orange' if x < 1.5 else 'red'
                  for x in stats_sorted['Avg_ISD']]
        ax.barh(stats_sorted['Rider'], stats_sorted['Avg_ISD'], color=colors, alpha=0.7)
        ax.set_xlabel('Avg ISD (seconds)', fontweight='bold')
        ax.set_title('Race Average ISD by Rider\n(Green=Elite, Red=Issues)', fontweight='bold')
        ax.grid(axis='x', alpha=0.3)
        
        # 2. ISD Distribution (Violin plot)
        ax = axes[0, 1]
        isd_data = []
        rider_labels = []
        for rider, group in race_isd_df.groupby('Rider'):
            isd_data.append(group['ISD'].values)
            rider_labels.append(rider)
        
        parts = ax.violinplot(isd_data, positions=range(len(rider_labels)),
                              showmeans=True, showmedians=True)
        ax.set_xticks(range(len(rider_labels)))
        ax.set_xticklabels(rider_labels, rotation=45, ha='right')
        ax.set_ylabel('ISD (seconds)', fontweight='bold')
        ax.set_title('ISD Distribution Across Races', fontweight='bold')
        ax.grid(axis='y', alpha=0.3)
        
        # 3. ISD vs Consistency (Scatter)
        ax = axes[0, 2]
        scatter = ax.scatter(race_stats_df['Avg_Consistency'], 
                            race_stats_df['Avg_ISD'],
                            s=race_stats_df['Rounds']*100,
                            alpha=0.6,
                            c=race_stats_df['DNFs'],
                            cmap='RdYlGn_r')
        
        for _, row in race_stats_df.iterrows():
            ax.annotate(row['Rider'],
                       (row['Avg_Consistency'], row['Avg_ISD']),
                       fontsize=8, alpha=0.7)
        
        ax.set_xlabel('Avg Consistency σ', fontweight='bold')
        ax.set_ylabel('Avg ISD (seconds)', fontweight='bold')
        ax.set_title('ISD vs Consistency\n(size=rounds, color=DNFs)', fontweight='bold')
        cbar = plt.colorbar(scatter, ax=ax)
        cbar.set_label('DNF Count')
        ax.grid(alpha=0.3)
        
        # 4. Degradation Rate (seconds per lap)
        ax = axes[1, 0]
        stats_degrade = race_stats_df.sort_values('Avg_Degrade_Rate')
        colors = ['green' if x < 0.05 else 'yellow' if x < 0.15 else 'red'
                  for x in stats_degrade['Avg_Degrade_Rate']]
        ax.barh(stats_degrade['Rider'], stats_degrade['Avg_Degrade_Rate'], 
               color=colors, alpha=0.7)
        ax.set_xlabel('Degrade Rate (s/lap)', fontweight='bold')
        ax.set_title('Tire Degradation Rate\n(Green=Excellent, Red=Poor)', fontweight='bold')
        ax.grid(axis='x', alpha=0.3)
        
        # 5. ISD Trend by Round (Line plot)
        ax = axes[1, 1]
        for rider in race_isd_df['Rider'].unique()[:10]:  # Top 10 for clarity
            rider_data = race_isd_df[race_isd_df['Rider'] == rider].sort_values('Round')
            ax.plot(rider_data['Round'], rider_data['ISD'],
                   marker='o', label=rider, linewidth=2, markersize=4)
        
        ax.set_xlabel('Round', fontweight='bold')
        ax.set_ylabel('ISD (seconds)', fontweight='bold')
        ax.set_title('ISD Trend Across Season (Top 10)', fontweight='bold')
        ax.grid(alpha=0.3)
        ax.legend(fontsize=8, loc='best')
        
        # 6. DNF Analysis
        ax = axes[1, 2]
        dnf_data = race_stats_df[race_stats_df['DNFs'] > 0].sort_values('DNFs', ascending=False)
        if not dnf_data.empty:
            ax.barh(dnf_data['Rider'], dnf_data['DNFs'], color='red', alpha=0.7)
            ax.set_xlabel('Number of DNFs', fontweight='bold')
            ax.set_title('DNF Count by Rider', fontweight='bold')
        else:
            ax.text(0.5, 0.5, 'No DNFs Found', ha='center', va='center', fontsize=14)
        ax.grid(axis='x', alpha=0.3)
        
        plt.tight_layout()
        
        # Save
        output_file = self.output_dir / "isd_analysis_plots.png"
        plt.savefig(output_file, dpi=300, bbox_inches='tight')
        print(f"✅ Plots saved to {output_file}\n")
        plt.close()

    def save_results(self, 
                    race_isd_df: pd.DataFrame, 
                    race_stats_df: pd.DataFrame,
                    qual_isd_df: Optional[pd.DataFrame] = None,
                    qual_stats_df: Optional[pd.DataFrame] = None):
        """Save analysis results to CSV files."""
        
        # Save race ISD data
        race_isd_file = self.output_dir / "isd_race_full_results.csv"
        race_isd_df.to_csv(race_isd_file, index=False)
        print(f"✅ Race ISD results saved to {race_isd_file}")
        
        # Save race statistics
        race_stats_file = self.output_dir / "isd_race_season_statistics.csv"
        race_stats_df.to_csv(race_stats_file, index=False)
        print(f"✅ Race season statistics saved to {race_stats_file}")
        
        # Save qualifying data if available
        if qual_isd_df is not None and not qual_isd_df.empty:
            qual_isd_file = self.output_dir / "isd_qual_full_results.csv"
            qual_isd_df.to_csv(qual_isd_file, index=False)
            print(f"✅ Qualifying ISD results saved to {qual_isd_file}")
            
            qual_stats_file = self.output_dir / "isd_qual_season_statistics.csv"
            qual_stats_df.to_csv(qual_stats_file, index=False)
            print(f"✅ Qualifying season statistics saved to {qual_stats_file}")


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
    analyzer = ISDAnalyzer()
    
    # Analyze season
    qual_isd_all, race_isd_all = await analyzer.analyze_season(CIRCUITS_2023)
    
    if not race_isd_all.empty:
        # Get statistics
        race_stats_df = analyzer.get_season_statistics(race_isd_all, session_type="race")
        qual_stats_df = analyzer.get_season_statistics(qual_isd_all, session_type="qualifying") if not qual_isd_all.empty else None
        
        # Print report
        analyzer.print_analysis_report(race_isd_all, race_stats_df, qual_isd_all, qual_stats_df)
        
        # Create visualizations
        analyzer.plot_isd_analysis(race_isd_all, race_stats_df, qual_isd_all)
        
        # Save results
        analyzer.save_results(race_isd_all, race_stats_df, qual_isd_all, qual_stats_df)
        
        print("\n✅ ISD Analysis Complete!")
    else:
        print("⚠️  No ISD data to analyze")


if __name__ == "__main__":
    asyncio.run(main())