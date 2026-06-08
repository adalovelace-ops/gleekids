import os
import psycopg
from environ import Env

env = Env()
Env.read_env('.env')

conn_str = f"host={env('DB_HOST')} port={env('DB_PORT')} dbname={env('DB_NAME')} user={env('DB_USER')} password={env('DB_PASSWORD')}"

with psycopg.connect(conn_str) as conn:
    with conn.cursor() as cur:
        cur.execute("DELETE FROM django_migrations WHERE app = 'ats_new';")
        conn.commit()
print("Migration history cleared for ats_new.")
