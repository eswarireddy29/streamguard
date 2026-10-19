"""
The event envelope.

Every item on the log is an Event: a small wrapper carrying metadata
plus a payload. The wrapper is deliberately generic so the same log
can later carry decisions, analyst verdicts or audit records — not
just transactions.

Events are IMMUTABLE. Once written, an event is never edited. That is
what makes the log trustworthy as a record of what happened.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class EventType(str, Enum):
    """What kind of thing happened."""
    TRANSACTION = "transaction"
    DECISION = "decision"
    ANALYST_VERDICT = "analyst_verdict"


# Bump this when the event structure changes in a way that older
# consumers could not understand. A consumer can then check the
# version and refuse rather than silently misreading fields.
SCHEMA_VERSION = 1


@dataclass(frozen=True)
class Event:
    """
    One item on the log.

    Attributes:
        offset       : position in the log. Assigned by the producer,
                       never by the caller. -1 means "not yet written".
        event_type   : what kind of event this is
        occurred_at  : when the thing happened in the real world
        produced_at  : when it was written to the log
        key          : partition/grouping key (we use card_ref), so
                       related events can be routed together later
        payload      : the actual data
        schema_version: structure version, for forward compatibility
    """

    event_type: str
    occurred_at: datetime
    key: str
    payload: dict[str, Any]
    offset: int = -1
    produced_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    schema_version: int = SCHEMA_VERSION

    # ---------- Serialisation ----------

    def to_json_line(self) -> str:
        """
        Render as a single line of JSON, newline terminated.

        One event per line is what makes the file streamable: a reader
        can process one line and discard it, so memory never depends
        on file size.
        """
        record = {
            "offset": self.offset,
            "event_type": self.event_type,
            "occurred_at": self.occurred_at.isoformat(),
            "produced_at": self.produced_at.isoformat(),
            "key": self.key,
            "schema_version": self.schema_version,
            "payload": self.payload,
        }
        # separators removes spaces: smaller files, faster parsing.
        # ensure_ascii=False keeps non-English text readable.
        return json.dumps(record, separators=(",", ":"),
                          ensure_ascii=False, default=str) + "\n"

    @classmethod
    def from_json_line(cls, line: str) -> Event:
        """Parse one line back into an Event."""
        record = json.loads(line)
        return cls(
            offset=record["offset"],
            event_type=record["event_type"],
            occurred_at=datetime.fromisoformat(record["occurred_at"]),
            produced_at=datetime.fromisoformat(record["produced_at"]),
            key=record["key"],
            payload=record["payload"],
            schema_version=record.get("schema_version", 1),
        )

    def with_offset(self, offset: int) -> Event:
        """
        Return a copy carrying the given offset.

        A copy, not a mutation: the dataclass is frozen, and that is
        deliberate. An event you cannot accidentally modify is an
        event you can trust.
        """
        return Event(
            event_type=self.event_type,
            occurred_at=self.occurred_at,
            key=self.key,
            payload=self.payload,
            offset=offset,
            produced_at=self.produced_at,
            schema_version=self.schema_version,
        )


def transaction_event(txn: dict[str, Any]) -> Event:
    """
    Build a TRANSACTION event from a transaction dict.

    The key is card_ref. Keys matter because related events should
    stay together: in a partitioned system, every event for one card
    lands on the same partition, so a consumer sees that card's
    history in order. Our single-partition log preserves global order
    anyway, but setting the key now means the Kafka swap needs no
    change here.
    """
    occurred = txn["occurred_at"]
    if isinstance(occurred, str):
        occurred = datetime.fromisoformat(occurred)

    return Event(
        event_type=EventType.TRANSACTION.value,
        occurred_at=occurred,
        key=str(txn["card_ref"]),
        payload=txn,
    )