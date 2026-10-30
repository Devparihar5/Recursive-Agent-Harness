"""LanceDB metadata index; complete harness artifacts remain on the filesystem."""
import json
import re
from pathlib import Path


class LibraryIndex:
    def __init__(self, root: Path):
        import lancedb
        import pyarrow as pa

        self.path = root / "index.lancedb"
        self.connection = lancedb.connect(str(self.path))
        self.table = self.connection.create_table(
            "entries",
            schema=pa.schema([pa.field("id", pa.string()), pa.field("metadata", pa.string())]),
            exist_ok=True,
        )

    def add(self, metadata: dict):
        if self.get(metadata["id"]) is not None:
            raise ValueError("Library entry already exists")
        self.table.add([{"id": metadata["id"], "metadata": json.dumps(metadata, allow_nan=False)}])

    def list_entries(self) -> list[dict]:
        entries = [json.loads(row["metadata"]) for row in self.table.to_arrow().to_pylist()]
        return sorted(entries, key=lambda entry: (entry["created_at"], entry["id"]), reverse=True)

    def get(self, entry_id: str) -> dict | None:
        return next((entry for entry in self.list_entries() if entry["id"] == entry_id), None)

    def remove(self, entry_id: str) -> None:
        if not re.fullmatch(r"[0-9a-f]{32}", entry_id):
            raise ValueError("Invalid library entry identifier")
        self.table.delete(f"id = '{entry_id}'")
