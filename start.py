"""Railway entrypoint — reads PORT and starts uvicorn."""
import os
import sys

port = int(os.environ.get("PORT", 8000))
print(f"Starting TrueFans AMP on port {port}", flush=True)
print(f"Python: {sys.version}", flush=True)
print(f"CWD: {os.getcwd()}", flush=True)
print(f"PYTHONPATH: {os.environ.get('PYTHONPATH', 'not set')}", flush=True)
print(f"Files in /app: {os.listdir('/app') if os.path.isdir('/app') else 'N/A'}", flush=True)

import uvicorn
uvicorn.run(
    "weeklyamp.web.app:create_app",
    host="0.0.0.0",
    port=port,
    factory=True,
    log_level="info",
)
