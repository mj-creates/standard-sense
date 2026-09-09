import sqlite3
import json
import os

db_path = "sih_standards.db"
meta_path = "semantic_search/is_metadata.json"

if not os.path.exists(db_path):
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    c.execute('''CREATE TABLE standards (is_code TEXT PRIMARY KEY, title TEXT, description TEXT)''')
    
    with open(meta_path, "r", encoding="utf-8") as f:
        metadata = json.load(f)
        
    for k, v in metadata.items():
        c.execute("INSERT OR REPLACE INTO standards VALUES (?, ?, ?)", (v['is_code'], v['title'], v['description']))
        
    conn.commit()
    conn.close()
    print("Populated sih_standards.db")
