#!/usr/bin/env python3
"""
File Change Handler for File Monitor Service

Handles file system events with SFTP synchronization and database logging.
"""

import os
import sys
import time
import mimetypes
import json
from pathlib import Path
from watchdog.events import FileSystemEventHandler, FileSystemEvent
from datetime import datetime


class FileChangeHandler(FileSystemEventHandler):
    """Handler for file system events with SFTP synchronization and database logging."""
    
    def __init__(self, ignore_patterns=None, ignore_config_file=None, sftp_manager=None, 
                 db_manager=None, local_base_path=None, mode='CLIENT'):
        super().__init__()
        
        # Load ignore patterns from config file if provided
        self.ignore_patterns = self.load_ignore_patterns(ignore_patterns, ignore_config_file)
        
        # Managers
        self.sftp_manager = sftp_manager
        self.db_manager = db_manager
        self.local_base_path = local_base_path
        self.mode = mode.upper()
        
        # Text file detection for future use
        self.text_extensions = {
            '.txt', '.py', '.js', '.html', '.css', '.json', '.xml', '.yaml', '.yml',
            '.md', '.rst', '.ini', '.cfg', '.conf', '.log', '.csv', '.tsv', '.sql',
            '.sh', '.bash', '.zsh', '.fish', '.bat', '.cmd', '.ps1', '.r', '.java',
            '.cpp', '.c', '.h', '.hpp', '.cs', '.php', '.rb', '.go', '.rs', '.swift',
            '.kt', '.scala', '.clj', '.hs', '.ml', '.fs', '.vb', '.pl', '.pm', '.tcl',
            '.lua', '.scm', '.el', '.vim', '.tex', '.bib', '.sty', '.cls', '.dtx',
            '.ltx', '.aux', '.bbl', '.blg', '.fdb_latexmk', '.fls', '.out', '.synctex.gz'
        }
    
    def load_ignore_patterns(self, ignore_patterns, config_file):
        """Load ignore patterns from command line and/or config file."""
        patterns = []
        
        # Add default patterns
        default_patterns = ['.git', '__pycache__', '.DS_Store', '.Trash', 'Thumbs.db']
        patterns.extend(default_patterns)
        
        # Add command line patterns
        if ignore_patterns:
            patterns.extend([pattern.strip() for pattern in ignore_patterns.split(',')])
        
        # Load from config file
        if config_file and os.path.exists(config_file):
            try:
                with open(config_file, 'r') as f:
                    config = json.load(f)
                    if 'ignore_patterns' in config:
                        patterns.extend(config['ignore_patterns'])
                    if 'ignore_folders' in config:
                        patterns.extend(config['ignore_folders'])
                    if 'ignore_files' in config:
                        patterns.extend(config['ignore_files'])
            except (json.JSONDecodeError, IOError) as e:
                print(f"Warning: Could not load config file {config_file}: {e}", file=sys.stderr)
        
        # Remove duplicates and empty patterns
        return list(set([p for p in patterns if p]))
    
    def is_text_file(self, file_path):
        """Check if a file is text-based (preserved for future use)."""
        if not os.path.isfile(file_path):
            return False
        
        # Check file extension first
        file_ext = Path(file_path).suffix.lower()
        if file_ext in self.text_extensions:
            return True
        
        # Check MIME type
        mime_type, _ = mimetypes.guess_type(file_path)
        if mime_type and mime_type.startswith('text/'):
            return True
        
        # Fallback: try to read first few bytes to detect text
        try:
            with open(file_path, 'rb') as f:
                chunk = f.read(1024)
                # Check if the chunk contains mostly printable characters
                text_chars = sum(1 for byte in chunk if 32 <= byte <= 126 or byte in (9, 10, 13))
                return text_chars / len(chunk) > 0.7 if chunk else False
        except (IOError, OSError):
            return False
    
    def should_ignore(self, path):
        """Check if a path should be ignored."""
        path_str = str(path)
        path_parts = Path(path).parts
        
        for pattern in self.ignore_patterns:
            # Check if pattern is in path
            if pattern in path_str:
                return True
            
            # Check if pattern matches any path component
            if pattern in path_parts:
                return True
            
            # Check for exact filename/directory match
            if os.path.basename(path) == pattern:
                return True
        
        return False
    
    def get_relative_path(self, file_path):
        """Get relative path from base directory."""
        if self.local_base_path:
            try:
                return os.path.relpath(file_path, self.local_base_path)
            except ValueError:
                return file_path
        return file_path
    
    def get_file_size(self, file_path):
        """Get file size in bytes."""
        try:
            if os.path.isfile(file_path):
                return os.path.getsize(file_path)
        except (OSError, IOError):
            pass
        return None
    
    def format_event(self, event_type, file_path, is_text=None):
        """Format the event for output."""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # Include text file info if available
        if is_text is not None:
            text_info = " [TEXT]" if is_text else " [BINARY]"
            return f"[{timestamp}] {event_type}: {file_path}{text_info}"
        else:
            return f"[{timestamp}] {event_type}: {file_path}"
    
    def log_to_database(self, event_type, file_path, old_path=None, new_path=None, is_text=None):
        """Log event to database if in HOST mode."""
        if self.mode == 'HOST' and self.db_manager and self.db_manager.connected:
            file_size = self.get_file_size(file_path) if file_path else None
            self.db_manager.queue_operation('log', event_type, file_path, old_path, new_path, 
                                          file_size, is_text, 'PENDING')
            
            # Save file version for text files on creation or modification
            if is_text and event_type in ['CREATED', 'MODIFIED'] and file_path:
                self.db_manager.queue_operation('save_version', file_path)
    
    def on_created(self, event):
        """Handle file creation events."""
        if not event.is_directory and not self.should_ignore(event.src_path):
            # Check if it's a text file for future use
            is_text = self.is_text_file(event.src_path)
            print(self.format_event("CREATED", event.src_path, is_text))
            
            # Log to database (HOST mode)
            self.log_to_database("CREATED", event.src_path, is_text=is_text)
            
            # Sync to SFTP
            if self.sftp_manager and self.sftp_manager.connected:
                relative_path = self.get_relative_path(event.src_path)
                self.sftp_manager.queue_operation('upload', event.src_path, relative_path)
    
    def on_modified(self, event):
        """Handle file modification events."""
        if not event.is_directory and not self.should_ignore(event.src_path):
            # Check if it's a text file for future use
            is_text = self.is_text_file(event.src_path)
            print(self.format_event("MODIFIED", event.src_path, is_text))
            
            # Log to database (HOST mode)
            self.log_to_database("MODIFIED", event.src_path, is_text=is_text)
            
            # Sync to SFTP
            if self.sftp_manager and self.sftp_manager.connected:
                relative_path = self.get_relative_path(event.src_path)
                self.sftp_manager.queue_operation('upload', event.src_path, relative_path)
    
    def on_deleted(self, event):
        """Handle file deletion events."""
        if not event.is_directory and not self.should_ignore(event.src_path):
            # For deleted files, we can't check if they were text files
            print(self.format_event("DELETED", event.src_path))
            
            # Log to database (HOST mode)
            self.log_to_database("DELETED", event.src_path)
            
            # Sync to SFTP
            if self.sftp_manager and self.sftp_manager.connected:
                relative_path = self.get_relative_path(event.src_path)
                self.sftp_manager.queue_operation('delete', relative_path)
    
    def on_moved(self, event):
        """Handle file move/rename events."""
        if not event.is_directory:
            src_path = event.src_path
            dest_path = event.dest_path
            
            if not self.should_ignore(src_path) and not self.should_ignore(dest_path):
                # Check if destination is a text file for future use
                is_text = self.is_text_file(dest_path) if os.path.exists(dest_path) else None
                print(self.format_event("MOVED", f"{src_path} -> {dest_path}", is_text))
                
                # Log to database (HOST mode)
                self.log_to_database("MOVED", dest_path, old_path=src_path, new_path=dest_path, is_text=is_text)
                
                # Sync to SFTP
                if self.sftp_manager and self.sftp_manager.connected:
                    old_relative_path = self.get_relative_path(src_path)
                    new_relative_path = self.get_relative_path(dest_path)
                    self.sftp_manager.queue_operation('move', old_relative_path, new_relative_path)
