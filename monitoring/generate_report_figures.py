"""
Generate two report-ready visualizations for the retraining results section.

Outputs:
- report_figures/fig1_gate_timeline.png
- report_figures/fig2_ml_performance.png

Data sources:
- /shared/mlops_status.json via kubectl exec
- monitoring/evaluate_active_model.py --hours 24
"""

from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import matplotlib.dates as mdates
import matplotlib.pyplot as plt


WORKSPACE = Path(r"c:\Users\WINDOWS\Desktop\AiOPs")
FIG_DIR = WORKSPACE / "report_figures"
STATUS_CMD = [
    "kubectl",
    "exec",
    "-n",
    "aiops",
    "deployment/aiops-engine",
    "--",
    "cat",
    "/shared/mlops_status.json",
]
PYTHON_EXE = str(WORKSPACE / ".venv" / "Scripts" / "python.exe")
ACTIVE_EVAL_CMD = [PYTHON_EXE, str(WORKSPACE / "monitoring" / "evaluate_active_model.py"), "--hours", "24"]


@dataclass
class Metrics:
    accuracy: float
    precision: float
    recall: float
    f1: float
    roc_auc: float
    cm: Tuple[int, int, int, int]  # TN, FP, FN, TP


def run(cmd: List[str], timeout: int = 120) -> str:
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if result.returncode != 0:
        raise RuntimeError(f"Command failed: {' '.join(cmd)}\n{result.stderr}")
    return result.stdout


def load_status() -> Dict:
    text = run(STATUS_CMD, timeout=90)
    return json.loads(text)


def parse_active_metrics(text: str) -> Metrics:
    # Parse "Active deployed model metrics (recomputed now)" block.
    block_start = text.find("Active deployed model metrics (recomputed now)")
    if block_start == -1:
        raise ValueError("Could not find active-model metrics block in evaluate_active_model output.")

    block = text[block_start:]

    def f(key: str) -> float:
        m = re.search(rf"{key}\s*:\s*([0-9]+\.[0-9]+)", block)
        if not m:
            raise ValueError(f"Missing metric: {key}")
        return float(m.group(1))

    m = re.search(r"CM \(TN,FP,FN,TP\): \((\d+),\s*(\d+),\s*(\d+),\s*(\d+)\)", block)
    if not m:
        raise ValueError("Missing confusion matrix in active-model block")

    return Metrics(
        accuracy=f("Accuracy"),
        precision=f("Precision"),
        recall=f("Recall"),
        f1=f("F1-score"),
        roc_auc=f("ROC-AUC"),
        cm=(int(m.group(1)), int(m.group(2)), int(m.group(3)), int(m.group(4))),
    )


def parse_dt(ts: str) -> datetime:
    # Status timestamps are ISO-8601 without timezone suffix.
    return datetime.fromisoformat(ts)


def extract_before_accuracy(status: Dict, retrain_start: datetime) -> Optional[float]:
    events = status.get("events_log", [])
    # Find nearest model_health_updated at or before retraining start.
    best_dt = None
    best_acc = None
    for e in events:
        if e.get("type") != "model_health_updated":
            continue
        ts = e.get("timestamp")
        if not ts:
            continue
        dt = parse_dt(ts)
        if dt <= retrain_start:
            acc = e.get("details", {}).get("accuracy")
            if acc is None:
                continue
            if best_dt is None or dt > best_dt:
                best_dt = dt
                best_acc = float(acc)
    return best_acc


def collect_timeline_points(status: Dict, start: datetime, end: datetime) -> List[Dict]:
    points: List[Dict] = []
    allowed = {"drift_detected", "model_health_updated", "no_drift"}
    for e in status.get("events_log", []):
        et = e.get("type")
        if et not in allowed:
            continue
        ts = e.get("timestamp")
        if not ts:
            continue
        dt = parse_dt(ts)
        if not (start <= dt <= end):
            continue

        details = e.get("details", {})
        roc = details.get("roc_auc")
        if roc is None:
            continue

        points.append(
            {
                "dt": dt,
                "type": et,
                "roc": float(roc),
                "samples": details.get("samples"),
            }
        )

    points.sort(key=lambda x: x["dt"])
    return points


def plot_gate_timeline(
    points: List[Dict],
    retrain_start: datetime,
    retrain_end: datetime,
    threshold: float,
    out_file: Path,
) -> None:
    plt.style.use("seaborn-v0_8-whitegrid")
    fig, ax = plt.subplots(figsize=(12, 5))

    color_map = {
        "drift_detected": "#D32F2F",
        "model_health_updated": "#1565C0",
        "no_drift": "#2E7D32",
    }

    for t in ["drift_detected", "model_health_updated", "no_drift"]:
        subset = [p for p in points if p["type"] == t]
        if not subset:
            continue
        ax.plot(
            [p["dt"] for p in subset],
            [p["roc"] for p in subset],
            marker="o",
            linewidth=2,
            markersize=6,
            label=t.replace("_", " ").title(),
            color=color_map[t],
        )

    # Threshold and retraining interval.
    ax.axhline(threshold, color="#FF8F00", linestyle="--", linewidth=2, label=f"Gate threshold ({threshold:.2f})")
    ax.axvspan(retrain_start, retrain_end, color="#CE93D8", alpha=0.25, label="Retraining window")

    # Annotate sample counts for drift/no_drift points.
    for p in points:
        if p["samples"] is not None and p["type"] in {"drift_detected", "no_drift"}:
            ax.annotate(
                f"n={p['samples']}",
                (p["dt"], p["roc"]),
                xytext=(0, 8),
                textcoords="offset points",
                ha="center",
                fontsize=8,
                color="#424242",
            )

    ax.set_title("Gate Logic and Retraining Timeline (ROC-AUC vs Time)", fontsize=13, fontweight="bold")
    ax.set_ylabel("ROC-AUC")
    ax.set_xlabel("Timestamp (UTC)")
    ax.set_ylim(0.0, 1.05)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M:%S"))
    fig.autofmt_xdate()
    ax.legend(loc="lower right", frameon=True)

    fig.tight_layout()
    fig.savefig(out_file, dpi=300)
    plt.close(fig)


def plot_ml_performance(before_acc: float, before_auc: float, after: Metrics, out_file: Path) -> None:
    plt.style.use("seaborn-v0_8-whitegrid")
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 5), gridspec_kw={"width_ratios": [1.15, 1]})

    # Left: before vs after grouped bars.
    metrics = ["Accuracy", "ROC-AUC", "Precision", "Recall", "F1-score"]
    before_vals = [before_acc, before_auc, 0.0, 0.0, 0.0]
    after_vals = [after.accuracy, after.roc_auc, after.precision, after.recall, after.f1]

    x = list(range(len(metrics)))
    width = 0.35
    ax1.bar([i - width / 2 for i in x], before_vals, width=width, color="#EF9A9A", label="Pre-retrain")
    ax1.bar([i + width / 2 for i in x], after_vals, width=width, color="#81C784", label="Post-retrain")

    for i, v in enumerate(after_vals):
        ax1.text(i + width / 2, v + 0.02, f"{v:.3f}", ha="center", va="bottom", fontsize=8)
    for i, v in enumerate(before_vals[:2]):
        ax1.text(i - width / 2, v + 0.02, f"{v:.3f}", ha="center", va="bottom", fontsize=8)

    ax1.set_xticks(x)
    ax1.set_xticklabels(metrics, rotation=20)
    ax1.set_ylim(0, 1.1)
    ax1.set_title("Pre vs Post Retraining Metrics", fontsize=12, fontweight="bold")
    ax1.legend()

    # Right: post-retrain confusion matrix heatmap.
    tn, fp, fn, tp = after.cm
    cm = [[tn, fp], [fn, tp]]
    im = ax2.imshow(cm, cmap="Blues")
    for r in range(2):
        for c in range(2):
            ax2.text(c, r, str(cm[r][c]), ha="center", va="center", fontsize=11, color="#0D47A1")

    ax2.set_xticks([0, 1])
    ax2.set_yticks([0, 1])
    ax2.set_xticklabels(["Pred Normal", "Pred Anomaly"])
    ax2.set_yticklabels(["Actual Normal", "Actual Anomaly"])
    ax2.set_title("Post-Retrain Confusion Matrix", fontsize=12, fontweight="bold")
    fig.colorbar(im, ax=ax2, fraction=0.046, pad=0.04)

    fig.tight_layout()
    fig.savefig(out_file, dpi=300)
    plt.close(fig)


def main() -> None:
    FIG_DIR.mkdir(parents=True, exist_ok=True)

    status = load_status()
    retraining = status.get("retraining", {})
    model_health = status.get("model_health", {})

    retrain_start = parse_dt(retraining["started_at"])
    retrain_end = parse_dt(retraining["completed_at"])
    threshold = float(model_health.get("threshold_critical", 0.8))

    # Before metrics from retraining metadata + nearest pre-start health event.
    before_auc = float(retraining.get("previous_model_roc_auc", 0.0))
    before_acc = extract_before_accuracy(status, retrain_start)
    if before_acc is None:
        before_acc = 0.0

    # After metrics from active-model evaluator.
    active_eval_output = run(ACTIVE_EVAL_CMD, timeout=180)
    after = parse_active_metrics(active_eval_output)

    # Timeline around retraining (15 min before to 30 min after).
    window_start = retrain_start - timedelta(minutes=15)
    window_end = retrain_start + timedelta(minutes=30)
    points = collect_timeline_points(status, window_start, window_end)

    fig1 = FIG_DIR / "fig1_gate_timeline.png"
    fig2 = FIG_DIR / "fig2_ml_performance.png"

    plot_gate_timeline(points, retrain_start, retrain_end, threshold, fig1)
    plot_ml_performance(before_acc, before_auc, after, fig2)

    print("Generated figures:")
    print(f"- {fig1}")
    print(f"- {fig2}")
    print("\nNumbers used:")
    print(f"Pre-retrain: accuracy={before_acc:.4f}, roc_auc={before_auc:.4f}")
    print(
        "Post-retrain (active model): "
        f"accuracy={after.accuracy:.4f}, precision={after.precision:.4f}, "
        f"recall={after.recall:.4f}, f1={after.f1:.4f}, roc_auc={after.roc_auc:.4f}"
    )


if __name__ == "__main__":
    main()
