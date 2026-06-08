import os
import psycopg
from environ import Env

env = Env()
Env.read_env('.env')

conn_str = f"host={env('DB_HOST')} port={env('DB_PORT')} dbname={env('DB_NAME')} user={env('DB_USER')} password={env('DB_PASSWORD')}"

with psycopg.connect(conn_str) as conn:
    with conn.cursor() as cur:
        # Drop tables in reverse order of dependencies
        cur.execute("DROP TABLE IF EXISTS ats_new_evaluation CASCADE;")
        cur.execute("DROP TABLE IF EXISTS ats_new_schedule CASCADE;")
        cur.execute("DROP TABLE IF EXISTS ats_new_applicant CASCADE;")
        conn.commit()
print("Tables dropped successfully.")
