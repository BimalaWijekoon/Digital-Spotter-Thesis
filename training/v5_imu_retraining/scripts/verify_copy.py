#!/usr/bin/env python3
"""Read-only verification of this workspace's copied research references."""

from __future__ import annotations

import argparse
import csv
import hashlib
from collections import defaultdict
from pathlib import Path


def digest(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(block)
    return hasher.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check-source", action="store_true")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    with (root / "COPY_MANIFEST.csv").open(newline="", encoding="utf-8") as handle:
        manifest = list(csv.DictReader(handle))
    if not manifest:
        raise SystemExit("FAIL: empty copy manifest")
    seen: set[str] = set()
    for record in manifest:
        relative = record["destination_path"]
        destination = (root / relative).resolve()
        if not destination.is_relative_to(root) or relative in seen:
            raise SystemExit("FAIL: unsafe or duplicate destination: " + relative)
        seen.add(relative)
        if destination.stat().st_size != int(record["size_bytes"]):
            raise SystemExit("FAIL: copied size differs: " + relative)
        expected = record["source_sha256"]
        if (record["match"] != "true" or record["copied_sha256"] != expected
                or digest(destination) != expected):
            raise SystemExit("FAIL: copied hash differs: " + relative)
        if args.check_source and digest(Path(record["source_path"])) != expected:
            raise SystemExit("FAIL: original source hash changed: " + relative)
    with (root / "reference/dataset/master_dataset.csv").open(
        newline="", encoding="utf-8-sig"
    ) as handle:
        rows = list(csv.DictReader(handle))
    groups: dict[tuple[str, str], list[int]] = defaultdict(list)
    for row in rows:
        groups[(row["Session_ID"], row["Rep_ID"])].append(int(row["Rep_Phase"]))
    if (len(rows) != 6054 or len(groups) != 2018
            or any(sorted(phases) != [1, 2, 3] for phases in groups.values())):
        raise SystemExit("FAIL: copied baseline repetition contract differs")
    print(f"PASS: {len(manifest)}/{len(manifest)} copied files match SHA256 and size")
    if args.check_source:
        print(f"PASS: {len(manifest)}/{len(manifest)} original source hashes unchanged")
    print("PASS: baseline has 6,054 rows / 2,018 complete [1, 2, 3] repetitions")
    print("No data generation, training, model loading or hardware access performed")


if __name__ == "__main__":
    main()
