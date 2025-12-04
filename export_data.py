import sqlite3
import os

DATABASE = 'database.db'

def fetch_and_print_table(table_name):
    print(f"\n--- Data from Table: {table_name.upper()} ---")
    try:
        conn = sqlite3.connect(DATABASE)
        # Use Row factory to access columns by name
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute(f"SELECT * FROM {table_name}")
        rows = cursor.fetchall()
        
        if not rows:
            print("No records found.")
            return

        # Print header (column names)
        header = [description[0] for description in cursor.description]
        print("| " + " | ".join(header) + " |")
        print("|" + "---|" * len(header))

        # Print data rows
        for row in rows:
            print("| " + " | ".join(str(row[col]) for col in header) + " |")

    except sqlite3.OperationalError as e:
        print(f"ERROR: Could not access table '{table_name}'. Ensure the table exists and the Flask server is stopped.")
        print(f"SQLite Error: {e}")
    finally:
        if conn:
            conn.close()

if __name__ == "__main__":
    if not os.path.exists(DATABASE):
        print("ERROR: database.db file not found. Please run 'flask run' once to create it.")
    else:
        # CRUCIAL: Must stop the Flask server before running this.
        fetch_and_print_table('users')
        fetch_and_print_table('leave_requests')