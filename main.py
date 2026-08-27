import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()

conn = psycopg2.connect(
    host=os.getenv("PG_HOST"),
    port=os.getenv("PG_PORT"),
    database=os.getenv("PG_DB"),
    user=os.getenv("PG_USER"),
    password=os.getenv("PG_PASSWORD")
)

cursor = conn.cursor()

query = """
SELECT
    table_schema,
    table_name,
    column_name
FROM information_schema.columns
WHERE column_name ILIKE '%username%'
ORDER BY table_schema, table_name;
"""

cursor.execute(query)

rows = cursor.fetchall()

for row in rows:
    print(row)

cursor.close()
conn.close()


