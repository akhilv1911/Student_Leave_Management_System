import sqlite3
import os

DATABASE = 'database.db'

def migrate_accounts():
    """Migrates old user accounts by adding missing columns and setting a default value."""
    if not os.path.exists(DATABASE):
        print("Database file not found. Please run the Flask app once to create it.")
        return

    try:
        conn = sqlite3.connect(DATABASE)
        cursor = conn.cursor()

        # Check for the existence of the `is_verified` column
        cursor.execute("PRAGMA table_info(users)")
        columns = [column[1] for column in cursor.fetchall()]

        if 'is_verified' not in columns:
            print("Adding 'is_verified' and 'verification_token' columns...")
            cursor.execute("ALTER TABLE users ADD COLUMN is_verified INTEGER NOT NULL DEFAULT 1")
            cursor.execute("ALTER TABLE users ADD COLUMN verification_token TEXT")
            conn.commit()
            print("Migration complete. Old accounts are now marked as verified.")
        else:
            print("Migration already performed. Columns exist.")

        conn.close()

    except sqlite3.OperationalError as e:
        print(f"Error during migration: {e}")
        print("Please ensure the Flask server is not running and try again.")
    
if __name__ == "__main__":
    migrate_accounts()