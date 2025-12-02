# ----------------------------
# Stage 1: Build stage
# ----------------------------
FROM python:3.12-slim AS builder

WORKDIR /app

# Install build dependencies (only in builder)
RUN apt-get update && apt-get install -y \
    build-essential \
    libgl1 \
    libglib2.0-0 \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# Copy project files and install Python dependencies
COPY requirements.txt .
RUN pip install --prefix=/install --no-cache-dir -r requirements.txt

COPY . .

# ----------------------------
# Stage 2: Final runtime stage
# ----------------------------
FROM python:3.12-slim

WORKDIR /app

# Install only runtime dependencies
RUN apt-get update && apt-get install -y \
    libgl1 \
    libglib2.0-0 \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# Copy installed Python packages from builder
COPY --from=builder /install /usr/local

# Copy only app code
COPY --from=builder /app /app

EXPOSE 8080

CMD ["gunicorn", "-b", "0.0.0.0:8080", "run:app"]
