#!/usr/bin/env python3
"""
Unified File Service

A comprehensive Python service that combines:
- File monitoring and SFTP synchronization
- Database logging and file versioning
- Version management and restoration capabilities

Modes:
- MONITOR: Monitor files and sync to SFTP (CLIENT/HOST modes)
- VERSION: Manage file versions (list, restore, search)
"""

import os
import sys
import time
import argparse
import json
from pathlib import Path
from watchdog.observers import Observer

# Import from include directory
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
            ".git", "__pycache__", ".DS_Store", ".Trash", "Thumbs.db",
            "node_modules", ".cache", ".tmp", ".temp", "*.swp", "*.swo", "*~"
        ],
        "ignore_folders": [
            ".git", "__pycache__", "node_modules", ".cache", ".tmp", ".temp",
            "build", "dist", "target", "bin", "obj"
        ],
        "ignore_files": [
            ".DS_Store", "Thumbs.db", "desktop.ini", "*.swp", "*.swo",
            "*~", "*.log", "*.tmp", "*.temp"
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


def run_monitor_mode(args, config):
    """Run the file monitoring service."""
    # Initialize SFTP manager
    sftp_manager = None
    if not args.no_sync and SFTP_AVAILABLE:
        sftp_config = config.get('sftp_settings', {})
        
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
        db_config = config.get('database_settings', {})
        
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


def run_version_mode(args, config):
    """Run the version management commands."""
    # Load database settings
    db_config = config.get('database_settings', {})
    
    db_host = args.db_host or db_config.get('host', 'localhost')
    db_user = args.db_user or db_config.get('user')
    db_pass = args.db_pass or db_config.get('password')
    db_name = args.db_name or db_config.get('database', 'file_activity')
    db_port = args.db_port or db_config.get('port', 3306)
    
    if not db_user or not db_pass:
        print("❌ Database credentials required for version management")
        print("Use --db-user and --db-pass arguments or configure in config.json")
        sys.exit(1)
    
    # Connect to database
    db = DatabaseManager(
        host=db_host,
        user=db_user,
        password=db_pass,
        database=db_name,
        port=db_port
    )
    
    if not db.connect():
        print("❌ Failed to connect to database")
        sys.exit(1)
    
    try:
        if args.version_command == 'list':
            versions = db.get_file_versions(args.file_path, args.limit)
            if versions:
                print(f"\n📋 Versions for: {args.file_path}")
                print("-" * 80)
                print(f"{'ID':<6} {'Timestamp':<20} {'Size':<10} {'Checksum':<16}")
                print("-" * 80)
                for version in versions:
                    timestamp = version['version_timestamp'].strftime('%Y-%m-%d %H:%M:%S')
                    size_kb = f"{version['file_size'] / 1024:.1f} KB"
                    checksum_short = version['checksum'][:16] if version['checksum'] else 'N/A'
                    print(f"{version['id']:<6} {timestamp:<20} {size_kb:<10} {checksum_short:<16}")
            else:
                print(f"❌ No versions found for: {args.file_path}")
        
        elif args.version_command == 'restore':
            if db.restore_file_version(args.version_id, args.target):
                print("✅ File restored successfully")
            else:
                print("❌ Failed to restore file")
                sys.exit(1)
        
        elif args.version_command == 'search':
            print("🔍 Search functionality coming soon...")
            print(f"Searching for files matching: {args.pattern}")
    
    finally:
        db.disconnect()


def main():
    """Main function for the unified file service."""
    parser = argparse.ArgumentParser(
        description="Unified File Service - Monitor files and manage versions",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Monitor files (CLIENT mode)
  python file_service.py monitor /path/to/watch --recursive
  
  # Monitor files with SFTP sync
  python file_service.py monitor /path/to/watch --sftp-host example.com --sftp-user user --sftp-pass password
  
  # Monitor files with database logging (HOST mode)
  python file_service.py monitor /path/to/watch --mode HOST --db-user filemonitor --db-pass password
  
  # List file versions
  python file_service.py version list /path/to/file.txt --db-user filemonitor --db-pass password
  
  # Restore file version
  python file_service.py version restore 123 --db-user filemonitor --db-pass password
  
  # Create default config
  python file_service.py monitor /path/to/watch --create-config
        """
    )
    
    # Global arguments
    parser.add_argument(
        '--config',
        help='Path to configuration file'
    )
    
    parser.add_argument(
        '--create-config',
        action='store_true',
        help='Create a default configuration file and exit'
    )
    
    # Database arguments (shared between modes)
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
    
    # Subcommands
    subparsers = parser.add_subparsers(dest='mode', help='Service mode')
    
    # Monitor mode
    monitor_parser = subparsers.add_parser('monitor', help='Monitor files for changes')
    monitor_parser.add_argument(
        'path',
        help='Path to the directory to monitor'
    )
    
    monitor_parser.add_argument(
        '--ignore',
        help='Comma-separated list of patterns to ignore (in addition to defaults)',
        default=''
    )
    
    monitor_parser.add_argument(
        '--recursive',
        action='store_true',
        help='Monitor subdirectories recursively'
    )
    
    monitor_parser.add_argument(
        '--quiet',
        action='store_true',
        help='Suppress startup messages'
    )
    
    monitor_parser.add_argument(
        '--mode',
        choices=['CLIENT', 'HOST'],
        default='CLIENT',
        help='Operation mode: CLIENT (monitor+sync) or HOST (monitor+sync+database)'
    )
    
    # SFTP arguments for monitor mode
    monitor_parser.add_argument(
        '--sftp-host',
        help='SFTP server hostname'
    )
    
    monitor_parser.add_argument(
        '--sftp-user',
        help='SFTP username'
    )
    
    monitor_parser.add_argument(
        '--sftp-pass',
        help='SFTP password'
    )
    
    monitor_parser.add_argument(
        '--sftp-key',
        help='SFTP private key file path'
    )
    
    monitor_parser.add_argument(
        '--sftp-port',
        type=int,
        default=22,
        help='SFTP port (default: 22)'
    )
    
    monitor_parser.add_argument(
        '--sftp-path',
        default='/',
        help='Remote path to sync to (default: /)'
    )
    
    monitor_parser.add_argument(
        '--no-sync',
        action='store_true',
        help='Disable SFTP synchronization'
    )
    
    # Version mode
    version_parser = subparsers.add_parser('version', help='Manage file versions')
    version_subparsers = version_parser.add_subparsers(dest='version_command', help='Version commands')
    
    # List versions
    list_parser = version_subparsers.add_parser('list', help='List file versions')
    list_parser.add_argument('file_path', help='File path to list versions for')
    list_parser.add_argument('--limit', type=int, default=10, help='Number of versions to show')
    
    # Restore version
    restore_parser = version_subparsers.add_parser('restore', help='Restore file to specific version')
    restore_parser.add_argument('version_id', type=int, help='Version ID to restore')
    restore_parser.add_argument('--target', help='Target path (default: original path)')
    
    # Search versions
    search_parser = version_subparsers.add_parser('search', help='Search for files with versions')
    search_parser.add_argument('pattern', help='File path pattern to search')
    search_parser.add_argument('--limit', type=int, default=20, help='Number of results to show')
    
    args = parser.parse_args()
    
    # Handle config creation
    if args.create_config:
        config_file = args.config or 'config.json'
        if create_default_config(config_file):
            print(f"Default configuration created: {config_file}")
            print("Edit this file to customize ignore patterns, SFTP settings, and database settings.")
        sys.exit(0)
    
    # Load configuration
    config = {}
    if args.config and os.path.exists(args.config):
        try:
            with open(args.config, 'r') as f:
                config = json.load(f)
        except (json.JSONDecodeError, IOError):
            pass
    
    # Run appropriate mode
    if args.mode == 'monitor':
        # Validate the path
        if not os.path.exists(args.path):
            print(f"Error: Path '{args.path}' does not exist.", file=sys.stderr)
            sys.exit(1)
        
        if not os.path.isdir(args.path):
            print(f"Error: Path '{args.path}' is not a directory.", file=sys.stderr)
            sys.exit(1)
        
        run_monitor_mode(args, config)
    
    elif args.mode == 'version':
        if not args.version_command:
            version_parser.print_help()
            return
        
        run_version_mode(args, config)
    
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
