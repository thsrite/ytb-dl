# Use Python 3.11 Alpine for minimal size
FROM python:3.11-alpine

# Install system dependencies including ffmpeg
RUN apk add --no-cache \
    ffmpeg \
    gcc \
    musl-dev \
    libffi-dev \
    openssl-dev \
    && rm -rf /var/cache/apk/*

# Set working directory
WORKDIR /app

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Copy and make entrypoint script executable
COPY docker-entrypoint.sh /usr/local/bin/
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

# Create necessary directories
RUN mkdir -p downloads config

# Set environment variables
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

# Expose port
EXPOSE 9832

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD wget --no-verbose --tries=1 --spider http://localhost:9832/ || exit 1

# Set entrypoint and default command
ENTRYPOINT ["/usr/local/bin/docker-entrypoint.sh"]
CMD ["python", "main.py"]