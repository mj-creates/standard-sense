import sqlite3
import datetime

conn = sqlite3.connect("compliance_audit.db")
c = conn.cursor()
c.execute('''CREATE TABLE IF NOT EXISTS audit_log
             (timestamp TEXT, reference TEXT, clause TEXT, standard TEXT, verdict TEXT)''')

logs = [
    ("Structural Steel Reinforcement", "IS 1786", "Compliant"),
    ("Concrete Mix Design", "IS 456", "Compliant"),
    ("Water-Cement Ratio Constraints", "IS 456", "Compliant"),
    ("Cement Standards", "IS 8112", "Compliant")
]

now = datetime.datetime.now().isoformat()
for clause, std, verdict in logs:
    c.execute("INSERT INTO audit_log VALUES (?, ?, ?, ?, ?)", (now, "NHAI/2026/CIVIL-049", clause, std, verdict))

conn.commit()
conn.close()
print("Audit log successfully written to compliance_audit.db")
