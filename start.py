"""Railway/production entrypoint — reads PORT and starts uvicorn."""
import os

port = int(os.environ.get("PORT", 8000))
workers = int(os.environ.get("WEB_CONCURRENCY", 1))
is_prod = os.environ.get("WEEKLYAMP_ENV", "development").lower() in ("production", "prod")

import uvicorn
uvicorn.run(
    "weeklyamp.web.app:create_app",
    host="0.0.0.0",
    port=port,
    workers=workers,
    factory=True,
    log_level=os.environ.get("LOG_LEVEL", "info").lower(),
    proxy_headers=True,
    forwarded_allow_ips="*",
    timeout_keep_alive=int(os.environ.get("UVICORN_TIMEOUT_KEEP_ALIVE", 5)),
    limit_max_requests=int(os.environ.get("UVICORN_LIMIT_MAX_REQUESTS", 0)) or None,
    limit_concurrency=int(os.environ.get("UVICORN_LIMIT_CONCURRENCY", 0)) or None,
    access_log=not is_prod,  # Disable access log in prod (use structured logging instead)
)
