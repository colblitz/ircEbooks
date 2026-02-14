"""IRC client for ebook fetching."""

import shlex
import struct
import threading
import time
from pathlib import Path
from typing import Optional, Set

import irc.client

from config import Config
from logger import Logger
from queue_manager import QueueManager, QueueItem


class IRCEbookClient(irc.client.SimpleIRCClient):
    """IRC client for fetching ebooks."""

    def __init__(self, config: Config, queue_manager: QueueManager):
        """
        Initialize IRC client.

        Args:
            config: Application configuration
            queue_manager: Queue manager instance
        """
        super().__init__()
        self.config = config
        self.queue_manager = queue_manager
        self.logger = Logger("IRCClient", config.debug)

        # State management with thread safety
        self._lock = threading.Lock()
        self._waiting_for_file: Optional[str] = None
        self._latest_file: Optional[Path] = None
        self._latest_filename: Optional[Path] = None
        self._received_bytes = 0
        self._total_bytes = 0  # Total file size for progress tracking
        self._current_item: Optional[QueueItem] = None
        self._users_online: Set[str] = set()

        # File handling
        self._file_handle = None
        self._dcc_connection = None

        # Configure connection to handle encoding errors
        self.connection.buffer_class.errors = "replace"

        # Search result event
        self.search_complete = threading.Event()
        self.search_result: Optional[str] = None

    @property
    def waiting_for_file(self) -> Optional[str]:
        """Thread-safe getter for waiting_for_file."""
        with self._lock:
            return self._waiting_for_file

    @waiting_for_file.setter
    def waiting_for_file(self, value: Optional[str]) -> None:
        """Thread-safe setter for waiting_for_file."""
        with self._lock:
            self._waiting_for_file = value

    @property
    def latest_filename(self) -> Optional[Path]:
        """Thread-safe getter for latest_filename."""
        with self._lock:
            return self._latest_filename

    def on_welcome(self, connection, event) -> None:
        """Handle successful connection to IRC server."""
        self.logger.info(f"Connected to {self.config.irc_server}")
        connection.join(self.config.irc_channel)

    def on_join(self, connection, event) -> None:
        """Handle channel join."""
        if event.source.nick == self.config.bot_nick:
            self.logger.info(f"Joined channel: {self.config.irc_channel}")

    def check_users_online(self, usernames: Set[str]) -> None:
        """
        Check which users are online.

        Args:
            usernames: Set of usernames to check
        """
        self._users_online = set()
        if usernames:
            self.connection.ison(list(usernames))

    def on_ison(self, connection, event) -> None:
        """Handle ISON response."""
        self._users_online = set(event.arguments[0].split())
        self.logger.debug(f"Users online: {self._users_online}")

    def get_users_online(self) -> Set[str]:
        """
        Get set of users currently online.

        Returns:
            Set of online usernames
        """
        return self._users_online.copy()

    def send_privmsg(self, message: str) -> None:
        """
        Send a private message to the handler.

        Args:
            message: Message to send
        """
        self.logger.info(f"PM to {self.config.handler}: {message}")
        self.connection.privmsg(self.config.handler, message)

    def send_channel_message(self, message: str) -> None:
        """
        Send a message to the channel.

        Args:
            message: Message to send
        """
        self.logger.info(f"To channel: {message}")
        self.connection.privmsg(self.config.irc_channel, message)

    def request_book(self, user: str, filename: str) -> None:
        """
        Request a book from a user.

        Args:
            user: Username to request from
            filename: File to request
        """
        # Always add to queue first for consistent behavior
        self.queue_manager.add(user, filename)
        
        # If not currently downloading, trigger queue processor
        if not self.waiting_for_file:
            self.process_queue()

    def process_queue(self) -> None:
        """Process the next item in the queue if not waiting."""
        if not self.waiting_for_file and not self.queue_manager.is_empty():
            item = self.queue_manager.peek_next()
            if item:
                self._current_item = item
                self.queue_manager.set_current(item)
                self.send_channel_message(item.command)
                self.waiting_for_file = "Book"

    def do_search(self, search_text: str) -> None:
        """
        Perform a search for ebooks.

        Args:
            search_text: Text to search for
        """
        message = f"@search {search_text}"
        self.logger.info(f"Searching for: {search_text}")
        self.search_complete.clear()
        self.search_result = None
        self.send_channel_message(message)
        self.waiting_for_file = "Search"

    def on_privmsg(self, connection, event) -> None:
        """Handle private messages."""
        message = event.arguments[0]
        self.logger.info(f"PM from {event.source.nick}: {message}")

        if message == "quit":
            self.logger.info("Received quit command")
            connection.disconnect()

    def on_pubmsg(self, connection, event) -> None:
        """Handle public channel messages."""
        message = event.arguments[0]
        self.logger.debug(f"{event.source.nick}: {message}")

    def on_notice(self, connection, event) -> None:
        """Handle notices."""
        self.logger.debug(f"Notice: {event}")

    def on_privnotice(self, connection, event) -> None:
        """Handle private notices."""
        message = event.arguments[0]
        if event.target == self.config.bot_nick:
            self.logger.info(f"Private notice from {event.source.nick}: {message}")

        if "returned no matches" in message or "Sorry" in message:
            self.logger.info("No search results found")
            self.waiting_for_file = None
            self.search_result = "NoResults"
            self.search_complete.set()

    def on_ctcp(self, connection, event) -> None:
        """Handle CTCP messages (DCC file transfers)."""
        if event.target != self.config.bot_nick:
            return

        payload = event.arguments[1]
        if "SEND" not in payload:
            return

        try:
            self._handle_dcc_send(event, payload)
        except Exception as e:
            self.logger.error(f"Error handling DCC SEND: {e}")

    def _handle_dcc_send(self, event, payload: str) -> None:
        """
        Handle DCC SEND request.

        Args:
            event: IRC event
            payload: CTCP payload
        """
        lex = shlex.shlex(payload)
        lex.whitespace_split = True
        parts = list(lex)

        if len(parts) < 5:
            self.logger.error(f"Invalid DCC SEND format: {payload}")
            return

        command, filename, peer_address, peer_port, size = parts
        if command != "SEND":
            return

        # Clean filename
        if filename.startswith('"') and filename.endswith('"'):
            filename = filename[1:-1]

        # Save to working directory
        save_path = self.config.working_directory / Path(filename).name
        total_size = int(size)
        
        self.logger.info(f"Receiving file from {event.source.nick}: {filename}")
        self.logger.info(f"File size: {total_size} bytes ({total_size / 1024 / 1024:.2f} MB)")
        self.logger.info(f"Saving to: {save_path}")

        with self._lock:
            self._latest_filename = save_path
            self._total_bytes = total_size
            self._received_bytes = 0
            self._file_handle = open(save_path, "wb")

        # Connect to DCC
        peer_address = irc.client.ip_numstr_to_quad(peer_address)
        peer_port = int(peer_port)
        self._dcc_connection = self.dcc_connect(peer_address, peer_port, "raw")

    def on_dccmsg(self, connection, event) -> None:
        """Handle DCC messages (file data)."""
        data = event.arguments[0]

        if self._file_handle:
            self._file_handle.write(data)
            self._received_bytes += len(data)
            self._dcc_connection.send_bytes(struct.pack("!I", self._received_bytes))

    def on_dcc_disconnect(self, connection, event) -> None:
        """Handle DCC disconnect (file transfer complete)."""
        if self._file_handle:
            self._file_handle.close()
            self._file_handle = None

        file_type = self.waiting_for_file
        filename = self._latest_filename
        size = self._received_bytes

        self.logger.info(f"Received {file_type}: {filename} ({size} bytes)")
        self.logger.info(f"Current item before completion: {self._current_item}")

        # Clear waiting_for_file FIRST before updating queue
        # This ensures status bar updates correctly
        self.waiting_for_file = None
        self._received_bytes = 0
        self._total_bytes = 0

        if file_type == "Search":
            self.search_result = str(filename)
            self.search_complete.set()
        elif file_type == "Book" and self._current_item:
            self.logger.info(f"Marking as completed: {self._current_item}")
            self.queue_manager.mark_completed(self._current_item, success=True)
            self.logger.info(f"Setting current to None")
            self.queue_manager.set_current(None)
            self._current_item = None
            self.logger.info(f"Completion handling done")
        else:
            self.logger.info(f"NOT marking as completed - file_type={file_type}, current_item={self._current_item}")

    def on_disconnect(self, connection, event) -> None:
        """Handle disconnection from IRC server."""
        self.logger.info("Disconnected from IRC server")

    def cancel_current_download(self) -> None:
        """Cancel the current download."""
        if self._current_item:
            self.logger.info(f"Cancelling download: {self._current_item}")
            self.queue_manager.mark_completed(self._current_item, success=False)
            self.queue_manager.set_current(None)
            self._current_item = None
        self.waiting_for_file = None

    def get_download_progress(self) -> tuple[int, int, float]:
        """
        Get current download progress.

        Returns:
            Tuple of (received_bytes, total_bytes, percentage)
        """
        with self._lock:
            if self._total_bytes > 0:
                percentage = (self._received_bytes / self._total_bytes) * 100
            else:
                percentage = 0.0
            return (self._received_bytes, self._total_bytes, percentage)


class QueueProcessorThread(threading.Thread):
    """Thread that processes the download queue."""

    def __init__(self, client: IRCEbookClient, queue_manager: QueueManager, debug: bool = False):
        """
        Initialize queue processor thread.

        Args:
            client: IRC client instance
            queue_manager: Queue manager instance
            debug: Whether to enable debug logging
        """
        super().__init__(name="QueueProcessor", daemon=True)
        self.client = client
        self.queue_manager = queue_manager
        self.logger = Logger("QueueProc", debug)
        self._stop_event = threading.Event()

    def run(self) -> None:
        """Process queue items."""
        self.logger.info("Queue processor started")
        check_count = 0

        while not self._stop_event.is_set():
            if not self.client.waiting_for_file and not self.queue_manager.is_empty():
                self.logger.debug("Processing next item in queue")
                self.client.process_queue()

            time.sleep(1)
            check_count += 1

            if check_count % 10 == 0:
                self.logger.debug(f"Queue size: {self.queue_manager.size()}")

    def stop(self) -> None:
        """Stop the queue processor."""
        self.logger.info("Stopping queue processor")
        self._stop_event.set()
