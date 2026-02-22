#!/usr/bin/env python3
"""
Traffic Generator — Multi-scenario Locust load test.

Scenarios:
  1. NormalLoad   — steady background traffic  (weight=3)
  2. DDoSUser     — sudden high-freq spike      (weight=1)
  3. SlowUser     — keep connections open long  (weight=1)
  4. ErrorUser    — trigger echo-server errors  (weight=1)

MasterLoadShape cycles through 7 automatic phases,
changing user counts AND echo-server fault mode.
"""

import time
import logging
import requests as _requests
from locust import HttpUser, task, between, events, LoadTestShape

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

ECHO_HOST = "http://echo-server:5000"


def _set_mode(mode: str):
    """Tell the echo-server to switch fault-injection mode."""
    try:
        _requests.post(f"{ECHO_HOST}/mode", json={"mode": mode}, timeout=3)
        logger.info(f"[LoadShape] echo-server mode → {mode}")
    except Exception as exc:
        logger.warning(f"[LoadShape] Could not set mode {mode}: {exc}")


# ─── User classes ─────────────────────────────────────────────────────────────
class NormalUser(HttpUser):
    """Standard traffic: mix of /echo and /health."""
    wait_time = between(0.5, 2)
    weight = 3

    @task(8)
    def echo(self):
        self.client.get("/echo")

    @task(2)
    def health(self):
        self.client.get("/health")


class DDoSUser(HttpUser):
    """High-freq requests — simulate DDoS / traffic spike."""
    wait_time = between(0.01, 0.1)
    weight = 1

    @task
    def flood(self):
        self.client.get("/echo")


class SlowUser(HttpUser):
    """Slow client — long gaps between requests."""
    wait_time = between(5, 15)
    weight = 1

    @task
    def slow_request(self):
        with self.client.get("/echo", catch_response=True) as resp:
            if resp.status_code != 200:
                resp.failure(f"Unexpected status {resp.status_code}")


class ErrorUser(HttpUser):
    """Trigger error responses to stress error-rate metric."""
    wait_time = between(0.2, 1)
    weight = 1

    @task
    def trigger_error(self):
        with self.client.get("/echo", catch_response=True) as resp:
            if resp.status_code >= 500:
                resp.success()   # expected during error scenario


# ─── Load shape ───────────────────────────────────────────────────────────────
class MasterLoadShape(LoadTestShape):
    """
    7 phases. tick() returns (target_users, spawn_rate) or None to stop.
    Automatically sets the echo-server fault mode on phase transitions.
    """

    phases = [
        # (duration_s, users, spawn_rate, mode,     label)
        (60,   5,   2,   'normal', 'Warm-up'),
        (120,  20,  5,   'normal', 'Steady state'),
        (60,   120, 40,  'normal', 'DDoS burst'),
        (60,   10,  5,   'slow',   'Slow clients'),
        (60,   25,  8,   'error',  'Error flood'),
        (60,   3,   1,   'normal', 'Traffic drop'),
        (120,  15,  4,   'cpu',    'CPU spike'),
    ]

    _phase_idx: int = -1

    def tick(self):
        elapsed = self.get_run_time()

        # Loop forever: wrap elapsed into a repeating cycle
        total = sum(d for d, *_ in self.phases)
        elapsed = elapsed % total

        cumulative = 0
        target_phase = len(self.phases) - 1
        for i, (dur, *_) in enumerate(self.phases):
            cumulative += dur
            if elapsed < cumulative:
                target_phase = i
                break

        dur, users, spawn_rate, mode, label = self.phases[target_phase]

        if target_phase != self._phase_idx:
            self._phase_idx = target_phase
            logger.warning(
                f"\n[LoadShape] Phase {target_phase+1}/{len(self.phases)}: "
                f"{label} — {users} users, mode={mode}"
            )
            _set_mode(mode)

        return (users, spawn_rate)


# ─── Event listeners ──────────────────────────────────────────────────────────
@events.test_start.add_listener
def on_test_start(environment, **kwargs):
    logger.info("Multi-scenario load test started")
    for i, (dur, users, _, mode, label) in enumerate(MasterLoadShape.phases):
        logger.info(f"   Phase {i+1}: {label:20s} {dur:4d}s  {users:4d} users  mode={mode}")


@events.test_stop.add_listener
def on_test_stop(environment, **kwargs):
    logger.info("✅ Load test completed — resetting echo-server to normal mode")
    _set_mode('normal')
