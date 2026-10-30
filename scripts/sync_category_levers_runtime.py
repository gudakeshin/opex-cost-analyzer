#!/usr/bin/env python3
"""Sync category-gated levers from sector_packs stubs into skills/sector-packs runtime JSON."""
from __future__ import annotations

from app.services.lever_runtime_sync import sync_all_packs


def main() -> None:
    count = sync_all_packs()
    print(f"Synced {count} pack(s)")


if __name__ == "__main__":
    main()
