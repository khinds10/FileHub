-- File Monitor Service Database Setup
-- Run this script as MySQL root user to set up the database

-- Create database
CREATE DATABASE IF NOT EXISTS file_activity 
CHARACTER SET utf8mb4 
COLLATE utf8mb4_unicode_ci;

-- Create user for file monitor service
CREATE USER IF NOT EXISTS 'filemonitor'@'localhost' IDENTIFIED BY 'your_secure_password_here';

-- Grant permissions to the user
GRANT ALL PRIVILEGES ON file_activity.* TO 'filemonitor'@'localhost';

-- Grant permissions for remote connections (if needed)
-- GRANT ALL PRIVILEGES ON file_activity.* TO 'filemonitor'@'%';

-- Flush privileges to apply changes
FLUSH PRIVILEGES;

-- Use the database
USE file_activity;

-- Create the file activity table
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
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Show the created table structure
DESCRIBE file_activity;

-- Show some useful queries for monitoring
SELECT 'Useful queries for monitoring file activity:' AS info;
SELECT 'SELECT COUNT(*) FROM file_activity WHERE DATE(timestamp) = CURDATE();' AS daily_count;
SELECT 'SELECT event_type, COUNT(*) FROM file_activity GROUP BY event_type;' AS event_summary;
SELECT 'SELECT * FROM file_activity ORDER BY timestamp DESC LIMIT 10;' AS recent_activity;
