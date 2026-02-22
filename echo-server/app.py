#!/usr/bin/env python3
"""
Echo Server — Flask app providing HTTP metrics for Prometheus + fault injection.

Endpoints:
  GET  /          → health summary JSON
  GET  /echo      → simulated workload (latency depends on current mode)
  GET  /health    → k8s liveness probe
  GET  /metrics   → Prometheus metrics (via prometheus_client)
  POST /mode      → set fault-injection mode
                    body: {"mode": "normal"|"slow"|"error"|"cpu"}
  GET  /mode      → get current mode
"""

import time
import random
import os
import threading
import math
from flask import Flask, jsonify, request, Response
from prometheus_client import (
    Counter, Histogram, Gauge, generate_latest, CollectorRegistry, REGISTRY
)

app = Flask(__name__)

# ─── Prometheus metrics ────────────────────────────────────────────────────────
http_requests_total = Counter(
    'http_requests_total',
    'Total HTTP requests',
    ['method', 'endpoint', 'status']
)
http_request_duration_seconds = Histogram(
    'http_request_duration_seconds',
    'HTTP request latency in seconds',
    buckets=(0.001, 0.01, 0.05, 0.1, 0.5, 1.0, 2.5, 5.0, 10.0)
)
CURRENT_MODE_GAUGE = Gauge(
    'echo_server_mode',
    'Current operating mode (0=normal,1=slow,2=error,3=cpu)',
    ['mode']
)
REQUEST_ERRORS = Counter(
    'echo_server_errors_total',
    'Total intentional error responses',
    ['status_code']
)

# ─── Request instrumentation ──────────────────────────────────────────────────
@app.before_request
def before_request():
    request.start_time = time.time()

@app.after_request
def after_request(response):
    duration = time.time() - request.start_time
    http_request_duration_seconds.observe(duration)
    http_requests_total.labels(
        method=request.method,
        endpoint=request.path,
        status=response.status_code
    ).inc()
    return response

# ─── Mode state ───────────────────────────────────────────────────────────────
MODES = ('normal', 'slow', 'error', 'cpu')
_state_lock = threading.Lock()
_current_mode = 'normal'

for m in MODES:
    CURRENT_MODE_GAUGE.labels(mode=m).set(1 if m == 'normal' else 0)


def get_mode() -> str:
    with _state_lock:
        return _current_mode


def set_mode(new_mode: str):
    global _current_mode
    if new_mode not in MODES:
        raise ValueError(f"Unknown mode '{new_mode}'. Valid: {MODES}")
    with _state_lock:
        _current_mode = new_mode
    for m in MODES:
        CURRENT_MODE_GAUGE.labels(mode=m).set(1 if m == new_mode else 0)


def _cpu_burn(seconds: float):
    """Burn CPU for `seconds` in the current thread."""
    end = time.time() + seconds
    x = 1.0
    while time.time() < end:
        x = math.sqrt(x + random.random())


# ─── Routes ───────────────────────────────────────────────────────────────────
@app.route('/')
def index():
    return jsonify({'service': 'echo-server', 'mode': get_mode(), 'status': 'ok'})


@app.route('/health')
def health():
    return jsonify({'status': 'healthy', 'mode': get_mode()})


@app.route('/echo', methods=['GET', 'POST'])
def echo():
    mode = get_mode()
    start = time.time()

    if mode == 'normal':
        delay = random.uniform(0.001, 0.5)
        time.sleep(delay)
        status = 200

    elif mode == 'slow':
        delay = random.uniform(2.0, 8.0)
        time.sleep(delay)
        status = 200

    elif mode == 'error':
        roll = random.random()
        if roll < 0.5:
            time.sleep(random.uniform(0.001, 0.05))
            REQUEST_ERRORS.labels(status_code='500').inc()
            return Response('Internal Server Error', status=500)
        elif roll < 0.8:
            time.sleep(random.uniform(0.001, 0.05))
            REQUEST_ERRORS.labels(status_code='503').inc()
            return Response('Service Unavailable', status=503)
        else:
            time.sleep(random.uniform(0.001, 0.2))
            status = 200

    elif mode == 'cpu':
        burn_time = random.uniform(0.2, 0.6)
        _cpu_burn(burn_time)
        status = 200

    else:
        time.sleep(random.uniform(0.001, 0.5))
        status = 200

    elapsed = time.time() - start
    return jsonify({'echo': 'ok', 'mode': mode, 'latency_ms': round(elapsed * 1000, 2)}), status


@app.route('/mode', methods=['GET'])
def get_mode_route():
    return jsonify({'mode': get_mode()})


@app.route('/mode', methods=['POST'])
def set_mode_route():
    data = request.get_json(silent=True) or {}
    new_mode = data.get('mode', '').strip()
    try:
        set_mode(new_mode)
        return jsonify({'mode': new_mode, 'status': 'ok'})
    except ValueError as e:
        return jsonify({'error': str(e)}), 400


@app.route('/metrics', methods=['GET'])
def metrics():
    """Prometheus metrics endpoint"""
    return Response(generate_latest(REGISTRY), mimetype='text/plain; version=0.0.4; charset=utf-8')


if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    app.run(host='0.0.0.0', port=port, threaded=True, debug=False)
