"""File processing utilities for IRC Ebook Fetcher."""

import sys
import traceback
import zipfile
from pathlib import Path
from typing import Dict, Set

from logger import Logger


class FileProcessor:
    """Processes search result files from IRC."""

    def __init__(self, debug: bool = False):
        """
        Initialize file processor.

        Args:
            debug: Whether to enable debug logging
        """
        self.logger = Logger("Processor", debug)

    def process_search_results(self, filename: Path, file_types: Set[str] = None) -> Dict[str, Set[str]]:
        """
        Process a zip file containing IRC ebook search results.

        Args:
            filename: Path to the zip file to process
            file_types: Set of file extensions to include (e.g., {'epub', 'mobi', 'pdf'})

        Returns:
            Dictionary mapping filenames to sets of users who have them

        Raises:
            zipfile.BadZipFile: If the file is not a valid zip
            FileNotFoundError: If the file doesn't exist
        """
        try:
            return self._extract_and_parse(filename, file_types)
        except zipfile.BadZipFile:
            self.logger.error(f"Invalid zip file: {filename}")
            return {}
        except FileNotFoundError:
            self.logger.error(f"File not found: {filename}")
            return {}
        except Exception as e:
            self.logger.error(f"Unexpected error processing file: {e}")
            traceback.print_exc()
            return {}

    def _extract_and_parse(self, filename: Path, file_types: Set[str] = None) -> Dict[str, Set[str]]:
        """
        Extract and parse the search results file.

        Args:
            filename: Path to the zip file
            file_types: Set of file extensions to include

        Returns:
            Dictionary mapping filenames to sets of users
        """
        # Extract zip file
        newfile = filename.with_suffix("")
        self.logger.info("Unzipping file")

        with zipfile.ZipFile(filename) as zf:
            if len(zf.namelist()) > 1:
                self.logger.error("File format has changed, more than one file in search zip")
                return {}

            txtfile = zf.namelist()[0]
            with open(newfile, "wb") as f:
                f.write(zf.read(txtfile))

        # Parse the extracted file
        self.logger.info("Parsing file")
        available = self._parse_results_file(newfile, file_types)
        self.logger.info(f"Got {len(available)} unique options")

        return available

    def _parse_results_file(self, filepath: Path, file_types: Set[str] = None) -> Dict[str, Set[str]]:
        """
        Parse the extracted results file.

        Args:
            filepath: Path to the extracted text file
            file_types: Set of file extensions to include (e.g., {'epub', 'mobi', 'pdf'}). 
                       If None, includes all ebook types.

        Returns:
            Dictionary mapping filenames to sets of users
        """
        # Default to common ebook formats if not specified
        if file_types is None:
            file_types = {'epub', 'mobi', 'pdf', 'azw3', 'azw', 'cbz', 'cbr'}
        
        available: Dict[str, Set[str]] = {}

        with open(filepath, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                if not line.startswith("!"):
                    continue
                
                # Check if line contains any of the desired file types
                line_lower = line.lower()
                if not any(f".{ext}" in line_lower for ext in file_types):
                    continue

                # Parse line format: !user filename::info
                try:
                    user, filename = self._parse_result_line(line)
                    if filename:
                        if filename not in available:
                            available[filename] = set()
                        available[filename].add(user)
                except Exception as e:
                    self.logger.debug(f"Failed to parse line: {line.strip()} - {e}")
                    continue

        return available

    def _parse_result_line(self, line: str) -> tuple[str, str]:
        """
        Parse a single result line.

        Args:
            line: Line from the results file

        Returns:
            Tuple of (user, filename)
        """
        i1 = line.find(" ")
        i2 = line.find("::")
        if i2 == -1:
            i2 = line.find("\r")
            if i2 == -1:
                i2 = line.find("\n")

        user = line[:i1].replace("!", "").strip()
        filename = line[i1:i2].strip()

        return user, filename
