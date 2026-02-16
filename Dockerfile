FROM python:3.12-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy project files
COPY . .

# Verify key files exist
RUN ls -la /app/config/default.yaml /app/src/weeklyamp/db/schema.sql /app/templates/web/base.html

# Set Python path so src layout works
ENV PYTHONPATH=/app/src
ENV PYTHONUNBUFFERED=1

# Create data directory
RUN mkdir -p /app/data

# Railway sets PORT dynamically
CMD python -m uvicorn weeklyamp.web.app:create_app --host 0.0.0.0 --port ${PORT:-8000} --factory --log-level info
