FROM python:3.12-slim

WORKDIR /app

# Copy and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy all project files
COPY . .

# Set Python path so src layout works
ENV PYTHONPATH=/app/src
ENV PYTHONUNBUFFERED=1

# Create data directory and verify build
RUN mkdir -p /app/data && \
    python -c "from weeklyamp.web.app import create_app; print('Build verification: OK')"

EXPOSE 8000

# Python entrypoint reads PORT from env directly — no shell expansion needed
ENTRYPOINT ["python", "/app/start.py"]
