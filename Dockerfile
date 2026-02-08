# Use an official Python runtime as a parent image
FROM python:3.10-slim

# 1. Install dependencies
# We install 'gnupg' instead of 'gnupg2' and common tools
RUN apt-get update && apt-get install -y \
    wget \
    gnupg \
    unzip \
    curl \
    --no-install-recommends \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# 2. Install Google Chrome (Stable)
# We download the .deb file directly to avoid GPG key errors
RUN wget -q https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb \
    && apt-get update \
    && apt-get install -y ./google-chrome-stable_current_amd64.deb \
    && rm google-chrome-stable_current_amd64.deb \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# 3. Set working directory
WORKDIR /app

# 4. Copy requirements and install
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 5. Copy the rest of the application
COPY . .

# 6. Run the app
# Increased timeout to 120s to prevent boot errors
CMD ["gunicorn", "-b", "0.0.0.0:10000", "app:app", "--timeout", "120"]
