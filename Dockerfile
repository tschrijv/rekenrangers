FROM docker.io/library/python:3.14.0-slim-trixie

WORKDIR /mathquiz

# Install Python deps
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Install netcat for wait-for-mysql.sh
RUN apt-get update && apt-get install -y netcat-openbsd && rm -rf /var/lib/apt/lists/*

# Copy app code
COPY mathquiz ./

# Copy wait script
COPY wait-for-mysql.sh /wait-for-mysql.sh
RUN chmod +x /wait-for-mysql.sh

# Start Flask after waiting for DB
CMD ["/wait-for-mysql.sh", "flask", "run", "--host=0.0.0.0", "--port=5000"]
