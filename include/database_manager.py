#!/usr/bin/env python3
"""
Database Manager for File Monitor Service

Manages MySQL database operations for file activity logging.
"""

import os
import sys
import json
import threading
import queue
from pathlib import Path
from datetime import datetime

# MySQL imports
try:
    import mysql.connector
    from mysql.connector import Error
    MYSQL_AVAILABLE = True
except ImportError:
    MYSQL_AVAILABLE = False
    print("Warning: mysql-connector not installed. Database logging will be disabled.")
    print("Install with: sudo apt install python3-mysql.connector")


class DatabaseManager:
    """Manages MySQL database operations for file activity logging."""
    
    def __init__(self, host, user, password, database, port=3306):
        self.host = host
        self.user = user
        self.password = password
        self.database = database
        self.port = port
        self.connection = None
        self.connected = False
        self.operation_queue = queue.Queue()
        self.worker_thread = None
        
    def connect(self):
        """Establish MySQL connection and create tables if needed."""
        try:
            self.connection = mysql.connector.connect(
                host=self.host,
                user=self.user,
                password=self.password,
                database=self.database,
                port=self.port,
                autocommit=True
            )
            
            if self.connection.is_connected():
                self.connected = True
                print(f"✅ Connected to MySQL database: {self.user}@{self.host}:{self.port}/{self.database}")
                self.create_tables()
                return True
                
        except Error as e:
            print(f"❌ MySQL connection failed: {e}")
            self.connected = False
            return False
    
    def disconnect(self):
        """Close MySQL connection."""
        if self.connection and self.connection.is_connected():
            self.connection.close()
        self.connected = False
        print("🔌 MySQL connection closed")
    
    def create_tables(self):
        """Create necessary tables if they don't exist."""
        try:
            cursor = self.connection.cursor()
            
            # File activity table
            create_table_query = """
            CREATE TABLE IF NOT EXISTS file_activity (
                id INT AUTO_INCREMENT PRIMARY KEY,
                timestamp DATETIME NOT NULL,
                event_type ENUM('CREATED', 'MODIFIED', 'DELETED', 'MOVED') NOT NULL,
                file_path VARCHAR(1000) NOT NULL,
                old_path VARCHAR(1000) NULL,
                new_path VARCHAR(1000) NULL,
                file_size BIGINT NULL,
                is_text_file BOOLEAN NULL,
                file_extension VARCHAR(50) NULL,
                sync_status ENUM('PENDING', 'SUCCESS', 'FAILED') DEFAULT 'PENDING',
                sync_timestamp DATETIME NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                INDEX idx_timestamp (timestamp),
                INDEX idx_event_type (event_type),
                INDEX idx_file_path (file_path(255)),
                INDEX idx_sync_status (sync_status)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            """
            
            cursor.execute(create_table_query)
            print("✅ Database tables created/verified")
            
        except Error as e:
            print(f"❌ Error creating tables: {e}")
    
    def log_activity(self, event_type, file_path, old_path=None, new_path=None, 
                    file_size=None, is_text_file=None, sync_status='PENDING'):
        """Log file activity to database."""
        try:
            cursor = self.connection.cursor()
            
            # Get file extension
            file_extension = Path(file_path).suffix if file_path else None
            
            # Prepare query
            query = """
            INSERT INTO file_activity 
            (timestamp, event_type, file_path, old_path, new_path, file_size, is_text_file, file_extension, sync_status)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """
            
            values = (
                datetime.now(),
                event_type,
                file_path,
                old_path,
                new_path,
                file_size,
                is_text_file,
                file_extension,
                sync_status
            )
            
            cursor.execute(query, values)
            print(f"📊 Logged: {event_type} - {file_path}")
            
        except Error as e:
            print(f"❌ Database logging failed: {e}")
    
    def update_sync_status(self, file_path, sync_status, event_type=None):
        """Update sync status for a file."""
        try:
            cursor = self.connection.cursor()
            
            if event_type:
                query = """
                UPDATE file_activity 
                SET sync_status = %s, sync_timestamp = %s
                WHERE file_path = %s AND event_type = %s
                ORDER BY timestamp DESC LIMIT 1
                """
                values = (sync_status, datetime.now(), file_path, event_type)
            else:
                query = """
                UPDATE file_activity 
                SET sync_status = %s, sync_timestamp = %s
                WHERE file_path = %s
                ORDER BY timestamp DESC LIMIT 1
                """
                values = (sync_status, datetime.now(), file_path)
            
            cursor.execute(query, values)
            
        except Error as e:
            print(f"❌ Database update failed: {e}")
    
    def start_worker(self):
        """Start background worker thread for database operations."""
        if not self.worker_thread or not self.worker_thread.is_alive():
            self.worker_thread = threading.Thread(target=self._worker_loop, daemon=True)
            self.worker_thread.start()
    
    def _worker_loop(self):
        """Background worker loop for processing database operations."""
        while True:
            try:
                operation = self.operation_queue.get(timeout=1)
                if operation is None:  # Shutdown signal
                    break
                
                op_type, args = operation
                
                if not self.connected:
                    print("⚠️  Database not connected, attempting to reconnect...")
                    if not self.connect():
                        print("❌ Reconnection failed, skipping operation")
                        continue
                
                if op_type == 'log':
                    self.log_activity(*args)
                elif op_type == 'update_sync':
                    self.update_sync_status(*args)
                
                self.operation_queue.task_done()
                
            except queue.Empty:
                continue
            except Exception as e:
                print(f"❌ Database worker error: {e}")
    
    def queue_operation(self, op_type, *args):
        """Queue a database operation for background processing."""
        if self.connected:
            self.operation_queue.put((op_type, args))
    
    def stop_worker(self):
        """Stop the background worker thread."""
        if self.worker_thread and self.worker_thread.is_alive():
            self.operation_queue.put(None)  # Shutdown signal
            self.worker_thread.join(timeout=5)
