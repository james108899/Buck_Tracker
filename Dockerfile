# ----------------------------
# Stage 1: Builder
# ----------------------------
FROM python:3.12-slim AS builder

WORKDIR /app

# Install only what is needed for building wheels
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    gcc \
    libgl1 \
    && rm -rf /var/lib/apt/lists/*

# Copy dependencies file
COPY requirements.txt .

# Install dependencies into a temporary folder
RUN pip install --upgrade pip && \
    pip install --prefix=/install --no-cache-dir -r requirements.txt

# Copy source
COPY . .

# ----------------------------
# Stage 2: Runtime (minimal size)
# ----------------------------
FROM python:3.12-slim

WORKDIR /app

# Install minimal runtime libraries only
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# Copy only installed python deps
COPY --from=builder /install /usr/local

# Copy only application code (not build deps)
COPY --from=builder /app /app

# Reduce Python overhead
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

EXPOSE 8080

# Use multiple workers in a lightweight way
CMD ["uvicorn", "run:app", "--host", "0.0.0.0", "--port", "8080", ]
