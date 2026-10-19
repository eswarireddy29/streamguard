"""
Event log consumer with committed offsets and replay.

A consumer belongs to a GROUP. Each group keeps its own offset file,
so several consumers can read the same log independently and at
their own pace.

Delivery is AT-LEAST-ONCE: the offset is committed after processing,
so a crash mid-batch causes reprocessing, never loss. Consumers must
therefore be idempotent -- processing the same event twice must be
harmless.

Offsets live in:
    data/events/<topic>/offsets/<group>.json
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from collections.abc import Iterator
from pathlib import Path

from streamguard.eventlog.event import Event
from streamguard.eventlog.producer import METADATA_FILE, SEGMENT_SUFFIX
from streamguard.utils.logging_config import get_logger

log = get_logger(__name__)

OFFSETS_DIR = "offsets"


class EventConsumer(ABC):
    """
    Abstract consumer.

    Callers depend on this, never on the file implementation, so a
    Kafka consumer can be dropped in later without touching them.
    """

    @abstractmethod
    def poll(self, max_events: int) -> list[Event]:
        """Read up to max_events from the current position."""

    @abstractmethod
    def commit(self, offset: int | None = None) -> None:
        """Persist progress."""

    @abstractmethod
    def seek(self, offset: int) -> None:
        """Move the read position."""

    @property
    @abstractmethod
    def position(self) -> int:
        """Offset of the next event to be read."""


class FileEventConsumer(EventConsumer):
    """Reads from segmented JSON Lines files written by FileEventProducer."""

    def __init__(
        self,
        root: Path,
        topic: str = "transactions",
        group: str = "default",
        from_beginning: bool = False,
    ):
        self.topic = topic
        self.group = group
        self.dir = Path(root) / topic
        self.offsets_dir = self.dir / OFFSETS_DIR
        self.offsets_dir.mkdir(parents=True, exist_ok=True)

        self.segment_size = self._read_segment_size()
        self._position = 0 if from_beginning else self._load_offset()
        self._uncommitted = self._position

        log.info(
            "consumer_ready",
            topic=topic,
            group=group,
            position=self._position,
            log_end=self.log_end_offset(),
        )

    # ---------- Configuration ----------

    def _read_segment_size(self) -> int:
        """
        Read segment size from the producer's metadata.

        The consumer must agree with the producer about segment size,
        or it would look for offset 150,000 in the wrong file.
        """
        meta_path = self.dir / METADATA_FILE
        if meta_path.exists():
            try:
                data = json.loads(meta_path.read_text(encoding="utf-8"))
                return int(data.get("segment_size", 100_000))
            except (json.JSONDecodeError, ValueError):
                log.warning("consumer_metadata_unreadable_using_default")
        return 100_000

    # ---------- Offset persistence ----------

    @property
    def offset_path(self) -> Path:
        return self.offsets_dir / f"{self.group}.json"

    def _load_offset(self) -> int:
        if not self.offset_path.exists():
            return 0
        try:
            data = json.loads(self.offset_path.read_text(encoding="utf-8"))
            return int(data["position"])
        except (json.JSONDecodeError, KeyError, ValueError) as exc:
            log.warning("offset_file_unreadable_restarting",
                        group=self.group, error=str(exc))
            return 0

    def commit(self, offset: int | None = None) -> None:
        """
        Persist progress.

        Called AFTER processing, which is what makes delivery
        at-least-once rather than at-most-once.
        """
        target = self._uncommitted if offset is None else offset
        payload = {
            "topic": self.topic,
            "group": self.group,
            "position": target,
        }
        self.offset_path.write_text(
            json.dumps(payload, indent=2), encoding="utf-8"
        )
        self._position = target

    # ---------- Position ----------

    def seek(self, offset: int) -> None:
        """Move to an arbitrary offset. seek(0) replays from the start."""
        self._position = max(0, offset)
        self._uncommitted = self._position
        log.info("consumer_seek", group=self.group, position=self._position)

    def seek_to_beginning(self) -> None:
        self.seek(0)

    def log_end_offset(self) -> int:
        """
        The offset just past the last written event.

        Read from producer metadata when available, otherwise counted
        from the segments themselves.
        """
        meta_path = self.dir / METADATA_FILE
        if meta_path.exists():
            try:
                data = json.loads(meta_path.read_text(encoding="utf-8"))
                return int(data["next_offset"])
            except (json.JSONDecodeError, KeyError, ValueError):
                pass

        segments = sorted(self.dir.glob(f"*{SEGMENT_SUFFIX}"))
        if not segments:
            return 0

        last = segments[-1]
        index = int(last.stem)
        count = sum(1 for _ in last.open("r", encoding="utf-8"))
        return index * self.segment_size + count

    def lag(self) -> int:
        """
        How many events remain unread.

        In production this is THE health metric for a streaming
        consumer: rising lag means you cannot keep up with the stream.
        """
        return max(0, self.log_end_offset() - self._position)

    @property
    def position(self) -> int:
        return self._position

    # ---------- Reading ----------

    def _segment_path(self, index: int) -> Path:
        return self.dir / f"{index:06d}{SEGMENT_SUFFIX}"

    def poll(self, max_events: int = 1000) -> list[Event]:
        """
        Read up to max_events starting at the current position.

        Returns fewer than requested (possibly none) when the end of
        the log is reached. Does NOT commit -- the caller commits once
        processing has succeeded.
        """
        events: list[Event] = []
        offset = self._uncommitted
        end = self.log_end_offset()

        while len(events) < max_events and offset < end:
            segment_index = offset // self.segment_size
            line_in_segment = offset % self.segment_size
            path = self._segment_path(segment_index)

            if not path.exists():
                log.warning("segment_missing", segment=segment_index,
                            offset=offset)
                break

            with path.open("r", encoding="utf-8") as fh:
                # Skip to our line without loading the whole file.
                # enumerate avoids holding 100,000 lines in memory.
                for i, line in enumerate(fh):
                    if i < line_in_segment:
                        continue
                    if len(events) >= max_events:
                        break
                    line = line.strip()
                    if line:
                        events.append(Event.from_json_line(line))
                        offset += 1

            # If we exhausted this segment without filling the batch,
            # the loop continues into the next one.
            if offset % self.segment_size == 0 and len(events) < max_events:
                continue

        self._uncommitted = offset
        return events

    def stream(
        self, batch_size: int = 1000, max_events: int | None = None
    ) -> Iterator[Event]:
        """
        Yield events one at a time until the log is exhausted.

        Reads in batches internally but hands out single events, so
        the caller writes a simple loop while memory stays flat.
        Commits are the CALLER's responsibility.
        """
        delivered = 0
        while True:
            if max_events is not None:
                remaining = max_events - delivered
                if remaining <= 0:
                    return
                batch = self.poll(min(batch_size, remaining))
            else:
                batch = self.poll(batch_size)

            if not batch:
                return

            for event in batch:
                yield event
                delivered += 1