"""No-clobber publication and bounded Windows sharing-error retries.

Windows: ``os.rename`` refuses an existing destination, and transient antivirus/
OneDrive holds surface as WinError 5/32, which ``sharing_retry`` retries a bounded
number of times. POSIX: ``os.link`` + unlink refuses an existing destination
(``os.rename`` would silently replace it); POSIX errors carry no ``winerror``, so they
are never retried. ``_WINDOWS`` exists so tests can exercise either primitive on one
host without patching ``os.name`` (which would break ``pathlib``).
"""
import time
import os

_WINDOWS = os.name == "nt"
# Backoff after attempts 1-4; a fifth failure is final. Sum 1.5 s <= the 2 s budget.
SHARING_DELAYS = (0.1, 0.2, 0.4, 0.8)
SHARING_WINERRORS = frozenset({5, 32})


def rename_no_clobber(source, destination):
    """Publish or archive without overwriting a concurrently created destination."""
    if _WINDOWS:
        os.rename(source, destination)
    else:
        os.link(source, destination)
        os.unlink(source)


def sharing_retry(operation, *, validate=lambda: None, sleep=None):
    sleep = time.sleep if sleep is None else sleep
    for attempt in range(len(SHARING_DELAYS) + 1):
        try:
            validate()
            return operation()
        except OSError as exc:
            if getattr(exc, "winerror", None) not in SHARING_WINERRORS or attempt == len(SHARING_DELAYS):
                raise
            sleep(SHARING_DELAYS[attempt])
