# File Monitor Service with SFTP Synchronization

A Python service that monitors a folder for file changes and outputs them to standard output. The service automatically ignores `.git` folders and other configurable patterns, but watches ALL files. **Real-time SFTP synchronization** ensures all local changes are immediately mirrored to a remote server.

## Operation Modes

- **CLIENT Mode**: Monitor files and sync to SFTP (no database logging)
- **HOST Mode**: Monitor files, sync to SFTP, and log all activity to MySQL database

## Project Structure

```
File-Service/
├── file_monitor.py      # Main monitoring and sync service
├── include/             # Modular class components
│   ├── database_manager.py    # MySQL database operations
│   ├── sftp_manager.py        # SFTP connection and sync
│   └── file_change_handler.py # File system event handling
├── config.json          # Configuration file (ignore patterns + SFTP + database settings)
├── setup_database.sql   # MySQL database setup script
├── requirements.txt     # Python dependencies
├── file-monitor.service # Systemd service template
└── README.md           # This documentation
```

## Features

- **Real-time monitoring**: Uses the `watchdog` library for efficient file system monitoring
- **All file monitoring**: Watches ALL files, not just text files
- **Real-time SFTP sync**: Automatically mirrors changes to remote server
- **Database logging**: HOST mode logs all activity to MySQL database
- **Text file detection**: Preserved for future use and shown in output
- **Smart filtering**: Ignores common patterns like `.git`, `__pycache__`, `.DS_Store`
- **Flexible configuration**: Customizable ignore patterns, SFTP, and database settings
- **Background processing**: Non-blocking operations with automatic reconnection
- **Clean output**: Timestamped events with clear formatting

## Installation

1. **Install Python dependencies:**
   ```bash
   sudo apt update
   sudo apt install python3-watchdog python3-paramiko python3-mysql.connector
   ```

2. **Make the script executable (optional):**
   ```bash
   chmod +x file_monitor.py
   ```

## Usage

### Basic Usage

Monitor a single directory:
```bash
python file_monitor.py /path/to/watch
```

### Advanced Options

**Monitor recursively (including subdirectories):**
```bash
python file_monitor.py /path/to/watch --recursive
```

**Custom ignore patterns:**
```bash
python file_monitor.py /path/to/watch --ignore .tmp,.cache,node_modules
```

**Use configuration file:**
```bash
python file_monitor.py /path/to/watch --config config.json
```

**Create default configuration:**
```bash
python file_monitor.py /path/to/watch --create-config
```

**CLIENT mode (monitor + sync):**
```bash
python file_monitor.py /path/to/watch --sftp-host example.com --sftp-user user --sftp-pass password
```

**HOST mode (monitor + sync + database):**
```bash
python file_monitor.py /path/to/watch --mode HOST --sftp-host example.com --sftp-user user --sftp-pass password --db-host localhost --db-user filemonitor --db-pass password
```

**Quiet mode (suppress startup messages):**
```bash
python file_monitor.py /path/to/watch --quiet
```

**Combine options:**
```bash
python file_monitor.py /path/to/watch --recursive --ignore .tmp,.cache --quiet
```

## Output Format

The service outputs events in the following format:
```
[2024-01-15 14:30:25] CREATED: /path/to/watch/new_file.txt [TEXT]
📤 Uploaded: /path/to/watch/new_file.txt -> /remote/path/new_file.txt
[2024-01-15 14:30:30] MODIFIED: /path/to/watch/existing_file.py [TEXT]
📤 Uploaded: /path/to/watch/existing_file.py -> /remote/path/existing_file.py
[2024-01-15 14:30:35] DELETED: /path/to/watch/old_file.md
🗑️  Deleted remote: /remote/path/old_file.md
[2024-01-15 14:30:40] MOVED: /path/to/watch/old_name.txt -> /path/to/watch/new_name.txt [TEXT]
🔄 Moved remote: /remote/path/old_name.txt -> /remote/path/new_name.txt
[2024-01-15 14:30:45] CREATED: /path/to/watch/image.jpg [BINARY]
📤 Uploaded: /path/to/watch/image.jpg -> /remote/path/image.jpg
```

## File Monitoring

The service now monitors **ALL files** (not just text files) while preserving text file detection for future use.

### Text File Detection (Preserved for Future Use)

The service uses multiple methods to detect text files:

1. **File extension matching**: Recognizes common text file extensions
2. **MIME type detection**: Uses system MIME type detection
3. **Content analysis**: Analyzes file content for printable characters

Text file information is shown in the output as `[TEXT]` or `[BINARY]` tags.

## SFTP Synchronization

The service provides real-time synchronization to a remote SFTP server. All local file changes are automatically mirrored to the remote location.

### Features

- **Real-time sync**: Changes are uploaded immediately when detected
- **Background processing**: SFTP operations don't block file monitoring
- **Automatic reconnection**: Handles connection drops gracefully
- **Directory structure preservation**: Maintains folder hierarchy on remote server
- **Support for both authentication methods**: Password and SSH key authentication

### Setup

1. **Run with SFTP sync:**
   ```bash
   python3 file_monitor.py /local/path --sftp-host your-server.com --sftp-user username --sftp-pass password --sftp-path /remote/path
   ```

2. **Using SSH key authentication:**
   ```bash
   python3 file_monitor.py /local/path --sftp-host your-server.com --sftp-user username --sftp-key ~/.ssh/id_rsa --sftp-path /remote/path
   ```

3. **Using configuration file:**
   ```bash
   # Edit config.json with your SFTP settings, then:
   python3 file_monitor.py /local/path --config config.json
   ```

### Supported Operations

- **File Creation**: New files are uploaded to remote server
- **File Modification**: Updated files are re-uploaded
- **File Deletion**: Files are removed from remote server
- **File Renaming/Moving**: Files are moved/renamed on remote server

### Security Notes

- Passwords are passed via command line (consider using SSH keys for production)
- SSH keys should have appropriate permissions (600)
- The service automatically accepts unknown host keys (use with caution in production)

## Database Setup (HOST Mode)

The HOST mode requires a MySQL database to log all file activity. Follow these steps to set up the database:

### 1. Install MySQL (if not already installed)
```bash
sudo apt install mysql-server
sudo mysql_secure_installation
```

### 2. Set up the database
```bash
# Run the setup script as MySQL root
sudo mysql < setup_database.sql
```

### 3. Update configuration
Edit `config.json` and set the database settings:
```json
"database_settings": {
    "enabled": true,
    "host": "localhost",
    "user": "filemonitor",
    "password": "your_secure_password_here",
    "database": "file_activity",
    "port": 3306
}
```

### 4. Database Schema

The service creates a `file_activity` table with the following structure:

| Column | Type | Description |
|--------|------|-------------|
| `id` | INT | Auto-increment primary key |
| `timestamp` | DATETIME | When the event occurred |
| `event_type` | ENUM | CREATED, MODIFIED, DELETED, MOVED |
| `file_path` | VARCHAR(1000) | Full path to the file |
| `old_path` | VARCHAR(1000) | Previous path (for MOVED events) |
| `new_path` | VARCHAR(1000) | New path (for MOVED events) |
| `file_size` | BIGINT | File size in bytes |
| `is_text_file` | BOOLEAN | Whether file is text-based |
| `file_extension` | VARCHAR(50) | File extension |
| `sync_status` | ENUM | PENDING, SUCCESS, FAILED |
| `sync_timestamp` | DATETIME | When sync completed |

### 5. Useful Database Queries

```sql
-- Daily activity count
SELECT COUNT(*) FROM file_activity WHERE DATE(timestamp) = CURDATE();

-- Event type summary
SELECT event_type, COUNT(*) FROM file_activity GROUP BY event_type;

-- Recent activity
SELECT * FROM file_activity ORDER BY timestamp DESC LIMIT 10;

-- Failed syncs
SELECT * FROM file_activity WHERE sync_status = 'FAILED';

-- Large files
SELECT * FROM file_activity WHERE file_size > 1048576 ORDER BY file_size DESC;
```

## Configuration

The service supports flexible configuration through command-line options and JSON configuration files.

### Configuration File Format

```json
{
  "ignore_patterns": [".git", "__pycache__", "node_modules"],
  "ignore_folders": [".git", "build", "dist"],
  "ignore_files": [".DS_Store", "*.tmp", "*.log"],
  "monitor_settings": {
    "include_text_info": true,
    "max_file_size_mb": 100,
    "follow_symlinks": false
  },
  "sftp_settings": {
    "enabled": true,
    "host": "your-sftp-server.com",
    "username": "your-username",
    "password": "your-password",
    "key_file": "",
    "port": 22,
    "remote_path": "/remote/sync/path"
  },
  "database_settings": {
    "enabled": true,
    "host": "localhost",
    "user": "filemonitor",
    "password": "your-database-password",
    "database": "file_activity",
    "port": 3306
  }
}
```

### Supported Text File Types (For Detection)

The service recognizes a wide range of text file types including:
- Programming languages: `.py`, `.js`, `.java`, `.cpp`, `.c`, `.php`, `.rb`, `.go`, etc.
- Web files: `.html`, `.css`, `.xml`, `.json`, `.yaml`, `.yml`
- Documentation: `.md`, `.rst`, `.txt`
- Configuration: `.ini`, `.cfg`, `.conf`, `.json`
- Scripts: `.sh`, `.bash`, `.bat`, `.ps1`
- Data files: `.csv`, `.tsv`, `.sql`
- And many more...

## Running as a Service

To run this as a background service on Ubuntu:

1. **Create a systemd service file:**
   ```bash
   sudo nano /etc/systemd/system/file-monitor.service
   ```

2. **Add the following content:**
   ```ini
   [Unit]
   Description=File Monitor Service
   After=network.target

   [Service]
   Type=simple
   User=your_username
   WorkingDirectory=/path/to/script/directory
   ExecStart=/usr/bin/python3 /path/to/script/file_monitor.py /path/to/watch --recursive
   Restart=always
   RestartSec=10

   [Install]
   WantedBy=multi-user.target
   ```

3. **Enable and start the service:**
   ```bash
   sudo systemctl daemon-reload
   sudo systemctl enable file-monitor
   sudo systemctl start file-monitor
   ```

4. **Check service status:**
   ```bash
   sudo systemctl status file-monitor
   sudo journalctl -u file-monitor -f
   ```

## Stopping the Service

- **Interactive mode**: Press `Ctrl+C`
- **Systemd service**: `sudo systemctl stop file-monitor`

## Troubleshooting

- **Permission denied**: Ensure you have read permissions for the monitored directory
- **No events detected**: Check that the directory contains text files and isn't being ignored
- **High CPU usage**: Consider using `--quiet` mode or reducing the monitored directory size

## License

This project is open source and available under the MIT License.
