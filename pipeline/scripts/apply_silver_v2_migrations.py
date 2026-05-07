"""
apply_silver_v2_migrations.py — Backwards-compatibility shim.

This file previously contained the Phase B-1 migration runner for
silver_v2_* DDL.  It has been superseded by apply_migrations.py, the
general-purpose idempotent runner that tracks all migrations via
infra.applied_migrations.

Import-level delegation ensures any code that imported this module
directly continues to work.
"""

from scripts.apply_migrations import apply_migrations, main  # noqa: F401

if __name__ == "__main__":
    main()
