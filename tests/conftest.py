"""Test-suite conftest.

Loads ``.env`` if python-dotenv is installed so that integration tests can
pick up ``BYTEFUL_API_PUBLIC_KEY`` / ``BYTEFUL_API_PRIVATE_KEY`` without the
developer having to export them into the shell first. Safe to import for
unit tests too: ``load_dotenv()`` is a no-op when no ``.env`` file exists.
"""

from __future__ import annotations

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - dev dep is normally present
    pass
else:
    load_dotenv()
