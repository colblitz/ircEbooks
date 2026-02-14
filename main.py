#!/usr/bin/env python3
"""Main entry point for IRC Ebook Fetcher."""

import sys
import threading
import time
import traceback
from typing import Optional

import irc.client

from config import Config
from gui import EbookFetcherGUI
from irc_client import IRCEbookClient, QueueProcessorThread
from logger import Logger
from queue_manager import QueueManager


class IRCClientThread(threading.Thread):
    """Thread for running the IRC client."""

    def __init__(self, config: Config, queue_manager: QueueManager):
        """
        Initialize IRC client thread.

        Args:
            config: Application configuration
            queue_manager: Queue manager instance
        """
        super().__init__(name="IRCClient", daemon=True)
        self.config = config
        self.queue_manager = queue_manager
        self.logger = Logger("ClientThread", config.debug)
        self.client: Optional[IRCEbookClient] = None

    def run(self) -> None:
        """Run the IRC client."""
        self.logger.info("Starting IRC client thread")

        if not irc.client.is_channel(self.config.irc_channel):
            self.logger.error(f"Invalid channel: {self.config.irc_channel}")
            return

        self.client = IRCEbookClient(self.config, self.queue_manager)

        try:
            self.logger.info(
                f"Connecting to {self.config.irc_server}:{self.config.irc_port}"
            )
            self.client.connect(
                self.config.irc_server, self.config.irc_port, self.config.bot_nick
            )
            self.client.start()
        except Exception as e:
            self.logger.error(f"Connection error: {e}")
            traceback.print_exc()
            sys.exit(1)

    def get_client(self) -> IRCEbookClient:
        """
        Get the IRC client instance.

        Returns:
            IRC client instance

        Raises:
            RuntimeError: If client not yet initialized
        """
        if self.client is None:
            raise RuntimeError("IRC client not yet initialized")
        return self.client


def main():
    """Main application entry point."""
    # Load configuration
    config = Config.from_env()
    logger = Logger("Main", config.debug)

    logger.info("=" * 60)
    logger.info("IRC Ebook Fetcher Starting")
    logger.info("=" * 60)
    logger.info(f"IRC Server: {config.irc_server}:{config.irc_port}")
    logger.info(f"Channel: {config.irc_channel}")
    logger.info(f"Bot Nick: {config.bot_nick}")
    logger.info(f"Working Directory: {config.working_directory}")
    logger.info("=" * 60)

    # Create queue manager
    queue_manager = QueueManager(config.debug)

    # Start IRC client thread
    logger.info("Starting IRC client thread...")
    client_thread = IRCClientThread(config, queue_manager)
    client_thread.start()

    # Wait for IRC connection to establish
    logger.info(f"Waiting {config.connection_wait_time} seconds for IRC connection...")
    time.sleep(config.connection_wait_time)

    # Get client instance
    try:
        client = client_thread.get_client()
    except RuntimeError as e:
        logger.error(f"Failed to get IRC client: {e}")
        sys.exit(1)

    # Start queue processor thread
    logger.info("Starting queue processor thread...")
    queue_thread = QueueProcessorThread(client, queue_manager, config.debug)
    queue_thread.start()

    # Create and run GUI
    logger.info("Creating GUI...")
    try:
        gui = EbookFetcherGUI(config, client, queue_manager)
        gui.create_gui()
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
    except Exception as e:
        logger.error(f"GUI error: {e}")
        traceback.print_exc()
        sys.exit(1)

    logger.info("Application shutting down")


if __name__ == "__main__":
    main()
