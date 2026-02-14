"""Main GUI for IRC Ebook Fetcher."""

import threading
import time
from pathlib import Path
from tkinter import (
    Tk,
    Frame,
    Label,
    Entry,
    Button,
    Spinbox,
    Listbox,
    Scrollbar,
    StringVar,
    IntVar,
    Checkbutton,
    messagebox,
    END,
    LEFT,
    RIGHT,
    TOP,
    BOTTOM,
    BOTH,
    X,
    Y,
    W,
    E,
    HORIZONTAL,
    VERTICAL,
)
from tkinter import ttk
from tkinter.ttk import Progressbar
from typing import Dict, List, Set, Optional

from config import Config
from file_processor import FileProcessor
from gui_components import VerticalScrolledFrame, color_scale
from irc_client import IRCEbookClient
from logger import Logger
from queue_manager import QueueManager


class SearchResultRow:
    """Represents a row in the search results."""

    def __init__(self, filename: str, users: Set[str], online_users: Set[str]):
        """
        Initialize search result row.

        Args:
            filename: Name of the file
            users: Set of users who have the file
            online_users: Set of users currently online
        """
        self.filename = filename
        self.users = users
        self.online_users = online_users
        self.widgets: List = []

    def matches_filter(self, min_users: int) -> bool:
        """
        Check if this row matches the filter.

        Args:
            min_users: Minimum number of users required

        Returns:
            True if row matches filter
        """
        return len(self.users) >= min_users

    def matches_search(self, search_text: str) -> bool:
        """
        Check if this row matches the search text.

        Args:
            search_text: Text to search for

        Returns:
            True if filename contains search text
        """
        if not search_text:
            return True
        return search_text.lower() in self.filename.lower()


class EbookFetcherGUI:
    """Main GUI application."""

    def __init__(self, config: Config, client: IRCEbookClient, queue_manager: QueueManager):
        """
        Initialize GUI.

        Args:
            config: Application configuration
            client: IRC client instance
            queue_manager: Queue manager instance
        """
        self.config = config
        self.client = client
        self.queue_manager = queue_manager
        self.file_processor = FileProcessor(config.debug)
        self.logger = Logger("GUI", config.debug)

        # GUI state
        self.search_results: List[SearchResultRow] = []
        self.root: Optional[Tk] = None
        self.default_color = ""
        self.darker_color = ""
        self._search_in_progress = False

        # GUI widgets
        self.search_field: Optional[Entry] = None
        self.search_filter_field: Optional[Entry] = None
        self.results_filter: Optional[Spinbox] = None
        self.results_list: Optional[VerticalScrolledFrame] = None
        self.status_label: Optional[Label] = None
        self.progress_bar: Optional[Progressbar] = None
        self.progress_label: Optional[Label] = None
        self.queue_listbox: Optional[Listbox] = None
        self.cancel_search_button: Optional[Button] = None
        
        # File type filter checkboxes
        self.file_type_vars: Dict[str, IntVar] = {}
        self.hide_offline_var: Optional[IntVar] = None

        # Register queue callback
        self.queue_manager.register_callback(self._on_queue_changed)

    def create_gui(self) -> None:
        """Create and display the GUI."""
        self.logger.info("Creating GUI")

        self.root = Tk()
        self.root.title(self.config.window_title)
        self.root.geometry(self.config.window_geometry)

        self.default_color = self.root.cget("bg")
        self.darker_color = color_scale(self.default_color, 0.9)

        # Create main layout
        self._create_search_panel()
        self._create_results_panel()
        self._create_queue_panel()
        self._create_status_bar()

        # Bind keyboard shortcuts
        self.root.bind("<Return>", lambda e: self._do_search())
        self.root.bind("<Escape>", lambda e: self.search_field.focus())

        # Start status update loop
        self.root.after(200, self._update_status)

        self.logger.info("GUI created, starting main loop")
        self.root.mainloop()

    def _create_search_panel(self) -> None:
        """Create the search input panel."""
        search_frame = Frame(self.root)
        search_frame.pack(side=TOP, fill=X, padx=5, pady=5)

        # Search field
        Label(search_frame, text="Search:").pack(side=LEFT)
        self.search_field = Entry(search_frame)
        self.search_field.pack(side=LEFT, fill=X, expand=True, padx=5)

        # Search button
        Button(search_frame, text="Search", command=self._do_search).pack(side=RIGHT)

        # Cancel button
        Button(search_frame, text="Cancel Current", command=self._cancel_current).pack(
            side=RIGHT, padx=2
        )

    def _create_results_panel(self) -> None:
        """Create the search results panel."""
        results_frame = Frame(self.root)
        results_frame.pack(side=TOP, fill=BOTH, expand=True, padx=5, pady=5)

        # Filter controls - Row 1
        filter_frame1 = Frame(results_frame)
        filter_frame1.pack(side=TOP, fill=X, pady=(0, 2))

        Label(filter_frame1, text="Min users:").pack(side=LEFT)
        self.results_filter = Spinbox(
            filter_frame1, from_=0, to=20, width=5, command=self._update_results_filter
        )
        self.results_filter.pack(side=LEFT, padx=5)

        Label(filter_frame1, text="Filter text:").pack(side=LEFT, padx=(10, 0))
        self.search_filter_field = Entry(filter_frame1, width=30)
        self.search_filter_field.pack(side=LEFT, padx=5)
        self.search_filter_field.bind("<KeyRelease>", lambda e: self._update_results_filter())

        Button(filter_frame1, text="Clear Filters", command=self._clear_filters).pack(
            side=LEFT, padx=5
        )

        # Filter controls - Row 2: File types and hide offline
        filter_frame2 = Frame(results_frame)
        filter_frame2.pack(side=TOP, fill=X, pady=(0, 5))

        Label(filter_frame2, text="File types:").pack(side=LEFT)
        
        # Create checkboxes for common ebook formats
        file_types = ['epub', 'mobi', 'pdf', 'azw3', 'cbz']
        for ft in file_types:
            var = IntVar(value=1 if ft == 'epub' else 0)  # EPUB checked by default
            self.file_type_vars[ft] = var
            cb = Checkbutton(
                filter_frame2, 
                text=ft.upper(), 
                variable=var,
                command=self._update_results_filter
            )
            cb.pack(side=LEFT, padx=2)
        
        # Add separator
        Label(filter_frame2, text=" | ").pack(side=LEFT, padx=10)
        
        # Hide offline toggle
        self.hide_offline_var = IntVar(value=0)
        Checkbutton(
            filter_frame2,
            text="Hide offline users",
            variable=self.hide_offline_var,
            command=self._update_results_filter
        ).pack(side=LEFT)

        # Results list
        self.results_list = VerticalScrolledFrame(results_frame)
        self.results_list.pack(side=TOP, fill=BOTH, expand=True)

    def _create_queue_panel(self) -> None:
        """Create the download queue panel."""
        queue_frame = Frame(self.root)
        queue_frame.pack(side=BOTTOM, fill=BOTH, padx=5, pady=5)

        Label(queue_frame, text="Download Queue:", font=("", 10, "bold")).pack(
            side=TOP, anchor=W
        )

        # Queue list with scrollbar
        list_frame = Frame(queue_frame)
        list_frame.pack(side=LEFT, fill=BOTH, expand=True)

        scrollbar = Scrollbar(list_frame, orient=VERTICAL)
        self.queue_listbox = Listbox(
            list_frame, height=6, yscrollcommand=scrollbar.set, selectmode="single"
        )
        scrollbar.config(command=self.queue_listbox.yview)
        scrollbar.pack(side=RIGHT, fill=Y)
        self.queue_listbox.pack(side=LEFT, fill=BOTH, expand=True)

        # Queue control buttons
        button_frame = Frame(queue_frame)
        button_frame.pack(side=RIGHT, fill=Y, padx=5)

        Button(button_frame, text="↑ Move Up", command=self._move_queue_up, width=12).pack(
            pady=2
        )
        Button(button_frame, text="↓ Move Down", command=self._move_queue_down, width=12).pack(
            pady=2
        )
        Button(button_frame, text="✕ Remove", command=self._remove_from_queue, width=12).pack(
            pady=2
        )
        Button(button_frame, text="Clear All", command=self._clear_queue, width=12).pack(
            pady=2
        )

    def _create_status_bar(self) -> None:
        """Create the status bar with progress bar."""
        status_frame = Frame(self.root, relief="sunken", bd=1)
        status_frame.pack(side=BOTTOM, fill=X)

        # Status text
        self.status_label = Label(status_frame, text="Ready", anchor=W)
        self.status_label.pack(side=LEFT, fill=X, expand=True, padx=5)

        # Progress label (shows MB downloaded)
        self.progress_label = Label(status_frame, text="", anchor=E, width=20)
        self.progress_label.pack(side=RIGHT, padx=5)

        # Progress bar
        self.progress_bar = Progressbar(status_frame, length=200, mode='determinate')
        self.progress_bar.pack(side=RIGHT, padx=5)

    def _do_search(self) -> None:
        """Perform a search."""
        if self.client.waiting_for_file:
            messagebox.showwarning("Busy", "Please wait for current operation to complete or cancel it")
            return

        search_text = self.search_field.get().strip()
        if not search_text:
            messagebox.showwarning("Empty Search", "Please enter search text")
            return

        self.logger.info(f"Searching for: {search_text}")
        self.search_field.delete(0, END)

        # Clear previous results
        self._clear_results()
        
        # Mark search as in progress
        self._search_in_progress = True

        # Start search in background thread
        threading.Thread(
            target=self._search_thread, args=(search_text,), daemon=True
        ).start()

    def _search_thread(self, search_text: str) -> None:
        """
        Perform search in background thread.

        Args:
            search_text: Text to search for
        """
        try:
            # Send search request
            self.client.do_search(search_text)

            # Wait for results (no timeout - wait indefinitely)
            self.logger.info("Waiting for search results... (use 'Cancel Current' to cancel)")
            self.client.search_complete.wait()

            # Check if search was cancelled
            if not self._search_in_progress:
                self.logger.info("Search was cancelled")
                return

            if self.client.search_result == "NoResults":
                self.logger.info("No results found")
                self._search_in_progress = False
                self.root.after(
                    0, lambda: messagebox.showinfo("No Results", "No matches found")
                )
                return

            # Process results with selected file types
            self.logger.info("Processing search results")
            results_file = Path(self.client.search_result)
            
            # Get selected file types
            selected_types = {ft for ft, var in self.file_type_vars.items() if var.get() == 1}
            if not selected_types:
                # If no types selected, use all
                selected_types = None
            
            available = self.file_processor.process_search_results(results_file, selected_types)

            if not available:
                self._search_in_progress = False
                self.root.after(
                    0, lambda: messagebox.showinfo("No Results", "No files found with selected types")
                )
                return

            # Check which users are online
            all_users = set()
            for users in available.values():
                all_users.update(users)

            self.client.check_users_online(all_users)
            time.sleep(0.5)  # Give time for ISON response
            online_users = self.client.get_users_online()

            # Display results
            self._search_in_progress = False
            self.root.after(
                0, lambda: self._display_results(available, online_users)
            )

        except Exception as e:
            self.logger.error(f"Search error: {e}")
            self._search_in_progress = False
            self.root.after(
                0, lambda: messagebox.showerror("Error", f"Search failed: {e}")
            )

    def _display_results(
        self, available: Dict[str, Set[str]], online_users: Set[str]
    ) -> None:
        """
        Display search results.

        Args:
            available: Dictionary mapping filenames to sets of users
            online_users: Set of users currently online
        """
        self.logger.info(f"Displaying {len(available)} results")

        # Create result rows
        self.search_results = []
        for filename in sorted(available.keys()):
            users = available[filename]
            row = SearchResultRow(filename, users, online_users)
            self.search_results.append(row)

        # Update filter max value
        max_users = max(len(row.users) for row in self.search_results)
        self.results_filter.config(to=max_users)

        # Display results
        self._update_results_filter()

    def _update_results_filter(self) -> None:
        """Update the results display based on filters."""
        if not self.search_results:
            return

        # Get filter values
        try:
            min_users = int(self.results_filter.get())
        except ValueError:
            min_users = 0

        filter_text = self.search_filter_field.get().strip()
        hide_offline = self.hide_offline_var.get() == 1

        # Clear existing widgets
        self._clear_results()

        # Display filtered results
        row_num = 0
        for result in self.search_results:
            if not result.matches_filter(min_users):
                continue
            if not result.matches_search(filter_text):
                continue
            
            # Skip if hiding offline and no users are online
            if hide_offline and not result.online_users:
                continue

            self._create_result_row(result, row_num, hide_offline)
            row_num += 1

        self.logger.info(f"Displayed {row_num} results")

    def _create_result_row(self, result: SearchResultRow, row_num: int, hide_offline: bool = False) -> None:
        """
        Create a single result row.

        Args:
            result: Search result row data
            row_num: Row number for grid placement
            hide_offline: If True, only show online users
        """
        bg_color = self.darker_color if row_num % 2 == 0 else self.default_color

        # Filename label
        filename_text = result.filename[:100]
        if len(result.filename) > 100:
            filename_text += "..."

        label = Label(
            self.results_list,
            text=filename_text,
            justify=LEFT,
            anchor=W,
            bg=bg_color,
        )
        label.grid(row=row_num, column=0, sticky=W + E, padx=2, pady=1)
        result.widgets.append(label)

        # User buttons
        col_num = 1
        for user in sorted(result.users):
            is_online = user in result.online_users
            
            # Skip offline users if hide_offline is enabled
            if hide_offline and not is_online:
                continue
            
            btn = Button(
                self.results_list,
                text=user,
                bg=bg_color,
                command=lambda u=user, f=result.filename: self._request_book(u, f),
                state="normal" if is_online else "disabled",
            )
            btn.grid(row=row_num, column=col_num, sticky=W + E, padx=1, pady=1)
            result.widgets.append(btn)
            col_num += 1

    def _clear_results(self) -> None:
        """Clear all result widgets."""
        for result in self.search_results:
            for widget in result.widgets:
                widget.destroy()
            result.widgets.clear()

    def _clear_filters(self) -> None:
        """Clear all filters."""
        self.results_filter.delete(0, END)
        self.results_filter.insert(0, "0")
        self.search_filter_field.delete(0, END)
        self._update_results_filter()

    def _request_book(self, user: str, filename: str) -> None:
        """
        Request a book download.

        Args:
            user: Username to request from
            filename: File to request
        """
        self.logger.info(f"Requesting {filename} from {user}")
        self.client.request_book(user, filename)

    def _cancel_current(self) -> None:
        """Cancel the current download or search."""
        if self.client.waiting_for_file:
            operation_type = self.client.waiting_for_file
            
            if operation_type == "Search":
                # Cancel search
                self._search_in_progress = False
                self.client.waiting_for_file = None
                self.logger.info("Search cancelled by user")
                messagebox.showinfo("Cancelled", "Search cancelled")
            elif operation_type == "Book":
                # Cancel download
                self.client.cancel_current_download()
                messagebox.showinfo("Cancelled", "Download cancelled")
            else:
                # Unknown operation
                self.client.waiting_for_file = None
                messagebox.showinfo("Cancelled", "Operation cancelled")
        else:
            messagebox.showinfo("Nothing to Cancel", "No operation in progress")

    def _update_queue_display(self) -> None:
        """Update the queue listbox."""
        try:
            self.logger.debug("_update_queue_display called")
            self.queue_listbox.delete(0, END)
            self.logger.debug("Cleared listbox successfully")
            
            # Show all queued items (first one is downloading if current is set)
            items = self.queue_manager.get_queue_items()
            current = self.queue_manager.get_current()
            self.logger.debug(f"Got {len(items)} queued items, current: {current}")
            
            for i, item in enumerate(items):
                # Mark the first item as downloading if it matches current
                if i == 0 and current and item == current:
                    display_text = f"⬇ DOWNLOADING: {item}"
                else:
                    display_text = f"{i + 1}. {item}"
                self.queue_listbox.insert(END, display_text)
            
            self.logger.debug("_update_queue_display completed successfully")
        except Exception as e:
            self.logger.error(f"EXCEPTION in _update_queue_display: {e}")
            import traceback
            traceback.print_exc()
            self.logger.error("Exception details printed above")

    def _move_queue_up(self) -> None:
        """Move selected queue item up."""
        selection = self.queue_listbox.curselection()
        if not selection:
            return

        index = selection[0]
        
        # Adjust for current item being shown at index 0
        has_current = self.queue_manager.get_current() is not None
        if has_current:
            if index == 0:
                # Can't move the downloading item
                return
            index -= 1  # Adjust to actual queue index
        
        if self.queue_manager.move_up(index):
            self._update_queue_display()
            # Re-select the moved item
            new_index = index - 1
            if has_current:
                new_index += 1
            self.queue_listbox.selection_set(new_index)

    def _move_queue_down(self) -> None:
        """Move selected queue item down."""
        selection = self.queue_listbox.curselection()
        if not selection:
            return

        index = selection[0]
        
        # Adjust for current item being shown at index 0
        has_current = self.queue_manager.get_current() is not None
        if has_current:
            if index == 0:
                # Can't move the downloading item
                return
            index -= 1  # Adjust to actual queue index
        
        if self.queue_manager.move_down(index):
            self._update_queue_display()
            # Re-select the moved item
            new_index = index + 1
            if has_current:
                new_index += 1
            self.queue_listbox.selection_set(new_index)

    def _remove_from_queue(self) -> None:
        """Remove selected item from queue."""
        selection = self.queue_listbox.curselection()
        if not selection:
            return

        index = selection[0]
        
        # Adjust for current item being shown at index 0
        has_current = self.queue_manager.get_current() is not None
        if has_current:
            if index == 0:
                # Can't remove the downloading item from here, use cancel instead
                messagebox.showinfo("Use Cancel", "Use 'Cancel Current' button to cancel the downloading item")
                return
            index -= 1  # Adjust to actual queue index
        
        if self.queue_manager.remove(index):
            self._update_queue_display()

    def _clear_queue(self) -> None:
        """Clear the entire queue."""
        if messagebox.askyesno("Clear Queue", "Clear all items from queue?"):
            self.queue_manager.clear()
            self._update_queue_display()

    def _on_queue_changed(self) -> None:
        """Callback when queue changes."""
        self.logger.debug("Queue changed callback triggered")
        if self.root:
            self.root.after(0, self._update_queue_display)
            # Also force an immediate status update
            self.root.after(0, self._force_status_update)

    def _force_status_update(self) -> None:
        """Force an immediate status bar update (called from callbacks)."""
        if not self.root:
            return

        status = self.queue_manager.get_status()
        
        # Update progress bar if downloading
        if self.client.waiting_for_file == "Book":
            received, total, percentage = self.client.get_download_progress()
            if total > 0:
                # Update progress bar
                self.progress_bar['value'] = percentage
                # Update progress label
                received_mb = received / 1024 / 1024
                total_mb = total / 1024 / 1024
                self.progress_label.config(text=f"{received_mb:.1f} / {total_mb:.1f} MB ({percentage:.1f}%)")
                status += f" | Downloading..."
            else:
                self.progress_bar['value'] = 0
                self.progress_label.config(text="")
                status += " | Downloading..."
        elif self.client.waiting_for_file == "Search":
            self.progress_bar['value'] = 0
            self.progress_label.config(text="")
            status += " | Searching... (click Cancel to stop)"
        elif self.client.waiting_for_file:
            self.progress_bar['value'] = 0
            self.progress_label.config(text="")
            status += " | Working..."
        else:
            # Not downloading - clear progress
            self.progress_bar['value'] = 0
            self.progress_label.config(text="")

        self.status_label.config(text=status)
        self.logger.debug(f"Status updated: {status}")

    def _update_status(self) -> None:
        """Update the status bar (periodic timer)."""
        self._force_status_update()
        if self.root:
            self.root.after(200, self._update_status)
