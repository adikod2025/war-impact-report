# Design note — Predictive MRO & Digital Twin

Blueprint §4.4 · Roadmap Layer 3 interfaces · Owner: A4 · Modules: `apexforge/mro/twin.py`, `apexforge/mro/predictor.py`

## The RUL model is a deterministic stub, and says so

`HealthPredictor._simple_rul(history, component)` is arithmetic, not learning: no history → `(100.0h, ±20.0h, conf 0.30)`; fewer than two usable samples → `(50.0h, ±15.0h, conf 0.50)` — absence of data is never evidence of health. Otherwise, over the last `TREND_WINDOW=5` samples, `slope = (recent[-1] - recent[0]) / (n-1)`, and:

* `slope >= 0` (flat or improving) — no wear-out horizon exists, so the nominal `FLAT_SERIES_MEAN_H = 80.0h` is reported rather than infinity;
* `slope < 0` — `mean = max(0, recent[-1] / |slope + 1e-9|)`, i.e. how long the present level lasts at the present rate of decline (the epsilon guards division by a vanishing slope);
* `std = pstdev(recent) * 10`; `conf = min(0.95, 0.4 + 0.1 * n_samples)` — the cap encodes that a five-point linear fit is never near-certain.

**Determinism:** pure functions of the input list — no RNG, clock, hidden state or I/O. Identical history yields identical `mean/std/confidence` on any machine in any call order, which is what makes the gated recommendation reviewable. **Robustness:** non-mapping entries and missing, non-numeric, boolean, NaN and infinite channels are filtered before any arithmetic, so a malformed HUMS stream degrades the estimate instead of raising.

## What a signed ONNX model replaces

Layer 3 replaces **the body of `_simple_rul` only**. The replacement must satisfy the interface already fixed around it: `Sequence[history dict] -> RULEstimate`; deterministic; total (never raises on degenerate input); confidence in `[0,1]`; no side effects beyond the `rul_prediction` event. Its distribution needs the Policy Package's provenance discipline — a named, versioned, signature-verified artefact loaded through one path, with the model identity carried in every event (today `model="deterministic_stub"`). Until that artefact exists, faking an ML model here would misreport Layer 3 as done.

## The work-order human gate

`recommend()` produces `elevated` or `critical` only; both set `requires_human_approval=True` as an invariant, and `WorkOrderRecommendation.__post_init__` **raises** if that flag is False at those priorities — it cannot be computed away. Lifecycle: `proposed → awaiting_approval → approved | rejected | timed_out → escalated`.

* `approve(order, decision)` demands a real `HumanDecision` (operator_id and rationale are mandatory in the frozen contract) whose `workflow_instance_id` matches the order, so an approval cannot be replayed onto another item.
* `WorkOrderBridge.submit()` — the mock ERP/PLM boundary — admits an order only when state is `approved` **and** an attributed approving decision is attached. A hand-set state string is refused; there is no bypass argument.
* `expire(order, elapsed_s)` reads `on_timeout` from the signed policy gate `critical_mro_work_order` (`hold`), moves the order to `timed_out`, records `escalate_to=fleet_manager` and emits `auto_approved=False`. `timed_out` has **no edge to `approved`** in the transition graph: an escalated order must still collect an attributed decision from the escalation authority.

Every transition emits via `emit_event()` with `platform_id`, `workflow_instance_id`, `assurance_verdict`, `policy_version`, timestamp and schema version; approvals emit `event_type="human_decision"`.

## Twin convergence under DDIL

`DigitalTwin` orders bounded per-platform history by `(timestamp, ingest sequence)`, not by arrival. `sync()` is idempotent — a replayed record is identified by its incoming content and counted as a duplicate, including against records already pushed live — and order-tolerant: a late buffered record lands in its chronological slot and cannot regress twin state. `converged(platform_id, expected)` names each mismatched field plus the lag against the source, and is True only when values agree within tolerance *and* lag ≤ SLA: a stale-but-matching twin is not converged.

## Known limitations

* The stub extrapolates one channel linearly — no load, duty cycle, temperature or component coupling — and treats battery fraction as a life proxy. It will be wrong on non-linear wear; hence the human gate.
* Confidence is a sample-count heuristic, not a calibrated probability.
* `sync` identity is content-based: two distinct but byte-identical reports collapse to one. Twin state and the audit log are in-process only (durability is Layer 6).
* `mro.history_capacity`, `mro.history_window`, `mro.convergence_sla_s` and `mro.convergence_tolerance` are read but declared in `config/default.yaml`; they fall back to named module constants.
