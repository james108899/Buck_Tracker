
# Use a lightweight Python base image
FROM python:3.12-slim


# Set working directory inside the container
WORKDIR /app
# Install required system dependencies for OpenCV
RUN apt-get update && apt-get install -y \
    libgl1 \
    libglib2.0-0 \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# Copy all project files to /app
COPY . .

# Install dependencies
# (If you have a requirements.txt file)
RUN pip install --no-cache-dir -r requirements.txt

# Expose port 8080 for Cloud Run
EXPOSE 8080

# Command to start the app using Gunicorn
CMD ["gunicorn", "-b", "0.0.0.0:8080", "run:app"]
