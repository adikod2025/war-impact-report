"""Shared fixtures.

Listed in the handoff's repository layout (§3 and Appendix §5) and absent from
the first cut of this build — the test files each defined their own fixtures
instead. Restored here for the fixtures that genuinely are shared; per-module
fixtures deliberately stay in the file that uses them, because a fixture used
once is clearer next to its test than in a common file.
"""

import pytest

from apexforge.config.loader import load_config
from apexforge.obs.logging import AuditLog
from apexforge.policy.package import load_policy


@pytest.fixture
def config():
    """The committed default configuration."""
    return load_config()


@pytest.fixture
def policy():
    """The active signed Policy Package."""
    return load_policy()


@pytest.fixture
def audit():
    """A fresh append-only audit log.

    Injected rather than relying on the module-level ``AUDIT`` singleton, so a
    test never sees another test's events and assertions about record counts
    mean what they say.
    """
    return AuditLog()


@pytest.fixture(autouse=True)
def _isolate_module_audit():
    """Keep the process-wide audit log from leaking between tests.

    ``apexforge.obs.logging.AUDIT`` is a module-level default for call sites
    that do not inject one. Without this, one test's events accumulate into the
    next test's view of history — the classic source of a suite that passes as
    a whole and fails when a file is run alone.
    """
    from apexforge.obs import logging as obs_logging

    obs_logging.AUDIT.clear()
    yield
    obs_logging.AUDIT.clear()
