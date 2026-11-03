"""LanceDB metadata index with optional vector column for embedding-based retrieval.

Schema
------
  id        : string   — UUID hex of the library entry
  metadata  : string   — full entry JSON
  vector    : fixed_size_list<float32>[768] — nomic-embed-text embedding, or zeros if unavailable

Migration
---------
On first open, if the table exists but has no ``vector`` column the index
migrates by adding the column (filled with zero vectors).  New entries always
attempt to embed; if the embedding client is unavailable or returns [] the
vector is stored as zeros and keyword fallback remains available.

Vector search
-------------
``search(query_vector, limit)`` returns the ``limit`` nearest neighbours by
cosine similarity.  If the query vector is all-zeros (embedding unavailable)
it falls through and returns an empty list so the caller uses keyword ranking.
"""
from __future__ import annotations

import json
import logging
import re
import lancedb
import pyarrow as pa
from pathlib import Path
from .embeddings import EmbeddingClient

log = logging.getLogger(__name__)

_DIM = 768
_ZERO_VECTOR = [0.0] * _DIM


class LibraryIndex:
    def __init__(self, root: Path, embedder: "EmbeddingClient | None" = None):
        self._pa = pa
        self.path = root / "index.lancedb"
        self.embedder = embedder
        self.connection = lancedb.connect(str(self.path))

        schema = pa.schema([
            pa.field("id", pa.string()),
            pa.field("metadata", pa.string()),
            pa.field("vector", pa.list_(pa.float32(), _DIM)),
        ])

        if "entries" in self.connection.list_tables():
            self.table = self.connection.open_table("entries")
            self._migrate_if_needed(schema)
        else:
            self.table = self.connection.create_table("entries", schema=schema)

    # ------------------------------------------------------------------
    # Schema migration
    # ------------------------------------------------------------------

    def _migrate_if_needed(self, target_schema) -> None:
        """Add the vector column to tables created before this version."""
        existing_names = {field.name for field in self.table.schema}
        if "vector" in existing_names:
            return
        log.info("LibraryIndex: migrating existing table to add vector column")
        rows = self.table.to_arrow().to_pylist()
        self.connection.drop_table("entries")
        self.table = self.connection.create_table("entries", schema=target_schema)
        if rows:
            migrated = [
                {
                    "id": row["id"],
                    "metadata": row["metadata"],
                    "vector": self._embed_row(row["metadata"]),
                }
                for row in rows
            ]
            self.table.add(migrated)
            log.info("LibraryIndex: migrated %d entries", len(migrated))

    def _embed_row(self, metadata_json: str) -> list[float]:
        """Embed a metadata JSON string; return zero vector on any failure."""
        if self.embedder is None:
            return _ZERO_VECTOR
        try:
            text = EmbeddingClient.entry_text(json.loads(metadata_json))
            vector = self.embedder.embed(text)
            return vector if len(vector) == _DIM else _ZERO_VECTOR
        except Exception as exc:
            log.warning("_embed_row failed: %s", exc)
            return _ZERO_VECTOR

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    def add(self, metadata: dict) -> None:
        if self.get(metadata["id"]) is not None:
            raise ValueError("Library entry already exists")
        metadata_json = json.dumps(metadata, allow_nan=False)
        vector = self._embed_row(metadata_json)
        if vector == _ZERO_VECTOR:
            log.debug("LibraryIndex.add: no embedding for entry %s — stored zero vector", metadata["id"])
        self.table.add([{
            "id": metadata["id"],
            "metadata": metadata_json,
            "vector": vector,
        }])

    def list_entries(self) -> list[dict]:
        rows = self.table.to_arrow().to_pylist()
        entries = [json.loads(row["metadata"]) for row in rows]
        return sorted(entries, key=lambda e: (e["created_at"], e["id"]), reverse=True)

    def get(self, entry_id: str) -> dict | None:
        return next((e for e in self.list_entries() if e["id"] == entry_id), None)

    def remove(self, entry_id: str) -> None:
        if not re.fullmatch(r"[0-9a-f]{32}", entry_id):
            raise ValueError("Invalid library entry identifier")
        self.table.delete(f"id = '{entry_id}'")

    # ------------------------------------------------------------------
    # Vector search
    # ------------------------------------------------------------------

    def search(self, query_vector: list[float], limit: int = 10) -> list[dict]:
        """Return up to *limit* entries ordered by cosine similarity.

        Returns [] if:
        - the query vector is all-zeros (embedding unavailable)
        - the table is empty
        - any LanceDB error occurs (fallback to keyword ranking)
        """
        if not query_vector or query_vector == _ZERO_VECTOR:
            return []
        try:
            results = (
                self.table.search(query_vector, vector_column_name="vector")
                .metric("cosine")
                .limit(limit)
                .to_arrow()
                .to_pylist()
            )
            entries = []
            for row in results:
                try:
                    entry = json.loads(row["metadata"])
                    # Attach similarity score (1 - cosine distance) for hybrid ranking.
                    entry["_vector_score"] = float(1.0 - row.get("_distance", 1.0))
                    entries.append(entry)
                except Exception:
                    pass
            return entries
        except Exception as exc:
            log.warning("LibraryIndex.search failed: %s — falling back to keyword ranking", exc)
            return []
