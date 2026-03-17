import sys
import os

# Add pipeline root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../')))

from src.db_manager import DBManager

def main():
    db = DBManager()
    print("Checking for Mocked data in media_lag_metrics...")
    try:
        df = db.fetch_df("SELECT * FROM media_lag_metrics WHERE rationale LIKE '%Mocked%'")
        print(f"Found {len(df)} mocked rows.")
        if len(df) > 0:
            print("Examples:")
            print(df[['player_name', 'rationale']].head())
            
            db.execute("DELETE FROM media_lag_metrics WHERE rationale LIKE '%Mocked%'")
            print("Successfully deleted mocked records.")
    except Exception as e:
        print("Error checking/deleting media_lag_metrics:", e)

    print("\nChecking prediction_results for 'Mocked' just in case...")
    try:
         # wait, prediction_results doesn't have rationale usually, but let's check
         df = db.fetch_df("SELECT * FROM information_schema.columns WHERE table_name='prediction_results' AND column_name='rationale'")
         if len(df) > 0:
            mocked_preds = db.fetch_df("SELECT * FROM prediction_results WHERE rationale LIKE '%Mocked%'")
            if len(mocked_preds) > 0:
                print(f"Found {len(mocked_preds)} in prediction_results")
                db.execute("DELETE FROM prediction_results WHERE rationale LIKE '%Mocked%'")
    except Exception as e:
        pass
        
if __name__ == '__main__':
    main()
