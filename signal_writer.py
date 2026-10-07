"""
Signal Writer - Writes parsed trade signals to a file for MT5 EA consumption.

Writes in pipe-delimited format with atomic file operations to prevent
the MT5 EA from reading a partially written file.

File format (one signal per line):
    id|timestamp|symbol|side|entry_type|entry_min|entry_max|sl|sl_type|tps|tp_type|move_to_be|confidence|raw_text
"""

import os
import tempfile
import logging
import time
from typing import List
from parser import TradeSignal

logger = logging.getLogger(__name__)


class SignalWriter:
    """Writes trade signals to a file atomically with rollback safety."""

    def __init__(self, output_path: str, max_signals: int = 100,
                 temp_suffix: str = ".tmp", encoding: str = "utf-8",
                 max_retries: int = 3, retry_delay: float = 0.5,
                 processed_path: str = None):
        self.output_path = output_path
        self.max_signals = max_signals
        self.temp_suffix = temp_suffix
        self.encoding = encoding
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.processed_path = processed_path or os.path.splitext(output_path)[0] + ".processed.txt"
        self._processed_ids = set()
        self._existing_signals = []

        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        os.makedirs(os.path.dirname(self.processed_path) or ".", exist_ok=True)
        self._load_existing()

    def _load_existing(self):
        """Load existing signals from the live queue and processed archive for dedup tracking."""
        if os.path.exists(self.processed_path):
            try:
                with open(self.processed_path, "r", encoding=self.encoding) as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        parts = line.split("|")
                        if len(parts) >= 1 and parts[0]:
                            self._processed_ids.add(parts[0])
            except Exception as e:
                logger.warning(f"Could not load processed archive: {e}")

        if not os.path.exists(self.output_path):
            return
        try:
            with open(self.output_path, "r", encoding=self.encoding) as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    sig = TradeSignal.from_pipe_string(line)
                    if sig:
                        self._existing_signals.append(sig)
                        self._processed_ids.add(sig.signal_id)
        except Exception as e:
            logger.warning(f"Could not load existing signals: {e}")

    def is_duplicate(self, signal: TradeSignal) -> bool:
        """Check if a signal has already been written."""
        return signal.signal_id in self._processed_ids

    def write_signal(self, signal: TradeSignal) -> bool:
        """
        Write a single signal to the file atomically.
        Only marks as processed after successful write.

        Returns:
            True if written, False if duplicate or error.
        """
        if self.is_duplicate(signal):
            logger.debug(f"Duplicate signal skipped: {signal.signal_id}")
            return False

        # Add to pending list (not yet marked as processed)
        self._existing_signals.append(signal)

        # Trim to max BEFORE writing
        if len(self._existing_signals) > self.max_signals:
            self._existing_signals = self._existing_signals[-self.max_signals:]

        # Attempt atomic write with retries
        if self._flush_with_retries():
            # Only mark as processed after successful write
            self._processed_ids.add(signal.signal_id)
            return True
        else:
            # Rollback: remove the signal from the list since write failed
            if signal in self._existing_signals:
                self._existing_signals.remove(signal)
            logger.error(f"Failed to write signal {signal.signal_id} after retries. Rolled back.")
            return False

    def mark_signal_processed(self, signal_id: str) -> bool:
        """Archive a processed signal ID without deleting the active queue file in-place.

        This avoids a race where the monitor is writing a new signal while the EA is
        deleting a stale file. Instead, we atomically rewrite the queue to remove the
        entries belonging to this signal_id and append the ID to a processed archive.
        """
        if not signal_id or not signal_id.strip():
            return False

        processed_id = signal_id.strip()
        if processed_id in self._processed_ids:
            return True

        remaining = []
        for sig in self._existing_signals:
            if sig.signal_id != processed_id:
                remaining.append(sig)

        if len(remaining) != len(self._existing_signals):
            self._existing_signals = remaining
            if self._flush_with_retries():
                self._processed_ids.add(processed_id)
                self._archive_processed_id(processed_id)
                return True

        self._processed_ids.add(processed_id)
        self._archive_processed_id(processed_id)
        return True

    def _archive_processed_id(self, signal_id: str) -> None:
        """Append a processed signal ID to an archive file atomically."""
        if not signal_id or not signal_id.strip():
            return

        dir_path = os.path.dirname(self.processed_path)
        if dir_path:
            os.makedirs(dir_path, exist_ok=True)

        tmp_path = None
        try:
            fd, tmp_path = tempfile.mkstemp(
                dir=dir_path or ".",
                suffix=self.temp_suffix,
                prefix="processed_",
            )
            with os.fdopen(fd, "w", encoding=self.encoding) as f:
                if os.path.exists(self.processed_path):
                    with open(self.processed_path, "r", encoding=self.encoding) as existing:
                        for line in existing:
                            if line.strip():
                                f.write(line)
                f.write(f"{signal_id}\n")
            os.replace(tmp_path, self.processed_path)
        except Exception as e:
            logger.warning(f"Could not archive processed signal {signal_id}: {e}")
            if tmp_path and os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except Exception:
                    pass

    def write_signals(self, signals: List[TradeSignal]) -> int:
        """Write multiple signals. Returns count of newly written signals."""
        new_count = 0
        new_signals = []
        for sig in signals:
            if not self.is_duplicate(sig):
                new_signals.append(sig)
                self._existing_signals.append(sig)
                new_count += 1

        # Trim
        if len(self._existing_signals) > self.max_signals:
            self._existing_signals = self._existing_signals[-self.max_signals:]

        if new_count > 0:
            if self._flush_with_retries():
                # Mark all new signals as processed only after successful write
                for sig in new_signals:
                    self._processed_ids.add(sig.signal_id)
            else:
                # Rollback: remove all new signals
                for sig in new_signals:
                    if sig in self._existing_signals:
                        self._existing_signals.remove(sig)
                logger.error(f"Failed to write {new_count} signals after retries. Rolled back.")
                return 0

        return new_count

    def _flush_with_retries(self) -> bool:
        """Attempt to flush with retries. Returns True on success."""
        for attempt in range(self.max_retries):
            if self._flush():
                return True
            if attempt < self.max_retries - 1:
                logger.warning(f"Write attempt {attempt+1} failed. Retrying in {self.retry_delay}s...")
                time.sleep(self.retry_delay)
        return False

    def _flush(self) -> bool:
        """Write all signals to file atomically (write to temp, then rename)."""
        dir_path = os.path.dirname(self.output_path)
        tmp_path = None
        try:
            fd, tmp_path = tempfile.mkstemp(
                dir=dir_path,
                suffix=self.temp_suffix,
                prefix="signals_",
            )
            with os.fdopen(fd, "w", encoding=self.encoding) as f:
                for sig in self._existing_signals:
                    f.write(sig.to_pipe_string() + "\n")

            # Atomic rename (os.replace works on Windows even if target exists)
            os.replace(tmp_path, self.output_path)

            logger.info(f"Signal file updated: {self.output_path} ({len(self._existing_signals)} signals)")
            return True

        except PermissionError as e:
            # MT5 might be reading the file - this is expected, will retry
            logger.warning(f"Permission error writing signal file (MT5 may be reading): {e}")
            if tmp_path and os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except:
                    pass
            return False
        except Exception as e:
            logger.error(f"Failed to write signal file: {e}")
            if tmp_path and os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except:
                    pass
            return False

    def get_pending_signals(self, last_read_id: str = "") -> List[TradeSignal]:
        """Get signals that haven't been processed by the EA yet."""
        if not last_read_id:
            return list(self._existing_signals)

        result = []
        found = False
        for sig in self._existing_signals:
            if found:
                result.append(sig)
            if sig.signal_id == last_read_id:
                found = True
        return result

    def clear(self):
        """Clear all signals while leaving an empty file behind for the consumer."""
        self._existing_signals = []
        self._processed_ids = set()
        try:
            dir_path = os.path.dirname(self.output_path)
            if dir_path:
                os.makedirs(dir_path, exist_ok=True)
            with open(self.output_path, "w", encoding=self.encoding) as f:
                f.write("")
        except Exception as e:
            logger.warning(f"Could not clear signal file: {e}")
