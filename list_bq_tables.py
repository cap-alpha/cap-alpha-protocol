from google.cloud import bigquery
import os
os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "/Users/andrewsmith/.config/gcloud/application_default_credentials.json"
client = bigquery.Client(project="cap-alpha-protocol")
print("Tables in nfl_dead_money:")
tables = client.list_tables("nfl_dead_money")
for table in tables:
    print(table.table_id)

for t in ["prediction_results", "media_lag_metrics", "audit_ledger_blocks", "audit_ledger_entries"]:
    try:
        table = client.get_table(f"cap-alpha-protocol.nfl_dead_money.{t}")
        print(f"\n--- {t} ---")
        for schema in table.schema:
            print(f"{schema.name}: {schema.field_type}")
    except Exception as e:
        print(f"\nError {t}: {e}")
