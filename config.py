"""Configuration management for IRC Ebook Fetcher."""

import os
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass
class Config:
    """Application configuration."""

    # IRC Settings
    irc_server: str = "irc.irchighway.net"
    irc_port: int = 6667
    irc_channel: str = "#ebooks"
    handler: str = "colblitz"
    bot_nick: str = f"fetcher{random.randint(1000, 9999)}"

    # Application Settings
    working_directory: Path = Path("ebooks")
    debug: bool = False
    connection_wait_time: int = 10  # Seconds to wait for IRC connection

    # GUI Settings
    window_title: str = "IRC Ebook Fetcher"
    window_geometry: str = "900x600"

    def __post_init__(self):
        """Ensure working directory exists."""
        if not self.working_directory.exists():
            print(f"Creating directory: {self.working_directory}")
            self.working_directory.mkdir(parents=True, exist_ok=True)

    @classmethod
    def from_env(cls) -> "Config":
        """Load configuration from environment variables."""
        return cls(
            irc_server=os.getenv("IRC_SERVER", cls.irc_server),
            irc_port=int(os.getenv("IRC_PORT", cls.irc_port)),
            irc_channel=os.getenv("IRC_CHANNEL", cls.irc_channel),
            handler=os.getenv("IRC_HANDLER", cls.handler),
            working_directory=Path(os.getenv("WORKING_DIR", cls.working_directory)),
            debug=os.getenv("DEBUG", "false").lower() == "true",
            connection_wait_time=int(os.getenv("CONNECTION_WAIT_TIME", "10")),
        )
