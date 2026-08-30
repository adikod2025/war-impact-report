#!/usr/bin/env python3
"""Re-sign the Policy Package after an authorised change.

Usage::

    python3 tools/sign_policy.py [path/to/policy.yaml]

Writes a detached ``<policy>.sig`` file. Run this whenever the policy body
changes; CI verifies the signature and a stale one fails the build, which is
what forces a policy change to go through review rather than drift in quietly.
"""
from __future__ import annotations

import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from apexforge.policy.package import DEFAULT_POLICY_PATH, sign_policy  # noqa: E402


def main(argv: list[str]) -> int:
    path = Path(argv[1]) if len(argv) > 1 else DEFAULT_POLICY_PATH
    body = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    body.pop("signature", None)
    signature = sign_policy(body)
    sidecar = path.with_suffix(path.suffix + ".sig")
    sidecar.write_text(signature + "\n", encoding="utf-8")
    print(f"signed {path.name} (policy_version={body.get('policy_version')})")
    print(f"  -> {sidecar.name}: {signature}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
