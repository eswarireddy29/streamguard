"""
Append-only event log producer.

Writes events to numbered segment files. The producer is the ONLY
thing that assigns offsets, which is what guarantees they are unique
and strictly increasing.

Layout on disk:

    data/events/<topic>/
        000000.jsonl      offsets 0 .. 99999
        000001.jsonl      offsets 100000 .. 199999
        000002.jsonl      offsets 200000 ..        (active)
        metadata.json     next offset, segment count
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Iterable

from streamguard.eventlog.event import Event
from streamguard.utils.logging_config import get_logger

log = get_logger(__name__)

# Events per segment file. 100k lines is roughly 40-60 MB of JSON --
# small enough to open in an editor, large enough that we are not
# creating thousands of files.
SEGMENT_SIZE = 100_000

METADATA_FILE = "metadata.json"
SEGMENT_SUFFIX = ".jsonl"


class EventProducer(ABC):
    """
    Abstract producer.

    The rest of the system depends on THIS, never on the file-based
    implementation below. Swapping in Kafka later means writing a new
    subclass, not editing callers.
    """

    @abstractmethod
    def append(self, event: Event) -> int:
        """Write one event. Returns the offset it was given."""

    @abstractmethod
    def append_many(self, events: Iterable[Event]) -> int:
        """Write several events. Returns the count written."""

    @abstractmethod
    def flush(self) -> None:
        """Force buffered writes to disk."""

    @abstractmethod
    def close(self) -> None:
        """Release resources."""

    @property
    @abstractmethod
    def next_offset(self) -> int:
        """The offset the next appended event will receive."""


class FileEventProducer(EventProducer):
    """Writes events to segmented JSON Lines files on local disk."""

    def __init__(
        self,
        root: Path,
        topic: str = "transactions",
        segment_size: int = SEGMENT_SIZE,
        truncate: bool = False,
    ):
        self.topic = topic
        self.segment_size = segment_size
        self.dir = Path(root) / topic
        self.dir.mkdir(parents=True, exist_ok=True)

        if truncate:
            self._truncate()

        self._next_offset = 0
        self._segment_index = 0
        self._handle = None

        self._load_metadata()
        self._open_active_segment()

        log.info(
            "producer_ready",
            topic=topic,
            directory=str(self.dir),
            next_offset=self._next_offset,
            segment=self._segment_index,
        )

    # ---------- Metadata ----------

    @property
    def metadata_path(self) -> Path:
        return self.dir / METADATA_FILE

    def _load_metadata(self) -> None:
        """
        Restore position from a previous run, so the producer can be
        stopped and restarted without losing its place or reusing
        offsets.
        """
        if not self.metadata_path.exists():
            self._next_offset = 0
            self._segment_index = 0
            return

        try:
            data = json.loads(self.metadata_path.read_text(encoding="utf-8"))
            self._next_offset = int(data["next_offset"])
            self._segment_index = int(data["segment_index"])
        except (json.JSONDecodeError, KeyError, ValueError) as exc:
            # Metadata is a cache, not the source of truth. If it is
            # damaged, rebuild it by counting what is actually on disk.
            log.warning("metadata_unreadable_rebuilding", error=str(exc))
            self._rebuild_metadata()

    def _rebuild_metadata(self) -> None:
        """Recover position by reading the segments themselves."""
        segments = sorted(self.dir.glob(f"*{SEGMENT_SUFFIX}"))
        if not segments:
            self._next_offset = 0
            self._segment_index = 0
            return

        last = segments[-1]
        self._segment_index = int(last.stem)

        count = 0
        with last.open("r", encoding="utf-8") as fh:
            for count, _ in enumerate(fh, start=1):
                pass

        self._next_offset = self._segment_index * self.segment_size + count
        log.info("metadata_rebuilt", next_offset=self._next_offset,
                 segment=self._segment_index)

    def _save_metadata(self) -> None:
        payload = {
            "topic": self.topic,
            "next_offset": self._next_offset,
            "segment_index": self._segment_index,
            "segment_size": self.segment_size,
        }
        self.metadata_path.write_text(
            json.dumps(payload, indent=2), encoding="utf-8"
        )

    def _truncate(self) -> None:
        """Delete every segment and start the log from zero."""
        for path in self.dir.glob(f"*{SEGMENT_SUFFIX}"):
            path.unlink()
        if self.metadata_path.exists():
            self.metadata_path.unlink()
        log.warning("log_truncated", topic=self.topic)

    # ---------- Segments ----------

    def _segment_path(self, index: int) -> Path:
        # Zero-padded so alphabetical sorting matches numerical order.
        # Without padding, "10" sorts before "2".
        return self.dir / f"{index:06d}{SEGMENT_SUFFIX}"

    def _open_active_segment(self) -> None:
        """Open the current segment for appending."""
        if self._handle is not None:
            self._handle.close()
        # "a" = append mode. The file is never truncated, and every
        # write goes to the end. This is what makes the log append-only
        # at the filesystem level, not just by convention.
        self._handle = self._segment_path(self._segment_index).open(
            "a", encoding="utf-8"
        )

    def _roll_segment_if_needed(self) -> None:
        """Start a new segment once the current one is full."""
        expected_index = self._next_offset // self.segment_size
        if expected_index != self._segment_index:
            self._segment_index = expected_index
            self._open_active_segment()
            log.info("segment_rolled", segment=self._segment_index,
                     offset=self._next_offset)

    # ---------- Writing ----------

    def append(self, event: Event) -> int:
        offset = self._next_offset
        self._handle.write(event.with_offset(offset).to_json_line())
        self._next_offset += 1
        self._roll_segment_if_needed()
        return offset

    def append_many(self, events: Iterable[Event]) -> int:
        """
        Write many events, building one string and writing once.

        One write call for 5,000 events instead of 5,000 calls is the
        difference between seconds and minutes. The trade-off is memory:
        we hold the batch as a string, so callers should pass
        reasonable batches, not the whole log.
        """
        lines: list[str] = []
        start = self._next_offset

        for event in events:
            lines.append(event.with_offset(self._next_offset).to_json_line())
            self._next_offset += 1

            # Respect segment boundaries mid-batch
            if self._next_offset % self.segment_size == 0:
                self._handle.write("".join(lines))
                lines.clear()
                self._roll_segment_if_needed()

        if lines:
            self._handle.write("".join(lines))

        self._roll_segment_if_needed()
        return self._next_offset - start

    def flush(self) -> None:
        """
        Push buffered data to the operating system and save metadata.

        Python buffers writes for speed. Until flush, recent events
        exist only in memory and would be lost on a crash.
        """
        if self._handle is not None:
            self._handle.flush()
        self._save_metadata()

    def close(self) -> None:
        self.flush()
        if self._handle is not None:
            self._handle.close()
            self._handle = None
        log.info("producer_closed", topic=self.topic,
                 total_events=self._next_offset)

    @property
    def next_offset(self) -> int:
        return self._next_offset

    # ---------- Context manager ----------

    def __enter__(self) -> FileEventProducer:
        return self

    def __exit__(self, *exc_info) -> None:
        # Runs even if an exception occurred, so the log is always
        # flushed and the file handle always released.
        self.close()