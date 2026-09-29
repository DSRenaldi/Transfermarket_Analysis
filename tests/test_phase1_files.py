from __future__ import annotations

import csv
import gzip
import hashlib
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "data" / "raw"
CONFIG_DIR = ROOT / "config"
REPORT_DIR = ROOT / "reports" / "data_audit"
EXPECTED_TABLES = {
    "competitions",
    "clubs",
    "players",
    "games",
    "appearances",
    "player_valuations",
    "club_games",
    "game_events",
    "game_lineups",
    "transfers",
    "countries",
    "national_teams",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class Phase1FilesTest(unittest.TestCase):
    def test_manifest_matches_downloaded_files(self) -> None:
        manifest = json.loads(
            (REPORT_DIR / "source_manifest.json").read_text(encoding="utf-8")
        )
        self.assertEqual(manifest["file_count"], 12)
        self.assertEqual(
            {item["table"] for item in manifest["files"]}, EXPECTED_TABLES
        )
        for item in manifest["files"]:
            path = RAW_DIR / item["filename"]
            self.assertTrue(path.exists(), path)
            self.assertEqual(path.stat().st_size, item["bytes"])
            self.assertEqual(sha256(path), item["sha256"])

    def test_all_source_headers_are_nonempty_and_unique(self) -> None:
        for table in EXPECTED_TABLES:
            with gzip.open(
                RAW_DIR / f"{table}.csv.gz",
                "rt",
                encoding="utf-8-sig",
                newline="",
            ) as source:
                headers = next(csv.reader(source))
            self.assertTrue(headers, table)
            self.assertTrue(all(headers), table)
            self.assertEqual(len(headers), len(set(headers)), table)

    def test_position_mapping_covers_observed_pairs(self) -> None:
        with (CONFIG_DIR / "position_mapping.csv").open(
            encoding="utf-8", newline=""
        ) as source:
            mapped = {
                (row["source_position"], row["source_sub_position"])
                for row in csv.DictReader(source)
            }
        observed: set[tuple[str, str]] = set()
        with gzip.open(
            RAW_DIR / "players.csv.gz",
            "rt",
            encoding="utf-8-sig",
            newline="",
        ) as source:
            for row in csv.DictReader(source):
                observed.add((row["position"], row["sub_position"]))
        self.assertEqual(observed - mapped, set())

    def test_competition_mapping_covers_observed_types(self) -> None:
        with (CONFIG_DIR / "competition_type_mapping.csv").open(
            encoding="utf-8", newline=""
        ) as source:
            mapped = {row["source_type"] for row in csv.DictReader(source)}
        observed: set[str] = set()
        for table, column in (("competitions", "type"), ("games", "competition_type")):
            with gzip.open(
                RAW_DIR / f"{table}.csv.gz",
                "rt",
                encoding="utf-8-sig",
                newline="",
            ) as source:
                observed.update(row[column] for row in csv.DictReader(source))
        self.assertEqual(observed - mapped, set())

    def test_competition_overrides_cover_games_missing_from_master(self) -> None:
        with (CONFIG_DIR / "competition_id_overrides.csv").open(
            encoding="utf-8", newline=""
        ) as source:
            overrides = {row["competition_id"] for row in csv.DictReader(source)}
        with gzip.open(
            RAW_DIR / "competitions.csv.gz",
            "rt",
            encoding="utf-8-sig",
            newline="",
        ) as source:
            master_ids = {row["competition_id"] for row in csv.DictReader(source)}
        with gzip.open(
            RAW_DIR / "games.csv.gz",
            "rt",
            encoding="utf-8-sig",
            newline="",
        ) as source:
            observed_ids = {row["competition_id"] for row in csv.DictReader(source)}
        self.assertEqual(observed_ids - master_ids - overrides, set())

    def test_postgresql_pipeline_has_no_duckdb_dependency(self) -> None:
        requirements = (ROOT / "requirements.txt").read_text(encoding="utf-8").lower()
        self.assertNotIn("duckdb", requirements)
        self.assertIn("psycopg", requirements)


if __name__ == "__main__":
    unittest.main()
