"""Queue management for download requests."""

import threading
from collections import deque
from dataclasses import dataclass
from typing import Callable, List, Optional

from logger import Logger


@dataclass
class QueueItem:
    """Represents an item in the download queue."""

    user: str
    filename: str
    command: str
    status: str = "pending"  # pending, downloading, completed, failed

    def __str__(self) -> str:
        """String representation of queue item."""
        return f"{self.filename[:50]} (from {self.user})"


class QueueManager:
    """Manages the download queue with thread-safe operations."""

    def __init__(self, debug: bool = False):
        """
        Initialize queue manager.

        Args:
            debug: Whether to enable debug logging
        """
        self.logger = Logger("QueueMgr", debug)
        self._queue: deque[QueueItem] = deque()
        self._completed: List[QueueItem] = []
        self._current: Optional[QueueItem] = None
        self._lock = threading.Lock()
        self._callbacks: List[Callable[[], None]] = []

    def add(self, user: str, filename: str) -> None:
        """
        Add an item to the queue.

        Args:
            user: IRC username
            filename: File to download
        """
        command = f"!{user} {filename}"
        item = QueueItem(user=user, filename=filename, command=command)

        with self._lock:
            self._queue.append(item)
            self.logger.info(f"Added to queue: {item}")
            self.logger.debug(f"Queue size after add: {len(self._queue)}")
            self.logger.debug(f"About to notify {len(self._callbacks)} callbacks")
        # Notify callbacks AFTER releasing the lock to avoid deadlock
        self._notify_callbacks()

    def peek_next(self) -> Optional[QueueItem]:
        """
        Peek at the next item in the queue without removing it.

        Returns:
            Next queue item or None if queue is empty
        """
        with self._lock:
            if self._queue:
                item = self._queue[0]
                item.status = "downloading"
                self.logger.info(f"Processing: {item}")
                return item
            return None

    def get_next(self) -> Optional[QueueItem]:
        """
        Get the next item from the queue (removes it).

        Returns:
            Next queue item or None if queue is empty
        """
        item = None
        with self._lock:
            if self._queue:
                item = self._queue.popleft()
                item.status = "downloading"
                self.logger.info(f"Processing: {item}")
        # Notify callbacks AFTER releasing the lock to avoid deadlock
        if item:
            self._notify_callbacks()
        return item

    def mark_completed(self, item: QueueItem, success: bool = True) -> None:
        """
        Mark an item as completed and remove it from the queue.

        Args:
            item: Queue item to mark
            success: Whether download was successful
        """
        with self._lock:
            item.status = "completed" if success else "failed"
            self._completed.append(item)
            # Remove the item from the queue
            if self._queue and self._queue[0] == item:
                self._queue.popleft()
                self.logger.info(f"Removed completed item from queue")
            self.logger.info(f"Completed: {item} (success={success})")
            self.logger.info(f"Stats after completion: {len(self._completed)} done, {len(self._queue)} queued")
        # Notify callbacks AFTER releasing the lock to avoid deadlock
        self._notify_callbacks()

    def remove(self, index: int) -> bool:
        """
        Remove an item from the queue by index.

        Args:
            index: Index of item to remove

        Returns:
            True if removed, False if index invalid
        """
        removed = False
        with self._lock:
            if 0 <= index < len(self._queue):
                item = self._queue[index]
                del self._queue[index]
                self.logger.info(f"Removed from queue: {item}")
                removed = True
        # Notify callbacks AFTER releasing the lock to avoid deadlock
        if removed:
            self._notify_callbacks()
        return removed

    def move_up(self, index: int) -> bool:
        """
        Move an item up in the queue.

        Args:
            index: Index of item to move

        Returns:
            True if moved, False if already at top or invalid index
        """
        moved = False
        with self._lock:
            if 0 < index < len(self._queue):
                self._queue[index], self._queue[index - 1] = (
                    self._queue[index - 1],
                    self._queue[index],
                )
                moved = True
        # Notify callbacks AFTER releasing the lock to avoid deadlock
        if moved:
            self._notify_callbacks()
        return moved

    def move_down(self, index: int) -> bool:
        """
        Move an item down in the queue.

        Args:
            index: Index of item to move

        Returns:
            True if moved, False if already at bottom or invalid index
        """
        moved = False
        with self._lock:
            if 0 <= index < len(self._queue) - 1:
                self._queue[index], self._queue[index + 1] = (
                    self._queue[index + 1],
                    self._queue[index],
                )
                moved = True
        # Notify callbacks AFTER releasing the lock to avoid deadlock
        if moved:
            self._notify_callbacks()
        return moved

    def clear(self) -> None:
        """Clear all items from the queue."""
        with self._lock:
            count = len(self._queue)
            self._queue.clear()
            self.logger.info(f"Cleared {count} items from queue")
        # Notify callbacks AFTER releasing the lock to avoid deadlock
        self._notify_callbacks()

    def get_queue_items(self) -> List[QueueItem]:
        """
        Get a copy of all queue items.

        Returns:
            List of queue items
        """
        with self._lock:
            return list(self._queue)

    def get_completed_items(self) -> List[QueueItem]:
        """
        Get a copy of all completed items.

        Returns:
            List of completed items
        """
        with self._lock:
            return list(self._completed)

    def set_current(self, item: Optional[QueueItem]) -> None:
        """
        Set the currently downloading item.

        Args:
            item: Current item or None
        """
        with self._lock:
            self._current = item
        # Notify callbacks AFTER releasing the lock to avoid deadlock
        self._notify_callbacks()

    def get_current(self) -> Optional[QueueItem]:
        """
        Get the currently downloading item.

        Returns:
            Current item or None
        """
        with self._lock:
            return self._current

    def get_status(self) -> str:
        """
        Get queue status string.

        Returns:
            Status string showing completed/total
        """
        with self._lock:
            # Queue now includes the currently downloading item
            total = len(self._completed) + len(self._queue)
            return f"{len(self._completed)} done, {len(self._queue)} queued (Total: {total})"

    def is_empty(self) -> bool:
        """
        Check if queue is empty.

        Returns:
            True if queue is empty
        """
        with self._lock:
            return len(self._queue) == 0

    def size(self) -> int:
        """
        Get queue size.

        Returns:
            Number of items in queue
        """
        with self._lock:
            return len(self._queue)

    def register_callback(self, callback: Callable[[], None]) -> None:
        """
        Register a callback to be called when queue changes.

        Args:
            callback: Function to call on queue changes
        """
        self._callbacks.append(callback)

    def _notify_callbacks(self) -> None:
        """Notify all registered callbacks of queue changes."""
        for callback in self._callbacks:
            try:
                callback()
            except Exception as e:
                self.logger.error(f"Error in queue callback: {e}")
                import traceback
                traceback.print_exc()
