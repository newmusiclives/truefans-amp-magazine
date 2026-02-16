FROM python:3.12-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy project files
COPY . .

# Verify key files exist at build time
RUN python -c "from pathlib import Path; assert Path('/app/config/default.yaml').exists(); assert Path('/app/src/weeklyamp/db/schema.sql').exists(); assert Path('/app/templates/web/base.html').exists(); print('All files OK')"

# Verify imports work at build time
RUN PYTHONPATH=/app/src python -c "from weeklyamp.web.app import create_app; print('Import OK')"

# Set Python path so src layout works
ENV PYTHONPATH=/app/src
ENV PYTHONUNBUFFERED=1

# Create data directory
RUN mkdir -p /app/data

# Use Python entrypoint for reliable PORT handling
CMD ["python", "/app/start.py"]
