"""A local console server. Standard library only, loopback only.

**Read this before deploying anything here.** This is a *local operator
console harness*, not a deployable service, and the difference is not a
formality:

* there is **no authentication**. The operator's identity comes from a registry
  supplied at construction and selected by a query parameter. Anyone who can
  reach the socket can be anyone in the registry;
* there is **no transport security**. Plain HTTP;
* there is **no session management**, no CSRF token, and no rate limiting.

All three are FR-2.7.1, which ``docs/FRS_TRACEABILITY.md`` records as an open
GAP covering cryptographic identity, transport encryption, zero-trust and
attestation. This module does not close it and must not be read as closing it.

What it *does* do is refuse to make the mistake easy: it binds to loopback and
refuses any other host, and it refuses to start without an explicit operator
registry, so there is no default-credentials path and no accidental exposure to
a network interface. A deployment that needs a real console puts an
authenticating reverse proxy in front of this and adds the identity layer
FR-2.7.1 describes - and until that exists, this is a single-machine tool.

Every mutating request still travels through :class:`OperatorConsole`, so the
access control, the assurance gate and the human-decision binding all apply
exactly as they do in process. The server adds no authority of its own.
"""

from __future__ import annotations

import json
import logging
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any, Callable, Dict, Mapping, Optional, Tuple
from urllib.parse import parse_qs, urlparse

from apexforge.contracts import ContractViolation
from apexforge.ui.access import AccessDenied
from apexforge.ui.console import ConsoleError, OperatorConsole
from apexforge.ui.contracts import IntentDraft, Operator
from apexforge.ui.render import render_page
from apexforge.ui.viewmodel import ViewModelBuilder

__all__ = ["ConsoleApp", "LOOPBACK_HOSTS", "serve"]

#: The only hosts this server will bind to. Not a suggestion - :func:`serve`
#: raises on anything else, because "it was only meant for local use" is not a
#: control, and a console with no authentication reachable from a network is a
#: strictly worse outcome than one that refused to start.
LOOPBACK_HOSTS = ("127.0.0.1", "localhost", "::1")

_LOGGER = logging.getLogger("apexforge.ui.server")


class ConsoleApp:
    """Request routing and rendering, independent of any HTTP machinery.

    Split out from the handler so the whole request surface is testable by
    calling methods, with no socket, no port and no thread. A console tested
    only through a live server is a console whose tests are timing-dependent.
    """

    def __init__(
        self,
        *,
        builder: ViewModelBuilder,
        console: OperatorConsole,
        operators: Mapping[str, Operator],
        default_operator_id: str = "",
    ):
        if not operators:
            raise ValueError(
                "ConsoleApp requires an explicit operator registry. There is no "
                "default operator and no anonymous mode: an unattributed console "
                "action cannot satisfy Pitfall 4."
            )
        self.builder = builder
        self.console = console
        self.operators = dict(operators)
        self.default_operator_id = default_operator_id or sorted(self.operators)[0]

    # -- identity ---------------------------------------------------------

    def operator_for(self, query: Mapping[str, Any]) -> Operator:
        """Resolve the acting operator. **Selection, not authentication.**

        An unknown id raises rather than falling back to the default. Falling
        back would mean an action attributed to somebody who did not take it,
        which is worse than an error page.
        """
        raw = query.get("operator")
        operator_id = (raw[0] if isinstance(raw, list) else raw) or self.default_operator_id
        try:
            return self.operators[str(operator_id)]
        except KeyError:
            raise LookupError(f"unknown operator {operator_id!r}") from None

    # -- routes -----------------------------------------------------------

    def get(self, path: str, query: Mapping[str, Any]) -> Tuple[int, str, str]:
        """Handle a GET. Returns ``(status, content_type, body)``."""
        try:
            operator = self.operator_for(query)
        except LookupError as exc:
            return 404, "text/plain; charset=utf-8", str(exc)

        mission = query.get("mission", [""])
        mission_id = mission[0] if isinstance(mission, list) else str(mission or "")

        if path == "/state.json":
            view = self.builder.console(operator, replay_mission_id=mission_id)
            return (
                200,
                "application/json; charset=utf-8",
                json.dumps(view.to_wire(), indent=2, default=str),
            )
        if path in ("/", "/console"):
            message = query.get("message", [""])
            note = message[0] if isinstance(message, list) else str(message or "")
            view = self.builder.console(operator, replay_mission_id=mission_id)
            return 200, "text/html; charset=utf-8", render_page(view, message=note)
        return 404, "text/plain; charset=utf-8", "no such view"

    def post(
        self, path: str, query: Mapping[str, Any], form: Mapping[str, Any]
    ) -> Tuple[int, str, str]:
        """Handle a POST. Every branch routes through :class:`OperatorConsole`."""
        try:
            operator = self.operator_for(query)
        except LookupError as exc:
            return 404, "text/plain; charset=utf-8", str(exc)

        if path == "/intent":
            return self._post_intent(operator, form)
        if path == "/gate":
            return self._post_gate(operator, form)
        return 404, "text/plain; charset=utf-8", "no such action"

    @staticmethod
    def _single(form: Mapping[str, Any], key: str, default: str = "") -> str:
        value = form.get(key, default)
        if isinstance(value, list):
            return value[0] if value else default
        return str(value)

    def _post_intent(
        self, operator: Operator, form: Mapping[str, Any]
    ) -> Tuple[int, str, str]:
        flat = {k: self._single(form, k) for k in form}
        try:
            draft = IntentDraft.from_form(flat)
        except (ContractViolation, ValueError) as exc:
            return self._redirect(operator, f"rejected: {exc}")

        try:
            outcome = self.console.submit_intent(operator, draft)
        except AccessDenied as exc:
            return 403, "text/plain; charset=utf-8", str(exc)
        except ConsoleError as exc:
            return 503, "text/plain; charset=utf-8", str(exc)

        if outcome.accepted:
            note = f"intent accepted: {outcome.dispatched} role(s) dispatched"
        elif outcome.appealable:
            note = (
                f"refused ({outcome.reason}) - appealable at gate "
                f"{outcome.gate.get('name', 'unknown')}"
            )
        else:
            note = f"refused ({outcome.reason}) - not appealable"
        return self._redirect(operator, note)

    def _post_gate(
        self, operator: Operator, form: Mapping[str, Any]
    ) -> Tuple[int, str, str]:
        instance_id = self._single(form, "instance_id")
        step_id = self._single(form, "step_id")
        rationale = self._single(form, "rationale")
        approved = self._single(form, "decision") == "approve"

        instance = self._instance(instance_id)
        if instance is None:
            return self._redirect(operator, f"no open instance {instance_id!r}")

        try:
            outcome = self.console.decide_gate(
                operator,
                instance,
                step_id,
                approved=approved,
                rationale=rationale,
            )
        except AccessDenied as exc:
            return 403, "text/plain; charset=utf-8", str(exc)
        except ConsoleError as exc:
            return 503, "text/plain; charset=utf-8", str(exc)
        except ContractViolation as exc:
            # An empty rationale lands here. Surfaced as a message rather than a
            # 500: the operator forgot a required field, which is a normal
            # interaction, not a fault.
            return self._redirect(operator, f"rejected: {exc}")

        verb = "approved" if approved else "denied"
        note = (
            f"gate {step_id} {verb} ({outcome.status})"
            if outcome.accepted
            else f"gate {step_id} not recorded: {outcome.reason}"
        )
        return self._redirect(operator, note)

    def _instance(self, instance_id: str) -> Optional[Any]:
        for inst in self.builder.instances:
            if str(getattr(inst, "instance_id", "")) == instance_id:
                return inst
        return None

    @staticmethod
    def _redirect(operator: Operator, message: str) -> Tuple[int, str, str]:
        """Post/redirect/get, so a refresh cannot resubmit a decision.

        Not a nicety. A browser refresh that re-POSTs a gate decision would
        produce a second attributed HumanDecision the operator never made.
        """
        from urllib.parse import quote

        target = (
            f"/console?operator={quote(operator.operator_id)}&message={quote(message)}"
        )
        return 303, target, ""


class _Handler(BaseHTTPRequestHandler):
    """Thin HTTP adapter. Holds no logic worth testing through a socket."""

    app: ConsoleApp  # set by serve()
    server_version = "ApexForgeConsole/1.0"

    def log_message(self, fmt: str, *args: Any) -> None:  # pragma: no cover - noise
        _LOGGER.info("%s - %s", self.address_string(), fmt % args)

    def _send(self, status: int, content_type: str, body: str) -> None:
        if status == 303:
            self.send_response(303)
            self.send_header("Location", content_type)
            self.end_headers()
            return
        payload = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        # A console that renders another site's data, or is rendered inside
        # one, is a console whose screenshots cannot be trusted as evidence.
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'none'; style-src 'unsafe-inline'; form-action 'self'",
        )
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self) -> None:  # noqa: N802 - stdlib naming
        parsed = urlparse(self.path)
        status, ctype, body = self.app.get(parsed.path, parse_qs(parsed.query))
        self._send(status, ctype, body)

    def do_POST(self) -> None:  # noqa: N802 - stdlib naming
        parsed = urlparse(self.path)
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length).decode("utf-8") if length else ""
        status, ctype, body = self.app.post(
            parsed.path, parse_qs(parsed.query), parse_qs(raw)
        )
        self._send(status, ctype, body)


def serve(
    app: ConsoleApp, host: str = "127.0.0.1", port: int = 8787
) -> HTTPServer:
    """Build a loopback-only HTTP server for ``app``.

    Returns the server without calling ``serve_forever``, so the caller decides
    the threading model and a test can exercise it without a background thread.

    Raises ``ValueError`` for any non-loopback host. See the module docstring:
    this console has no authentication, so binding it to a routable interface
    is not a configuration choice, it is a defect.
    """
    if host not in LOOPBACK_HOSTS:
        raise ValueError(
            f"refusing to bind the console to {host!r}. This server has no "
            f"authentication and no transport security (FR-2.7.1); it may only "
            f"bind {list(LOOPBACK_HOSTS)}."
        )
    handler = type("_BoundHandler", (_Handler,), {"app": app})
    return HTTPServer((host, port), handler)
