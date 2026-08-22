"""The Policy Package - a signed, versioned product artefact.

Pitfall 5 (*Policy & Configuration Sprawl*) describes the failure: policy
starts as constants and ad-hoc files, and within weeks nobody can answer "what
is the currently active policy set?" or produce a signed artefact for audit.

The controls implemented here:

* a **named artefact** (``default_policy.yaml``) with an explicit
  ``policy_version``;
* a **single loading path** (:func:`load_policy`) used by the Orchestrator and
  every EdgeAgent;
* a **detached HMAC-SHA256 signature** over a canonical serialisation, so the
  active policy can be proven to be the reviewed one;
* ``policy_version`` surfaced on every verdict and log line.

The signing here is a development-grade HMAC. Production replaces the key
material with a hardware root of trust (Roadmap Layer 6); the *interface* -
sign, verify, refuse to run unverified in strict mode - is what matters now and
is deliberately fixed at this boundary.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml

from apexforge.contracts import Action, ContractViolation

__all__ = [
    "PolicyPackage",
    "PolicyError",
    "PolicySignatureError",
    "LocalPolicy",
    "load_policy",
    "sign_policy",
    "DEFAULT_POLICY_PATH",
]

DEFAULT_POLICY_PATH = Path(__file__).with_name("default_policy.yaml")

#: Development signing key. Production supplies this from a secure store via
#: APEXFORGE_POLICY_KEY and never from source control.
_DEV_KEY = b"apexforge-development-policy-key-not-for-production"


class PolicyError(ValueError):
    """Raised when a policy package is malformed or absent."""


class PolicySignatureError(PolicyError):
    """Raised when a policy package fails signature verification."""


def _signing_key() -> bytes:
    env = os.environ.get("APEXFORGE_POLICY_KEY")
    return env.encode("utf-8") if env else _DEV_KEY


def _canonical(body: Dict[str, Any]) -> bytes:
    """Deterministic serialisation - the thing that actually gets signed.

    Sorted keys and fixed separators mean two semantically identical packages
    always produce the same bytes, so a signature is stable across round-trips
    through YAML.
    """
    return json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sign_policy(body: Dict[str, Any], key: Optional[bytes] = None) -> str:
    """Return the detached HMAC-SHA256 signature for a policy body."""
    return hmac.new(key or _signing_key(), _canonical(body), hashlib.sha256).hexdigest()


@dataclass(frozen=True)
class PolicyPackage:
    """An immutable, verified policy artefact.

    Frozen on purpose: a policy that can be mutated at runtime is a policy that
    cannot be audited.
    """

    policy_version: str
    body: Dict[str, Any]
    signature: str
    source: str = "<memory>"
    verified: bool = False

    @property
    def digest(self) -> str:
        """Short content digest, safe to put in logs alongside the version."""
        return hashlib.sha256(_canonical(self.body)).hexdigest()[:16]

    def get(self, dotted: str, default: Any = None) -> Any:
        cursor: Any = self.body
        for part in dotted.split("."):
            if not isinstance(cursor, dict) or part not in cursor:
                return default
            cursor = cursor[part]
        return cursor

    def human_gate(self, name: str) -> Dict[str, Any]:
        """Return the declared behaviour of a named human decision point.

        Raises if the gate is undeclared: an undeclared gate has no timeout, no
        escalation path and no defined timeout behaviour, which is exactly the
        Pitfall 4 failure. Refusing to guess is the control.
        """
        gate = self.get(f"human_gates.{name}")
        if not isinstance(gate, dict):
            raise PolicyError(
                f"human gate {name!r} is not declared in policy {self.policy_version}. "
                f"Every human decision point must declare notify/timeout_s/"
                f"escalate_to/on_timeout (Pitfall 4)."
            )
        missing = [k for k in ("notify", "timeout_s", "escalate_to", "on_timeout") if k not in gate]
        if missing:
            raise PolicyError(
                f"human gate {name!r} is under-specified, missing {missing}"
            )
        if gate["on_timeout"] not in ("hold", "abort"):
            raise PolicyError(
                f"human gate {name!r} declares on_timeout={gate['on_timeout']!r}; "
                f"only 'hold' or 'abort' are permitted. A gate must never "
                f"auto-approve on timeout (ADR-001, Pitfall 4)."
            )
        return dict(gate)

    def local_policy(self) -> "LocalPolicy":
        """Build the onboard enforcement object for an EdgeAgent."""
        return LocalPolicy(self)


class LocalPolicy:
    """Onboard policy enforcement, derived from a signed Policy Package.

    Every EdgeAgent enforces this locally *before* emitting an action, so the
    envelope holds even with zero backhaul (ADR-001: agents must remain
    functional with no connectivity).
    """

    def __init__(self, package: Optional[PolicyPackage] = None):
        self.package = package if package is not None else load_policy()
        self.policy_version = self.package.policy_version
        self.max_speed = float(self.package.get("edge.max_speed_mps", 15.0))
        self.min_altitude_m = float(self.package.get("edge.min_altitude_m", 0.0))
        self.max_altitude_m = float(self.package.get("edge.max_altitude_m", 400.0))
        self.rtb_battery_threshold = float(
            self.package.get("edge.rtb_battery_threshold", 0.25)
        )
        self.no_fly_zones: List[Dict[str, Any]] = list(
            self.package.get("geofence.no_fly_zones", []) or []
        )

    # -- enforcement ------------------------------------------------------

    def check(self, action: Action) -> Tuple[bool, str]:
        """Return ``(allowed, reason)``. ``reason`` is 'ok' when allowed.

        Returning the reason rather than a bare bool is deliberate: the reason
        goes into assurance evidence, so a rejection is reconstructable months
        later.
        """
        params = action.params or {}

        speed = params.get("speed")
        if speed is not None and float(speed) > self.max_speed:
            return False, f"speed_exceeds_policy({speed}>{self.max_speed})"

        alt = params.get("altitude_m")
        if alt is not None:
            if float(alt) > self.max_altitude_m:
                return False, f"altitude_above_ceiling({alt}>{self.max_altitude_m})"
            if float(alt) < self.min_altitude_m:
                return False, f"altitude_below_floor({alt}<{self.min_altitude_m})"

        position = params.get("position")
        if position is not None:
            zone = self.violated_zone(position)
            if zone:
                return False, f"no_fly_zone({zone})"

        return True, "ok"

    def allows(self, action: Action) -> bool:
        """Boolean form of :meth:`check`, kept for the published interface."""
        return self.check(action)[0]

    def violated_zone(self, position: Any) -> Optional[str]:
        """Name of the first no-fly zone containing ``position``, else None.

        ``position`` is ``(lat, lon)`` or ``(lat, lon, alt)``. Distance uses an
        equirectangular approximation, which is accurate to well under a percent
        at the few-kilometre scale of these zones and needs no dependencies.
        """
        try:
            lat = float(position[0])
            lon = float(position[1])
        except (TypeError, ValueError, IndexError):
            return None

        import math

        for zone in self.no_fly_zones:
            try:
                zlat = float(zone["lat"])
                zlon = float(zone["lon"])
                radius = float(zone["radius_m"])
            except (KeyError, TypeError, ValueError):
                continue
            mean_lat = math.radians((lat + zlat) / 2.0)
            dx = math.radians(lon - zlon) * math.cos(mean_lat) * 6371000.0
            dy = math.radians(lat - zlat) * 6371000.0
            if math.hypot(dx, dy) <= radius:
                return str(zone.get("name", "unnamed"))
        return None

    def safe_fallback(self) -> Action:
        """The action taken when policy rejects the intended one.

        'hold' is the safe default: it neither advances the mission nor
        commits the platform to anything the policy has not cleared.
        """
        return Action(type="hold", params={}, confidence=1.0)


def load_policy(
    path: Optional[Path] = None,
    *,
    require_signature: bool = True,
    key: Optional[bytes] = None,
) -> PolicyPackage:
    """Load and verify the policy package. The single sanctioned loading path.

    Parameters
    ----------
    require_signature:
        When True (the default and the only setting permitted on a mission),
        a package whose signature is absent or wrong raises rather than loads.
        Tests that construct deliberately-unsigned fixtures pass False.
    """
    policy_path = Path(path) if path is not None else DEFAULT_POLICY_PATH
    try:
        with open(policy_path, "r", encoding="utf-8") as fh:
            body = yaml.safe_load(fh) or {}
    except FileNotFoundError as exc:
        raise PolicyError(f"policy package not found: {policy_path}") from exc
    except yaml.YAMLError as exc:
        raise PolicyError(f"policy package {policy_path} is not valid YAML: {exc}") from exc

    if not isinstance(body, dict):
        raise PolicyError(f"policy package root of {policy_path} must be a mapping")

    version = body.get("policy_version")
    if not version:
        raise PolicyError(
            f"policy package {policy_path} declares no policy_version. "
            f"An unversioned policy cannot appear in an assurance verdict."
        )

    # The signature covers the body without the signature field itself.
    supplied = body.pop("signature", None)
    expected = sign_policy(body, key)

    verified = bool(supplied) and hmac.compare_digest(str(supplied), expected)
    if require_signature and not verified:
        if supplied is None:
            # A sidecar .sig file is the normal distribution form; fall back to
            # it before failing, so signing does not have to mutate the YAML.
            sidecar = policy_path.with_suffix(policy_path.suffix + ".sig")
            if sidecar.exists():
                supplied = sidecar.read_text(encoding="utf-8").strip()
                verified = hmac.compare_digest(supplied, expected)
        if not verified:
            raise PolicySignatureError(
                f"policy package {policy_path} (v{version}) failed signature "
                f"verification. Expected {expected[:16]}..., got "
                f"{str(supplied)[:16] if supplied else '<none>'}. Refusing to load "
                f"an unverified policy."
            )

    return PolicyPackage(
        policy_version=str(version),
        body=body,
        signature=expected,
        source=str(policy_path),
        verified=verified,
    )
