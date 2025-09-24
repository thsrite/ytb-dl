#!/bin/sh
set -e

# Create directories if they don't exist
mkdir -p /app/downloads /app/config

# Set proper permissions
chmod 755 /app/downloads /app/config

# Note: Config file will be created automatically by the Python application
# This ensures consistency between the entrypoint script and Python default config
echo "Directories prepared. Config files will be created by the application if needed."

# Execute the command
exec "$@"