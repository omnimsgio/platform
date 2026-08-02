"""CLI entrypoint: alembic upgrade head using package migrations."""

from __future__ import annotations

import sys
from pathlib import Path

from alembic import command
from alembic.config import Config


def migrations_dir() -> Path:
    return Path(__file__).resolve().parent / "migrations"


def _alembic_config() -> Config:
    root = migrations_dir()
    cfg = Config(str(root / "alembic.ini"))
    cfg.set_main_option("script_location", str(root))
    return cfg


def main(argv: list[str] | None = None) -> None:
    args = argv if argv is not None else sys.argv[1:]
    cfg = _alembic_config()
    if not args or args == ["upgrade", "head"] or (args[0] == "upgrade" and len(args) == 1):
        command.upgrade(cfg, "head")
        return
    if args[0] == "upgrade":
        command.upgrade(cfg, args[1])
        return
    print("usage: omnimsg-migrate [upgrade head]", file=sys.stderr)
    raise SystemExit(2)


if __name__ == "__main__":
    main()
