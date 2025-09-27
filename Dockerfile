# Multi-stage build for smaller final image
FROM python:3.12-slim AS builder

# Install build dependencies and Python packages in a single layer
COPY requirements.txt .
RUN apt-get update && \
    apt-get install -y --no-install-recommends gcc python3-dev && \
    pip install --no-cache-dir --upgrade pip setuptools wheel && \
    pip install --no-cache-dir --user -r requirements.txt && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Final stage
FROM python:3.12-slim

# Set environment variables early for layer caching
ENV PYTHONPATH=/app \
    PYTHONUNBUFFERED=1 \
    PATH=/root/.local/bin:$PATH

# Install FFmpeg 8.0 from static builds
RUN apt-get update && \
    apt-get install -y --no-install-recommends wget xz-utils && \
    wget -q https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-linux64-gpl.tar.xz && \
    tar -xf ffmpeg-master-latest-linux64-gpl.tar.xz && \
    mv ffmpeg-master-latest-linux64-gpl/bin/ffmpeg /usr/local/bin/ && \
    mv ffmpeg-master-latest-linux64-gpl/bin/ffprobe /usr/local/bin/ && \
    rm -rf ffmpeg-master-latest-linux64-gpl* && \
    apt-get remove -y wget xz-utils && \
    apt-get autoremove -y && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/* && \
    mkdir -p /app/downloads /app/config

# Copy Python packages from builder stage
COPY --from=builder /root/.local /root/.local

# Set working directory
WORKDIR /app

# Copy entrypoint script first (less likely to change)
COPY docker-entrypoint.sh /usr/local/bin/
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

# Copy application code last (most likely to change)
COPY . .

# Expose port
EXPOSE 9832

# Set entrypoint and default command
ENTRYPOINT ["/usr/local/bin/docker-entrypoint.sh"]
CMD ["python", "main.py"]