#!/usr/bin/env python3
"""
Upload Bot Main Entry Point

Standalone Telegram bot for admins to upload documents to the Ingestion Service.

Usage:
    python -m services.upload_bot.main
"""

import asyncio
import logging
import sys
from pathlib import Path

# Add project root to path to import shared modules
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from services.upload_bot.bot import UploadBot
from services.upload_bot.config import (
    get_allowed_upload_user_ids,
    get_ingestion_service_url,
    get_upload_bot_token,
)

# Configure logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


def main() -> None:
    """Run the Upload Bot."""
    try:
        token = get_upload_bot_token()
        ingestion_url = get_ingestion_service_url()
        allowed_ids = get_allowed_upload_user_ids()

        bot = UploadBot(
            token=token,
            ingestion_service_url=ingestion_url,
            allowed_user_ids=allowed_ids,
        )

        logger.info("Starting Upload Bot...")
        bot.application.run_polling()

    except ValueError as e:
        logger.error(f"Configuration error: {e}")
        sys.exit(1)
    except KeyboardInterrupt:
        logger.info("Upload Bot stopped by user")
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
