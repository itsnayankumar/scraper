FROM python:3.10-slim

# 1. Install Chrome, wget, and unzip
RUN apt-get update && apt-get install -y wget gnupg2 unzip curl \
    && wget -q -O - https://dl-ssl.google.com/linux/linux_signing_key.pub | apt-key add - \
    && sh -c 'echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" >> /etc/apt/sources.list.d/google-chrome.list' \
    && apt-get update \
    && apt-get install -y google-chrome-stable \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# 2. Set up App
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 3. Copy Files
COPY . .

# 4. Run Command
CMD ["gunicorn", "-b", "0.0.0.0:10000", "app:app", "--timeout", "120"]
