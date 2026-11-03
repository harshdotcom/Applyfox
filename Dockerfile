# Applyfox - High-Performance ATS CV Studio & Career Portals Engine
FROM python:3.11-slim-bookworm

# Install required system dependencies for Tectonic LaTeX XeTeX compilation & SSL
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    curl \
    libssl3 \
    libgraphite2-3 \
    libstdc++6 \
    libzstd1 \
    fontconfig \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY . .

# Ensure standalone Tectonic binary is executable
RUN chmod +x bin/tectonic

# Persistent data directory for applications tracker sheet & archives
VOLUME ["/app/data"]

# Cloud-compatible environment defaults
ENV PORT=8080
ENV HOST=0.0.0.0
ENV PYTHONUNBUFFERED=1

EXPOSE 8080

CMD ["python3", "cv_service.py", "serve"]
