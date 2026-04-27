import uvicorn

from app.config import get_settings
from app.logging_config import LOGGING_CONFIG, configure_logging


def main() -> None:
    settings = get_settings()
    configure_logging(settings.environment)
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        log_config=LOGGING_CONFIG,
        reload=settings.environment == "development",
    )


if __name__ == "__main__":
    main()
