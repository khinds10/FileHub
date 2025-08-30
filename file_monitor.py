#!/usr/bin/env python3
"""
File Monitor Service with SFTP Synchronization

A Python service that monitors a folder for file changes and outputs them to standard output.
Also synchronizes changes to a remote SFTP folder in real-time.
Ignores .git folders and other configurable patterns, but watches ALL files.
Text file detection is preserved for future use.

Modes:
- CLIENT: Monitor and sync files (no database logging)
- HOST: Monitor, sync, and log all activity to MySQL database
"""

import os
import sys
import time
import mimetypes
import argparse
import json
import threading
import queue
from pathlib import Path
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler, FileSystemEvent
from datetime import datetime

# Import classes from include directory
try:
    from include.database_manager import DatabaseManager, MYSQL_AVAILABLE
    from include.sftp_manager import SFTPManager, SFTP_AVAILABLE
    from include.file_change_handler import FileChangeHandler
except ImportError as e:
    print(f"Error importing classes from include directory: {e}")
    print("Make sure all files in the include/ directory are present.")
    sys.exit(1)


def create_default_config(config_file):
    """Create a default configuration file."""
    default_config = {
        "ignore_patterns": [
            ".git",
            "__pycache__",
            ".DS_Store",
            ".Trash",
            "Thumbs.db",
            "node_modules",
            ".cache",
            ".tmp",
            ".temp",
            "*.swp",
            "*.swo",
            "*~"
        ],
        "ignore_folders": [
            ".git",
            "__pycache__",
            "node_modules",
            ".cache",
            ".tmp",
            ".temp",
            "build",
            "dist",
            "target",
            "bin",
            "obj"
        ],
        "ignore_files": [
            ".DS_Store",
            "Thumbs.db",
            "desktop.ini",
            "*.swp",
            "*.swo",
            "*~",
            "*.log",
            "*.tmp",
            "*.temp"
        ],
        "monitor_settings": {
            "include_text_info": True,
            "max_file_size_mb": 100,
            "follow_symlinks": False
        },
        "sftp_settings": {
            "enabled": False,
            "host": "example.com",
            "username": "user",
            "password": "",
            "key_file": "",
            "port": 22,
            "remote_path": "/remote/sync/path"
        },
        "database_settings": {
            "enabled": False,
            "host": "localhost",
            "user": "filemonitor",
            "password": "",
            "database": "file_activity",
            "port": 3306
        }
    }
    
    try:
        with open(config_file, 'w') as f:
            json.dump(default_config, f, indent=2)
        print(f"Created default config file: {config_file}")
        return True
    except IOError as e:
        print(f"Error creating config file: {e}", file=sys.stderr)
        return False


def main():
    """Main function to run the file monitor service."""
    parser = argparse.ArgumentParser(
        description="Monitor a folder for file changes and sync to SFTP",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python file_monitor.py /path/to/watch
  python file_monitor.py /path/to/watch --ignore .tmp,.cache
  python file_monitor.py /path/to/watch --recursive
  python file_monitor.py /path/to/watch --config config.json
  python file_monitor.py /path/to/watch --create-config
  python file_monitor.py /path/to/watch --sftp-host example.com --sftp-user user --sftp-pass password
  python file_monitor.py /path/to/watch --mode HOST --db-host localhost --db-user filemonitor --db-pass password
        """
    )
    
    parser.add_argument(
        'path',
        help='Path to the directory to monitor'
    )
    
    parser.add_argument(
        '--ignore',
        help='Comma-separated list of patterns to ignore (in addition to defaults)',
        default=''
    )
    
    parser.add_argument(
        '--config',
        help='Path to configuration file with ignore patterns and SFTP settings'
    )
    
    parser.add_argument(
        '--create-config',
        action='store_true',
        help='Create a default configuration file and exit'
    )
    
    parser.add_argument(
        '--recursive',
        action='store_true',
        help='Monitor subdirectories recursively'
    )
    
    parser.add_argument(
        '--quiet',
        action='store_true',
        help='Suppress startup messages'
    )
    
    # Mode selection
    parser.add_argument(
        '--mode',
        choices=['CLIENT', 'HOST'],
        default='CLIENT',
        help='Operation mode: CLIENT (monitor+sync) or HOST (monitor+sync+database)'
    )
    
    # SFTP arguments
    parser.add_argument(
        '--sftp-host',
        help='SFTP server hostname'
    )
    
    parser.add_argument(
        '--sftp-user',
        help='SFTP username'
    )
    
    parser.add_argument(
        '--sftp-pass',
        help='SFTP password'
    )
    
    parser.add_argument(
        '--sftp-key',
        help='SFTP private key file path'
    )
    
    parser.add_argument(
        '--sftp-port',
        type=int,
        default=22,
        help='SFTP port (default: 22)'
    )
    
    parser.add_argument(
        '--sftp-path',
        default='/',
        help='Remote path to sync to (default: /)'
    )
    
    parser.add_argument(
        '--no-sync',
        action='store_true',
        help='Disable SFTP synchronization'
    )
    
    # Database arguments
    parser.add_argument(
        '--db-host',
        help='MySQL database hostname'
    )
    
    parser.add_argument(
        '--db-user',
        help='MySQL database username'
    )
    
    parser.add_argument(
        '--db-pass',
        help='MySQL database password'
    )
    
    parser.add_argument(
        '--db-name',
        help='MySQL database name'
    )
    
    parser.add_argument(
        '--db-port',
        type=int,
        default=3306,
        help='MySQL database port (default: 3306)'
    )
    
    args = parser.parse_args()
    
    # Handle config creation
    if args.create_config:
        config_file = args.config or 'config.json'
        if create_default_config(config_file):
            print(f"Default configuration created: {config_file}")
            print("Edit this file to customize ignore patterns, SFTP settings, and database settings.")
        sys.exit(0)
    
    # Validate the path
    if not os.path.exists(args.path):
        print(f"Error: Path '{args.path}' does not exist.", file=sys.stderr)
        sys.exit(1)
    
    if not os.path.isdir(args.path):
        print(f"Error: Path '{args.path}' is not a directory.", file=sys.stderr)
        sys.exit(1)
    
    # Load configuration
    config = {}
    if args.config and os.path.exists(args.config):
        try:
            with open(args.config, 'r') as f:
                config = json.load(f)
        except (json.JSONDecodeError, IOError):
            pass
    
    # Initialize SFTP manager
    sftp_manager = None
    if not args.no_sync and SFTP_AVAILABLE:
        # Load SFTP settings from config file
        sftp_config = config.get('sftp_settings', {})
        
        # Command line arguments override config file
        sftp_host = args.sftp_host or sftp_config.get('host')
        sftp_user = args.sftp_user or sftp_config.get('username')
        sftp_pass = args.sftp_pass or sftp_config.get('password')
        sftp_key = args.sftp_key or sftp_config.get('key_file')
        sftp_port = args.sftp_port or sftp_config.get('port', 22)
        sftp_path = args.sftp_path or sftp_config.get('remote_path', '/')
        
        if sftp_host and sftp_user and (sftp_pass or sftp_key):
            sftp_manager = SFTPManager(
                host=sftp_host,
                username=sftp_user,
                password=sftp_pass,
                key_file=sftp_key,
                port=sftp_port,
                remote_path=sftp_path
            )
            
            if sftp_manager.connect():
                sftp_manager.start_worker()
            else:
                print("Warning: SFTP connection failed, continuing without sync")
                sftp_manager = None
        else:
            print("Info: SFTP not configured, running without sync")
    
    # Initialize database manager (HOST mode only)
    db_manager = None
    if args.mode == 'HOST' and MYSQL_AVAILABLE:
        # Load database settings from config file
        db_config = config.get('database_settings', {})
        
        # Command line arguments override config file
        db_host = args.db_host or db_config.get('host', 'localhost')
        db_user = args.db_user or db_config.get('user')
        db_pass = args.db_pass or db_config.get('password')
        db_name = args.db_name or db_config.get('database', 'file_activity')
        db_port = args.db_port or db_config.get('port', 3306)
        
        if db_host and db_user and db_pass:
            db_manager = DatabaseManager(
                host=db_host,
                user=db_user,
                password=db_pass,
                database=db_name,
                port=db_port
            )
            
            if db_manager.connect():
                db_manager.start_worker()
            else:
                print("Warning: Database connection failed, continuing without logging")
                db_manager = None
        else:
            print("Warning: Database not configured for HOST mode")
    
    # Create event handler and observer
    event_handler = FileChangeHandler(
        ignore_patterns=args.ignore if args.ignore else None,
        ignore_config_file=args.config,
        sftp_manager=sftp_manager,
        db_manager=db_manager,
        local_base_path=os.path.abspath(args.path),
        mode=args.mode
    )
    observer = Observer()
    
    # Schedule the observer
    observer.schedule(
        event_handler,
        args.path,
        recursive=args.recursive
    )
    
    if not args.quiet:
        print(f"Starting file monitor for: {os.path.abspath(args.path)}")
        print(f"Mode: {args.mode}")
        print(f"Ignoring patterns: {event_handler.ignore_patterns}")
        print(f"Recursive monitoring: {args.recursive}")
        print("Monitoring ALL files (text detection preserved for future use)")
        
        if sftp_manager and sftp_manager.connected:
            print(f"✅ SFTP sync enabled: {sftp_manager.username}@{sftp_manager.host}:{sftp_manager.remote_path}")
        else:
            print("❌ SFTP sync disabled")
        
        if db_manager and db_manager.connected:
            print(f"✅ Database logging enabled: {db_manager.user}@{db_manager.host}:{db_manager.port}/{db_manager.database}")
        else:
            print("❌ Database logging disabled")
        
        print("Press Ctrl+C to stop monitoring...")
        print("-" * 50)
    
    try:
        observer.start()
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        if not args.quiet:
            print("\nStopping file monitor...")
        
        observer.stop()
        
        if sftp_manager:
            sftp_manager.stop_worker()
            sftp_manager.disconnect()
        
        if db_manager:
            db_manager.stop_worker()
            db_manager.disconnect()
    
    observer.join()


if __name__ == "__main__":
    main()
