"""One-off script to standardize all user password hashes in dev DB."""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text
from app.core.database import engine

NEW_HASH = "$2b$12$PpeIPwx6wUWQ7GuuACenQuDcyUHVrm9E.eTaQneJNAcVmz4u6d.qa"

with engine.connect() as conn:
    rows = conn.execute(text("SELECT id, email, full_name FROM users ORDER BY email")).fetchall()
    print("USERS BEFORE:")
    for r in rows:
        print(f"  {r.id}  {r.email}  ({r.full_name})")
    print()

    result = conn.execute(
        text("UPDATE users SET password_hash = :h"),
        {"h": NEW_HASH},
    )
    print(f"Rows updated: {result.rowcount}")
    conn.commit()
    print()

    rows2 = conn.execute(
        text(
            "SELECT email, "
            "substring(password_hash from 1 for 10) || '...' AS hash_prefix "
            "FROM users ORDER BY email"
        )
    ).fetchall()
    print("USERS AFTER (all sharing the same hash):")
    for r in rows2:
        print(f"  {r.email}  ->  {r.hash_prefix}")

engine.dispose()
print()
print("All users can now log in with password: pass1234")
