"""Back up the deckdoctor Postgres database to the tower NAS.

`pg_dump -Fc` (compressed custom format) → scp to tower → prune to the newest N.
Works on the Windows dev box and the Linux VPS; the only host-specific bit is the
pg_dump path (auto-detected, or set PG_DUMP / --pg-dump).

    python tools/backup_db.py
    python tools/backup_db.py --dest root@tower:/mnt/user/backups/deck-doctor --keep 14

Restore a dump with:  pg_restore --no-owner --clean --if-exists -d deckdoctor <file>
"""

from __future__ import annotations

import argparse
import os
import re
import socket
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_URL = os.environ.get(
    "DATABASE_URL", "postgresql://deckdoctor:deckdoctor@localhost:5432/deckdoctor")
DEFAULT_DEST = os.environ.get("BACKUP_DEST", "root@tower:/mnt/user/backups/deck-doctor")


def _find_pg_dump() -> str:
    if os.environ.get("PG_DUMP"):
        return os.environ["PG_DUMP"]
    # portable install used on the Windows dev box
    win = Path(r"C:/simmander/pg/pgsql/bin/pg_dump.exe")
    return str(win) if win.exists() else "pg_dump"


def main() -> int:
    ap = argparse.ArgumentParser(description="Back up deckdoctor Postgres to tower.")
    ap.add_argument("--database-url", default=DEFAULT_URL)
    ap.add_argument("--dest", default=DEFAULT_DEST,
                    help="user@host:/dir on the backup target (tower)")
    ap.add_argument("--keep", type=int, default=14, help="keep the newest N dumps")
    ap.add_argument("--pg-dump", default=_find_pg_dump())
    args = ap.parse_args()

    if ":" not in args.dest:
        print("--dest must be user@host:/dir", file=sys.stderr)
        return 2
    host, remote_dir = args.dest.split(":", 1)

    # Host-tagged so dev + prod dumps coexist in one dir and prune independently.
    host = re.sub(r"[^A-Za-z0-9_-]", "", socket.gethostname()) or "host"
    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%SZ")
    fname = f"deckdoctor-{host}-{ts}.dump"
    local = Path(tempfile.gettempdir()) / fname

    print(f"[backup] pg_dump -> {local}")
    with local.open("wb") as fh:
        rc = subprocess.run(
            [args.pg_dump, "-Fc", "--no-owner", "--no-acl", args.database_url],
            stdout=fh).returncode
    if rc != 0 or not local.exists() or local.stat().st_size < 1024:
        print(f"[backup] pg_dump FAILED (rc={rc})", file=sys.stderr)
        local.unlink(missing_ok=True)
        return 1
    size_mb = local.stat().st_size / 1e6
    print(f"[backup] dump {size_mb:.1f} MB")

    ssh = ["ssh", "-o", "ConnectTimeout=20", host]
    if subprocess.run(ssh + [f"mkdir -p '{remote_dir}'"]).returncode != 0:
        print("[backup] could not reach tower / mkdir failed", file=sys.stderr)
        return 1
    print(f"[backup] scp -> {args.dest}/{fname}")
    if subprocess.run(["scp", "-q", str(local), f"{args.dest}/{fname}"]).returncode != 0:
        print("[backup] scp FAILED", file=sys.stderr)
        return 1
    local.unlink(missing_ok=True)

    # Prune: keep the newest --keep dumps FROM THIS HOST (so dev pruning never
    # touches prod dumps sharing the directory).
    prune = (f"ls -1t '{remote_dir}'/deckdoctor-{host}-*.dump 2>/dev/null | "
             f"tail -n +{args.keep + 1} | xargs -r rm -f")
    subprocess.run(ssh + [prune])
    kept = subprocess.run(
        ssh + [f"ls -1 '{remote_dir}'/deckdoctor-{host}-*.dump 2>/dev/null | wc -l"],
        capture_output=True, text=True).stdout.strip()
    print(f"[backup] done — {args.dest}/{fname} ({kept} dumps retained, keep={args.keep})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
