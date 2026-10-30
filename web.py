"""Compatibility entry point: python web.py or uvicorn web:app."""
from config import settings
from drugagent.api import create_app

app = create_app()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=settings.host, port=settings.port, log_level="info")
