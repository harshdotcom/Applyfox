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

# bin/ is gitignored, so a fresh clone (what every cloud host builds from) has no
# LaTeX engine. Download the standalone Tectonic build for this CPU if it's missing.
ARG TECTONIC_VERSION=0.15.0
RUN if [ ! -x bin/tectonic ]; then \
      mkdir -p bin && \
      ARCH="$(uname -m)" && \
      curl -fsSL "https://github.com/tectonic-typesetting/tectonic/releases/download/tectonic%40${TECTONIC_VERSION}/tectonic-${TECTONIC_VERSION}-${ARCH}-unknown-linux-musl.tar.gz" \
        | tar -xz -C bin tectonic; \
    fi && chmod +x bin/tectonic && bin/tectonic --version

# Persistent data directory for applications tracker sheet & archives
VOLUME ["/app/data"]

# Cloud-compatible environment defaults
ENV PORT=8080
ENV HOST=0.0.0.0
ENV PYTHONUNBUFFERED=1

EXPOSE 8080

CMD ["python3", "cv_service.py", "serve"]

