# Multi-stage build for smaller final image
FROM python:3.12-alpine AS builder

# Install build dependencies
RUN apk add --no-cache gcc musl-dev libffi-dev openssl-dev

# Install Python dependencies
COPY requirements.txt .
RUN pip install --upgrade pip setuptools wheel \
    && pip install --no-cache-dir --user -r requirements.txt

# Final stage
FROM python:3.12-alpine

# Install only runtime dependencies
RUN apk add --no-cache ffmpeg ca-certificates wget \
    && rm -rf /var/cache/apk/* \
    && update-ca-certificates

# Copy Python packages from builder stage
COPY --from=builder /root/.local /root/.local

# Make sure scripts in .local are usable
ENV PATH=/root/.local/bin:$PATH

# Set working directory and copy app
WORKDIR /app
COPY . .

# Setup entrypoint and create directories in single layer
RUN chmod +x docker-entrypoint.sh \
    && mkdir -p downloads config \
    && mv docker-entrypoint.sh /usr/local/bin/

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