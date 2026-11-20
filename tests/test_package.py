from __future__ import annotations

from importlib.metadata import version

import soa


def test_version_matches_the_installed_metadata():
    assert soa.__version__ == version("system-on-an-agent")
