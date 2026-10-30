"""Bounded Windows sharing-error retries; other errors remain immediate failures."""
import time
import os


def rename_no_clobber(source, destination):
    """Publish or archive without overwriting a concurrently created destination."""
    if os.name == "nt":
        os.rename(source, destination)
    else:
        os.link(source, destination)
        source.unlink()


def sharing_retry(operation, *, validate=lambda: None, sleep=None):
    sleep = time.sleep if sleep is None else sleep
    delays = (0.1, 0.2, 0.4, 0.8)
    for attempt in range(5):
        try:
            validate()
            return operation()
        except OSError as exc:
            if getattr(exc, "winerror", None) not in {5, 32} or attempt == 4:
                raise
            sleep(delays[attempt])
