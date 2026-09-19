#!/usr/bin/env python
"""Download the two UCI datasets into data/raw/.

Both are fetched straight from the UCI API. Two runtime quirks are handled
here rather than downstream (see DECISIONS.md):

* the python.org macOS build has no usable CA store, so certifi's bundle is
  installed into the environment before any TLS call;
* the energy CSV is served with a UTF-8 BOM, which corrupts the first column
  name under plain utf-8.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.request
from pathlib import Path

import certifi

REPO_ROOT = Path(__file__).resolve().parents[1]
RAW = REPO_ROOT / "data" / "raw"

ENERGY_ID = 851
FAULTS_ID = 198

EXPECTED_ENERGY_ROWS = 35_040
EXPECTED_FAULTS_ROWS = 1_941


def _install_ca_bundle() -> None:
    """Point urllib and requests at certifi's CA bundle."""
    os.environ.setdefault("SSL_CERT_FILE", certifi.where())
    os.environ.setdefault("REQUESTS_CA_BUNDLE", certifi.where())


def _metadata(dataset_id: int) -> dict:
    """Fetch a dataset's metadata from the UCI API."""
    url = f"https://archive.ics.uci.edu/api/dataset?id={dataset_id}"
    with urllib.request.urlopen(url, timeout=60) as response:  # noqa: S310
        return json.load(response)["data"]


def _download(url: str, target: Path) -> Path:
    """Stream a URL to disk, returning the path."""
    target.parent.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(url, timeout=300) as response:  # noqa: S310
        target.write_bytes(response.read())
    return target


def fetch(dataset_id: int, filename: str, expected_rows: int) -> Path:
    """Download one dataset and assert it has the row count the plan expects."""
    import pandas as pd

    meta = _metadata(dataset_id)
    data_url = meta["data_url"]
    print(f"  id={dataset_id}  {meta['name']}")
    print(f"  from {data_url}")

    path = _download(data_url, RAW / filename)
    # utf-8-sig strips the BOM; without it the first column is named '﻿date'.
    frame = pd.read_csv(path, encoding="utf-8-sig")
    print(f"  -> {path.relative_to(REPO_ROOT)}  {len(frame):,} rows x {frame.shape[1]} cols")

    if len(frame) != expected_rows:
        print(
            f"  WARNING: expected {expected_rows:,} rows, got {len(frame):,}. "
            "The upstream dataset changed; record this in DECISIONS.md.",
            file=sys.stderr,
        )
    return path


def main() -> int:
    """Download both datasets."""
    _install_ca_bundle()
    RAW.mkdir(parents=True, exist_ok=True)

    print("Steel Industry Energy Consumption")
    fetch(ENERGY_ID, "energy_851.csv", EXPECTED_ENERGY_ROWS)
    print("\nSteel Plates Faults")
    fetch(FAULTS_ID, "plates_198.csv", EXPECTED_FAULTS_ROWS)

    print("\nDone. Raw files are gitignored; re-run this script on a fresh clone.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
