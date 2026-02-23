import duckdb

con = duckdb.connect('data/nfl_production.db')
print("Tables in nfl_production:")
print(con.execute("SHOW TABLES").df())

