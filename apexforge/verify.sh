#!/usr/bin/env bash
# ApexForge ADFMS - the verification gate.
#
# This is the single command that decides whether the baseline is trustworthy.
# It is what CI runs, what a Layer Exit Review runs, and what any agentic
# session must run before claiming it is done. Everything it checks is
# reproducible from a clean checkout.
set -euo pipefail

cd "$(dirname "$0")"

COV_MIN="${APEXFORGE_COV_MIN:-80}"
GREEN=$'\033[0;32m'; RED=$'\033[0;31m'; BOLD=$'\033[1m'; NC=$'\033[0m'

step() { printf '\n%s==> %s%s\n' "$BOLD" "$1" "$NC"; }
ok()   { printf '%s    PASS%s  %s\n' "$GREEN" "$NC" "$1"; }
fail() { printf '%s    FAIL%s  %s\n' "$RED" "$NC" "$1"; exit 1; }

step "Environment"
python3 --version
python3 -c "import pytest, yaml; print('pytest', pytest.__version__, '| pyyaml', yaml.__version__)"

step "1/6  Policy Package signature"
python3 - <<'PY'
import sys
from apexforge.policy.package import load_policy
pkg = load_policy()                     # raises unless the signature verifies
assert pkg.verified, "policy package did not verify"
print(f"    policy_version={pkg.policy_version} digest={pkg.digest} verified=True")
PY
ok "signed policy package verifies"

step "2/6  Frozen contract tests (Pitfall 1 control)"
python3 -m pytest tests/test_contracts.py -q --no-header
ok "contracts frozen and green"

step "3/6  WF-SMOKE-01 (must stay green forever)"
python3 -m pytest -m smoke -q --no-header
ok "WF-SMOKE-01 green"

step "4/6  ADR-001 invariant tests (Pitfall 7 control)"
python3 -m pytest -m invariant -q --no-header
ok "ADR-001 invariants preserved"

step "5/6  Full suite with coverage (threshold ${COV_MIN}%)"
python3 -m pytest -q --no-header \
    --cov=apexforge --cov-report=term-missing:skip-covered \
    --cov-fail-under="${COV_MIN}"
ok "full suite green, coverage >= ${COV_MIN}%"

step "6/6  Performance budgets"
python3 -m pytest -m perf -q --no-header
ok "edge tick p99 and assurance aggregation within budget"

printf '\n%sVERIFICATION GATE PASSED%s\n' "$GREEN$BOLD" "$NC"
printf 'Layer 1 exit-gate evidence is reproducible from this checkout.\n'
