from __future__ import annotations

import fcntl
import threading
from collections.abc import Iterator
from contextlib import contextmanager, suppress
from pathlib import Path

_PROCESS_CATALOG_LOCK = threading.RLock()


@contextmanager
def catalog_transaction(data_dir: Path) -> Iterator[None]:
    """Serialize catalog media publication and reconciliation across workers."""

    lock_path = data_dir / ".feed-catalog.lock"
    with _PROCESS_CATALOG_LOCK, lock_path.open("a+") as lock_file:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            # Closing the descriptor also releases the lock. An explicit
            # unlock failure must not turn a committed publication into an
            # apparent failure.
            with suppress(OSError):
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
