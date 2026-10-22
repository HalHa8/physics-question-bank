"""Capability checks for optional native filesystem behavior, not product gates."""
import os
import pytest


def symlink_or_skip(link, target, **kwargs):
    try:
        link.symlink_to(target, **kwargs)
    except OSError as exc:
        if os.name == 'nt' and getattr(exc, 'winerror', None) == 1314:
            pytest.skip('Windows process lacks symlink privilege; path-security unit checks still run')
        raise
