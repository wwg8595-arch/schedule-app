import sqlite3
import os

# Use absolute path so it works both locally and on Render
DATABASE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'database.db')

def get_db_connection():
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Create rooms table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS rooms (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Create candidates table (dates)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS candidates (
            id TEXT PRIMARY KEY,
            room_id TEXT NOT NULL,
            date_str TEXT NOT NULL,
            FOREIGN KEY (room_id) REFERENCES rooms (id) ON DELETE CASCADE
        )
    ''')
    
    # Create votes table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS votes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            room_id TEXT NOT NULL,
            candidate_id TEXT NOT NULL,
            voter_name TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (room_id) REFERENCES rooms (id) ON DELETE CASCADE,
            FOREIGN KEY (candidate_id) REFERENCES candidates (id) ON DELETE CASCADE,
            UNIQUE(room_id, candidate_id, voter_name)
        )
    ''')
    
    conn.commit()
    conn.close()
    print("Database initialized successfully.")

if __name__ == '__main__':
    init_db()
