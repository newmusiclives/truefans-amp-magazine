FROM python:3.12-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy project files
COPY . .

# Set Python path so src layout works
ENV PYTHONPATH=/app/src
ENV PYTHONUNBUFFERED=1

# Railway sets PORT dynamically
CMD python -m uvicorn weeklyamp.web.app:create_app --host 0.0.0.0 --port ${PORT:-8000} --factory
