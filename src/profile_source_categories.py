"""Inventory source categorical values needed to maintain reference mappings."""

from __future__ import annotations

import csv
import gzip
import json
from collections import Counter
from pathlib import Path


CATEGORY_COLUMNS = {
    "players": ("position", "sub_position"),
    "competitions": ("type", "sub_type"),
    "games": ("competition_type",),
    "transfers": ("transfer_fee",),
}


def main() -> None:
    output: dict[str, dict[str, dict[str, int]]] = {}
    for table, columns in CATEGORY_COLUMNS.items():
        counts = {column: Counter() for column in columns}
        path = Path("data/raw") / f"{table}.csv.gz"
        with gzip.open(path, "rt", encoding="utf-8-sig", newline="") as source:
            for row in csv.DictReader(source):
                for column in columns:
                    counts[column][row[column]] += 1
        output[table] = {
            column: dict(sorted(counter.items(), key=lambda item: (-item[1], item[0])))
            for column, counter in counts.items()
        }

    destination = Path("reports/data_audit/source_categories.json")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(output, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(f"Category inventory written to {destination}")


if __name__ == "__main__":
    main()
