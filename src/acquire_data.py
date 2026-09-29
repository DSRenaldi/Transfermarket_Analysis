"""Download and fingerprint the published Transfermarkt CSV snapshot."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
import shutil
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


BASE_URL = "https://pub-e682421888d945d684bcae8890b0ec20.r2.dev/data"
TABLES = (
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
)
USER_AGENT = "football-player-value-analytics/1.0"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_gzip(path: Path) -> None:
    with gzip.open(path, "rb") as source:
        while source.read(1024 * 1024):
            pass


def download(url: str, destination: Path) -> dict[str, str | int | None]:
    partial = destination.with_suffix(destination.suffix + ".part")
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            with partial.open("wb") as target:
                shutil.copyfileobj(response, target, length=1024 * 1024)
            headers = response.headers
    except Exception:
        partial.unlink(missing_ok=True)
        raise

    os.replace(partial, destination)
    validate_gzip(destination)
    return {
        "etag": headers.get("ETag"),
        "last_modified": headers.get("Last-Modified"),
        "content_length_header": int(headers["Content-Length"])
        if headers.get("Content-Length")
        else None,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-dir", type=Path, default=Path("data/raw"))
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path("reports/data_audit/source_manifest.json"),
    )
    parser.add_argument("--force", action="store_true", help="Redownload existing files")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    args.raw_dir.mkdir(parents=True, exist_ok=True)
    args.manifest.parent.mkdir(parents=True, exist_ok=True)

    files: list[dict[str, object]] = []
    for table in TABLES:
        filename = f"{table}.csv.gz"
        path = args.raw_dir / filename
        url = f"{BASE_URL}/{filename}"
        response_metadata: dict[str, str | int | None] = {}

        if args.force or not path.exists():
            print(f"Downloading {filename} ...", flush=True)
            try:
                response_metadata = download(url, path)
            except urllib.error.URLError as error:
                print(f"Download failed for {url}: {error}", file=sys.stderr)
                return 1
        else:
            print(f"Reusing {filename} ...", flush=True)
            validate_gzip(path)

        files.append(
            {
                "table": table,
                "filename": filename,
                "url": url,
                "bytes": path.stat().st_size,
                "sha256": sha256_file(path),
                **response_metadata,
            }
        )

    manifest = {
        "dataset": "dcaribou/transfermarkt-datasets",
        "source_repository": "https://github.com/dcaribou/transfermarkt-datasets",
        "original_data_source": "Transfermarkt",
        "distribution_base_url": BASE_URL,
        "downloaded_at_utc": datetime.now(timezone.utc).isoformat(),
        "file_count": len(files),
        "total_compressed_bytes": sum(int(item["bytes"]) for item in files),
        "files": files,
    }
    args.manifest.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(f"Manifest written to {args.manifest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
