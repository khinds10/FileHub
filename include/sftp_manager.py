#!/usr/bin/env python3
"""
SFTP Manager for File Monitor Service

Manages SFTP connection and operations for file synchronization.
"""

import os
import sys
import json
import threading
import queue
from pathlib import Path

# SFTP imports
try:
    import paramiko
    from paramiko import SSHClient, AutoAddPolicy
    SFTP_AVAILABLE = True
except ImportError:
    SFTP_AVAILABLE = False
    print("Warning: paramiko not installed. SFTP sync will be disabled.")
    print("Install with: sudo apt install python3-paramiko")


class SFTPManager:
    """Manages SFTP connection and operations."""
    
    def __init__(self, host, username, password=None, key_file=None, port=22, remote_path="/"):
        self.host = host
        self.username = username
        self.password = password
        self.key_file = key_file
        self.port = port
        self.remote_path = remote_path.rstrip('/')
        self.client = None
        self.sftp = None
        self.connected = False
        self.operation_queue = queue.Queue()
        self.worker_thread = None
        
    def connect(self):
        """Establish SFTP connection."""
        try:
            self.client = SSHClient()
            self.client.set_missing_host_key_policy(AutoAddPolicy())
            
            if self.key_file:
                self.client.connect(
                    self.host, 
                    port=self.port,
                    username=self.username,
                    key_filename=self.key_file
                )
            else:
                self.client.connect(
                    self.host, 
                    port=self.port,
                    username=self.username,
                    password=self.password
                )
            
            self.sftp = self.client.open_sftp()
            self.connected = True
            print(f"✅ Connected to SFTP server: {self.username}@{self.host}:{self.port}")
            return True
            
        except Exception as e:
            print(f"❌ SFTP connection failed: {e}")
            self.connected = False
            return False
    
    def disconnect(self):
        """Close SFTP connection."""
        if self.sftp:
            self.sftp.close()
        if self.client:
            self.client.close()
        self.connected = False
        print("🔌 SFTP connection closed")
    
    def ensure_remote_path(self, remote_file_path):
        """Ensure remote directory exists."""
        try:
            remote_dir = os.path.dirname(remote_file_path)
            if remote_dir:
                self.sftp.makedirs(remote_dir, exist_ok=True)
        except Exception as e:
            print(f"Warning: Could not create remote directory {remote_dir}: {e}")
    
    def upload_file(self, local_path, remote_path):
        """Upload a file to remote location."""
        try:
            full_remote_path = f"{self.remote_path}/{remote_path.lstrip('/')}"
            self.ensure_remote_path(full_remote_path)
            self.sftp.put(local_path, full_remote_path)
            print(f"📤 Uploaded: {local_path} -> {full_remote_path}")
            return True
        except Exception as e:
            print(f"❌ Upload failed for {local_path}: {e}")
            return False
    
    def delete_file(self, remote_path):
        """Delete a file from remote location."""
        try:
            full_remote_path = f"{self.remote_path}/{remote_path.lstrip('/')}"
            self.sftp.remove(full_remote_path)
            print(f"🗑️  Deleted remote: {full_remote_path}")
            return True
        except Exception as e:
            print(f"❌ Delete failed for {remote_path}: {e}")
            return False
    
    def move_file(self, old_remote_path, new_remote_path):
        """Move/rename a file on remote location."""
        try:
            old_full_path = f"{self.remote_path}/{old_remote_path.lstrip('/')}"
            new_full_path = f"{self.remote_path}/{new_remote_path.lstrip('/')}"
            
            # Ensure new directory exists
            self.ensure_remote_path(new_full_path)
            
            # Move the file
            self.sftp.rename(old_full_path, new_full_path)
            print(f"🔄 Moved remote: {old_full_path} -> {new_full_path}")
            return True
        except Exception as e:
            print(f"❌ Move failed: {old_remote_path} -> {new_remote_path}: {e}")
            return False
    
    def start_worker(self):
        """Start background worker thread for SFTP operations."""
        if not self.worker_thread or not self.worker_thread.is_alive():
            self.worker_thread = threading.Thread(target=self._worker_loop, daemon=True)
            self.worker_thread.start()
    
    def _worker_loop(self):
        """Background worker loop for processing SFTP operations."""
        while True:
            try:
                operation = self.operation_queue.get(timeout=1)
                if operation is None:  # Shutdown signal
                    break
                
                op_type, args = operation
                
                if not self.connected:
                    print("⚠️  SFTP not connected, attempting to reconnect...")
                    if not self.connect():
                        print("❌ Reconnection failed, skipping operation")
                        continue
                
                if op_type == 'upload':
                    self.upload_file(*args)
                elif op_type == 'delete':
                    self.delete_file(*args)
                elif op_type == 'move':
                    self.move_file(*args)
                
                self.operation_queue.task_done()
                
            except queue.Empty:
                continue
            except Exception as e:
                print(f"❌ SFTP worker error: {e}")
    
    def queue_operation(self, op_type, *args):
        """Queue an SFTP operation for background processing."""
        if self.connected:
            self.operation_queue.put((op_type, args))
    
    def stop_worker(self):
        """Stop the background worker thread."""
        if self.worker_thread and self.worker_thread.is_alive():
            self.operation_queue.put(None)  # Shutdown signal
            self.worker_thread.join(timeout=5)
