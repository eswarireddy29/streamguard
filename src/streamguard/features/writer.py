"""
Buffered Parquet writer for feature rows.

Writes in chunks so memory stays flat: 791,112 rows x 49 features
held as Python objects would be several gigabytes. We accumulate
50,000 rows, write them, and discard.

Parquet rather than CSV: columnar, compressed, and typed. Roughly a
tenth the size, far faster to read, and DuckDB can query it without
loading it into memory -- which matters on 8 GB.
"""

from __future__ import annotations

from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from streamguard.features.computer import FEATURE_NAMES
from streamguard.utils.logging_config import get_logger

log = get_logger(__name__)

CHUNK_SIZE = 50_000

# Columns carried alongside the features. Identifiers for joining
# back to the database, and labels for training.
#
# NOTE: is_fraud and fraud_type are LABELS. They are written to the
# file because training needs them. Nothing in the feature path ever
# reads them -- enforced by a test in Task 11.
ID_COLUMNS = [
    "transaction_ref",
    "occurred_at",
    "card_ref",
    "customer_ref",
    "merchant_ref",
    "event_offset",
]
LABEL_COLUMNS = ["is_fraud", "fraud_type"]


def build_schema() -> pa.Schema:
    """
    Explicit Arrow schema.

    Declaring types rather than letting Arrow infer them prevents a
    nasty class of bug: if the first chunk happens to contain only
    integers in a column, inference picks int64, and a later chunk
    with a float then fails to append.
    """
    fields = [
        pa.field("transaction_ref", pa.string()),
        pa.field("occurred_at", pa.timestamp("us", tz="Asia/Kolkata")),
        pa.field("card_ref", pa.string()),
        pa.field("customer_ref", pa.string()),
        pa.field("merchant_ref", pa.string()),
        pa.field("event_offset", pa.int64()),
    ]
    fields += [pa.field(name, pa.float64()) for name in FEATURE_NAMES]
    fields += [
        pa.field("is_fraud", pa.bool_()),
        pa.field("fraud_type", pa.string()),
    ]
    return pa.schema(fields)


class FeatureWriter:
    """Accumulates rows and flushes them to Parquet in chunks."""

    def __init__(self, path: Path, chunk_size: int = CHUNK_SIZE):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.chunk_size = chunk_size
        self.schema = build_schema()

        self._buffer: list[dict] = []
        self._writer: pq.ParquetWriter | None = None
        self.rows_written = 0
        self.chunks_written = 0

    def _ensure_writer(self) -> None:
        if self._writer is None:
            # snappy: fast compression, modest ratio. zstd compresses
            # better but costs CPU, and we are CPU-bound here, not
            # disk-bound.
            self._writer = pq.ParquetWriter(
                self.path, self.schema, compression="snappy"
            )

    def add(self, row: dict) -> None:
        self._buffer.append(row)
        if len(self._buffer) >= self.chunk_size:
            self.flush()

    def flush(self) -> None:
        """Write the buffer to disk and clear it."""
        if not self._buffer:
            return

        self._ensure_writer()

        # Build column-wise. Arrow is columnar, so assembling columns
        # directly avoids a row-to-column transposition.
        columns = {}
        for field in self.schema:
            columns[field.name] = [row.get(field.name) for row in self._buffer]

        table = pa.Table.from_pydict(columns, schema=self.schema)
        self._writer.write_table(table)

        self.rows_written += len(self._buffer)
        self.chunks_written += 1
        self._buffer.clear()

        log.info("feature_chunk_written",
                 chunk=self.chunks_written, total_rows=self.rows_written)

    def close(self) -> None:
        self.flush()
        if self._writer is not None:
            self._writer.close()
            self._writer = None
        log.info("feature_file_closed", path=str(self.path),
                 rows=self.rows_written, chunks=self.chunks_written)

    def __enter__(self) -> FeatureWriter:
        return self

    def __exit__(self, *exc_info) -> None:
        self.close()