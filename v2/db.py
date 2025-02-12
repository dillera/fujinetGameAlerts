import sqlite3
from flask import g

def get_db(app):
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(app.config['DATABASE'])
    return db

def close_connection(exception):
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()

def setup_database():
    conn = sqlite3.connect('gameEvents.db')
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS gameEvents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created DATETIME,
            event_type TEXT,
            game TEXT,
            appkey INTEGER,
            server TEXT,
            region TEXT,
            serverurl TEXT,
            status TEXT,
            maxplayers INTEGER,
            curplayers INTEGER
        )
    ''')
    conn.commit()
    conn.close()

    conn = sqlite3.connect('smsErrors.db')
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS smsErrors (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp DATETIME,
            resource_sid TEXT,
            service_sid TEXT,
            error_code TEXT,
            error_message TEXT,
            callback_url TEXT,
            request_method TEXT,
            error_details TEXT
        )
    ''')
    conn.commit()
    conn.close()

    conn = sqlite3.connect('playerTracking.db')
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS playerTracking (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            game TEXT UNIQUE,
            curplayers INTEGER,
            total_players INTEGER DEFAULT 0,
            created DATETIME
        )
    ''')
    conn.commit()
    conn.close()

    conn = sqlite3.connect('serverTracking.db')
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS serverTracking (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created DATETIME,
            serverurl TEXT,
            currentplayers INTEGER,
            total_updates INTEGER DEFAULT 0
        )
    ''')
    conn.commit()
    conn.close()

    # Create globalSync table to track app-wide sync status
    conn = sqlite3.connect('globalSync.db')
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS globalSync (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            last_sync DATETIME,
            sync_type TEXT
        )
    ''')
    conn.commit()
    conn.close()
