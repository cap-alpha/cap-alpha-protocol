
import pandas as pd
import os

# Try to find the database or use raw CSVs as backup
data_raw_path = "data/raw/penalties/"
csv_files = []
if os.path.exists(data_raw_path):
    csv_files = [os.path.join(data_raw_path, f) for f in os.listdir(data_raw_path) if f.endswith('.csv')]

def run_analysis():
    print("--- Searching for specific player/team data ---")
    
    dfs = []
    for f in csv_files:
        try:
            df = pd.read_csv(f)
            # Normalize columns
            df.columns = [c.lower().replace(' ', '_') for c in df.columns]
            dfs.append(df)
        except:
            pass
            
    if not dfs:
        print("No penalty CSVs found in data/raw/penalties/")
        return

    full_df = pd.concat(dfs, ignore_index=True)
    
    # 1. Check Carlton Davis
    print("\n--- Carlton Davis Stats ---")
    davis = full_df[full_df['player_name_short'].astype(str).str.contains('C.Davis', case=False, na=False)]
    if not davis.empty:
        print(davis[['player_name_short', 'team_city', 'penalty_yards', 'year']].to_string())
    else:
        print("Carlton Davis not found in penalty files.")

    # 2. Check Seahawks (SEA/Seattle) and Patriots (NE/New England) Totals
    print("\n--- Team Penalty Totals (2024/2025) ---")
    if 'team_city' in full_df.columns and 'penalty_yards' in full_df.columns:
        team_stats = full_df.groupby(['team_city', 'year'])['penalty_yards'].sum().reset_index()
        
        target_teams = ['Seattle', 'New England', 'Detroit', 'Denver'] # Including DEN/DET for context
        print(team_stats[team_stats['team_city'].isin(target_teams)].sort_values(['year', 'penalty_yards']))
        
        # Calculate strict ranking
        print("\n--- League Rankings (Low Penalties = Good) ---")
        for year in team_stats['year'].unique():
            print(f"\nYear: {year}")
            year_data = team_stats[team_stats['year'] == year].sort_values('penalty_yards')
            year_data['rank'] = range(1, len(year_data) + 1)
            print(year_data[year_data['team_city'].isin(target_teams)])

if __name__ == "__main__":
    run_analysis()
