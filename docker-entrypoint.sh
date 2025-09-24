#!/bin/sh
set -e

# Create directories if they don't exist
mkdir -p /app/downloads /app/config

# Set proper permissions
chmod 755 /app/downloads /app/config

# Check if config file exists, create default if not
if [ ! -f /app/config/config.json ]; then
    echo "Creating default config file..."
    cat > /app/config/config.json << 'EOF'
{
    "cookies_file": null,
    "proxy": null,
    "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "extra_params": {
        "nocheckcertificate": true,
        "geo_bypass": true,
        "age_limit": null,
        "sleep_interval": 1,
        "max_sleep_interval": 3,
        "retries": 3,
        "fragment_retries": 3,
        "skip_unavailable_fragments": true
    },
    "custom_params": [],
    "wecom": {
        "corp_id": "",
        "agent_id": null,
        "app_secret": "",
        "token": "",
        "encoding_aes_key": "",
        "public_base_url": "",
        "default_format_id": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
        "proxy_domain": ""
    }
}
EOF
fi

# Execute the command
exec "$@"