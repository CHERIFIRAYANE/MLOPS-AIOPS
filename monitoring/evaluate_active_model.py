"""
Evaluate the currently deployed model directly inside the aiops-engine pod.

Why this script exists:
- `evaluate_current_model.py` reads stored `is_anomaly` values from CSV, which can
  include predictions produced by older model versions.
- This script recomputes predictions with the active model artifact in `/data/models`
  so results represent the model that is currently deployed.

Usage:
  python monitoring/evaluate_active_model.py            # default: last 24 hours
  python monitoring/evaluate_active_model.py --hours 1  # last 1 hour
"""

import argparse
import json
import subprocess
from typing import Dict, Any


POD_EVAL_CODE = r'''
import json
import numpy as np
import pandas as pd
import joblib
from datetime import timedelta
from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score, roc_auc_score, confusion_matrix

PHASES = [
    (60, 0),   # warm-up
    (120, 0),  # steady
    (60, 1),   # ddos
    (60, 1),   # slow
    (60, 1),   # error
    (60, 0),   # traffic_drop
    (120, 1),  # cpu_spike
]
CYCLE_SECONDS = sum(p[0] for p in PHASES)


def make_labels(ts_series):
    start_time = ts_series.min()
    labels = []
    for ts in ts_series:
        phase_pos = ((ts - start_time).total_seconds()) % CYCLE_SECONDS
        cumulative = 0
        label = 0
        for duration, phase_label in PHASES:
            if cumulative <= phase_pos < cumulative + duration:
                label = phase_label
                break
            cumulative += duration
        labels.append(label)
    return np.array(labels, dtype=int)


def metrics(y_true, y_pred_binary, y_pred_score):
    cm = confusion_matrix(y_true, y_pred_binary)
    tn, fp, fn, tp = cm.ravel()
    return {
        'accuracy': float(accuracy_score(y_true, y_pred_binary)),
        'precision': float(precision_score(y_true, y_pred_binary, zero_division=0)),
        'recall': float(recall_score(y_true, y_pred_binary, zero_division=0)),
        'f1': float(f1_score(y_true, y_pred_binary, zero_division=0)),
        'roc_auc': float(roc_auc_score(y_true, y_pred_score)),
        'confusion_matrix': {'tn': int(tn), 'fp': int(fp), 'fn': int(fn), 'tp': int(tp)},
    }


def main(hours_back):
    df = pd.read_csv('/data/cleaned_dataset.csv')
    df['timestamp'] = pd.to_datetime(df['timestamp'], errors='coerce')
    df = df.dropna(subset=['timestamp']).copy()

    max_ts = df['timestamp'].max()
    cutoff = max_ts - timedelta(hours=hours_back)
    recent = df[df['timestamp'] >= cutoff].copy()

    # Build ground truth from recent window start (important: slice first, then label)
    y_true = make_labels(recent['timestamp'])

    # Stored runtime predictions in CSV (may include old model outputs)
    stored_score = recent['is_anomaly'].astype(float).to_numpy()
    stored_pred = (stored_score > 0.5).astype(int)
    stored_metrics = metrics(y_true, stored_pred, stored_score)

    # Active model predictions recomputed from current deployed artifacts
    model_bundle = joblib.load('/data/models/anomaly_detector.pkl')
    scaler = joblib.load('/data/models/scaler.pkl')

    if isinstance(model_bundle, dict) and 'classifier' in model_bundle:
        clf = model_bundle['classifier']
        feature_cols = model_bundle.get('feature_cols')
    else:
        clf = model_bundle
        feature_cols = None

    excluded = {'timestamp', 'phase', 'is_anomaly', 'anomaly_score', 'iso_score', 'anomaly_type'}
    if not feature_cols:
        feature_cols = [c for c in recent.columns if c not in excluded and np.issubdtype(recent[c].dtype, np.number)]

    for c in feature_cols:
        if c not in recent.columns:
            recent[c] = 0.0

    X = recent[feature_cols].replace([np.inf, -np.inf], 0.0).fillna(0.0)
    X_scaled = scaler.transform(X)

    # Remove any non-finite rows post-scaling to avoid NaN in ROC-AUC.
    finite_mask = np.isfinite(X_scaled).all(axis=1)
    X_scaled = X_scaled[finite_mask]
    y_true = y_true[finite_mask]

    model_score = clf.predict_proba(X_scaled)[:, 1]
    model_score = np.where(np.isfinite(model_score), model_score, 0.0)
    model_pred = (model_score > 0.5).astype(int)
    model_metrics = metrics(y_true, model_pred, model_score)

    print(json.dumps({
        'rows_total': int(len(df)),
        'rows_recent': int(len(recent)),
        'timestamp_min': str(df['timestamp'].min()),
        'timestamp_max': str(df['timestamp'].max()),
        'hours_back': float(hours_back),
        'stored_prediction_metrics': stored_metrics,
        'active_model_metrics': model_metrics,
    }))


if __name__ == '__main__':
    import sys
    h = float(sys.argv[1]) if len(sys.argv) > 1 else 24.0
    main(h)
'''


def run_pod_eval(hours: float) -> Dict[str, Any]:
    cmd = [
        'kubectl', 'exec', '-n', 'aiops', 'deployment/aiops-engine', '--',
        'python', '-c', POD_EVAL_CODE, str(hours)
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=180)

    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or 'Pod evaluation command failed')

    text = result.stdout.strip()
    if not text:
        raise RuntimeError('Empty output from pod evaluation')

    # kubectl may prepend informational lines; parse last JSON-looking line
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    payload = json.loads(lines[-1])
    return payload


def print_block(title: str, m: Dict[str, Any]) -> None:
    cm = m['confusion_matrix']
    print(f"\n{title}")
    print('-' * len(title))
    print(f"Accuracy : {m['accuracy']:.4f}")
    print(f"Precision: {m['precision']:.4f}")
    print(f"Recall   : {m['recall']:.4f}")
    print(f"F1-score : {m['f1']:.4f}")
    print(f"ROC-AUC  : {m['roc_auc']:.4f}")
    print(f"CM (TN,FP,FN,TP): ({cm['tn']}, {cm['fp']}, {cm['fn']}, {cm['tp']})")


def main() -> None:
    parser = argparse.ArgumentParser(description='Evaluate active model inside aiops-engine pod.')
    parser.add_argument('--hours', type=float, default=24.0, help='Recent window size in hours (default: 24)')
    args = parser.parse_args()

    payload = run_pod_eval(args.hours)

    print('=== ACTIVE MODEL REPRESENTATIVENESS CHECK ===')
    print(f"Rows total in CSV : {payload['rows_total']}")
    print(f"Rows in recent set: {payload['rows_recent']} (last {payload['hours_back']}h)")
    print(f"Time range total  : {payload['timestamp_min']} -> {payload['timestamp_max']}")

    print_block('Stored CSV prediction metrics (historical runtime outputs)', payload['stored_prediction_metrics'])
    print_block('Active deployed model metrics (recomputed now)', payload['active_model_metrics'])


if __name__ == '__main__':
    main()
