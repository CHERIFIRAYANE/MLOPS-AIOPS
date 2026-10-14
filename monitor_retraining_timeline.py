#!/usr/bin/env python3
import subprocess
import json
from datetime import datetime
from pathlib import Path
import time

workspace = r"c:\Users\WINDOWS\Desktop\AiOPs"
timeline_file = Path(workspace) / "retraining_timeline.json"

timeline = {
    "initial_evaluation": {
        "timestamp": datetime.now().isoformat(),
        "event": "Started timestamped monitoring"
    },
    "degradation_detected": None,
    "sample_accumulation": [],
    "retraining_triggered": None,
    "post_retrain_evaluation": None
}

def run_cmd(cmd):
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    return result.stdout.strip()

def check_dataset_samples():
    try:
        cmd = 'kubectl exec -n aiops $(kubectl get pod -n aiops -l app=aiops-engine -o jsonpath="{.items[0].metadata.name}") -- wc -l /data/cleaned_dataset.csv 2>/dev/null'
        output = run_cmd(cmd)
        if output and output.isdigit():
            return int(output)

        local_csv = Path(workspace) / "data" / "cleaned_dataset.csv"
        if local_csv.exists():
            with open(local_csv) as f:
                return sum(1 for _ in f)
    except:
        pass
    return 0

def record_event(name, details=None):
    event = {"timestamp": datetime.now().isoformat(), "event": name}
    if details:
        event.update(details)
    return event

print("=" * 80)
print("RETRAINING TIMELINE MONITOR")
print("=" * 80)
init_ts = timeline['initial_evaluation']['timestamp']
print("\n[{}]".format(init_ts))
print("Initial evaluation completed (ROC-AUC=0.506, Accuracy=0.510)")
print("  -> Drift detected, but retraining blocked: samples=50 < required=200")

timeline["degradation_detected"] = record_event(
    "Performance degradation detected",
    {"roc_auc": 0.506, "accuracy": 0.510, "samples": 50}
)

print("\n[MONITORING] Waiting for 200 samples to trigger retraining...")
check_interval = 10
max_wait = 600
start_time = time.time()
last_count = 50

while (time.time() - start_time) < max_wait:
    current = check_dataset_samples()

    if current >= 50 and current != last_count:
        ts = datetime.now().isoformat()
        print("[{}] Samples: {}/200".format(ts, current))
        timeline["sample_accumulation"].append({"timestamp": ts, "count": current})
        last_count = current

    if current >= 200:
        print("\nSamples reached 200+! Triggering retraining...")
        timeline["retraining_triggered"] = record_event("Retraining triggered", {"samples": current})

        retrain_cmd = "cd {} && .venv/Scripts/python.exe aiops-engine/auto_retrain_pipeline.py".format(workspace)
        print("  Running: {}".format(retrain_cmd))
        output = run_cmd(retrain_cmd)
        print("  Retraining completed")

        # Wait for hot-reload
        time.sleep(3)

        # Evaluate retrained model
        eval_ts = datetime.now().isoformat()
        print("\n[{}] Evaluating retrained model...".format(eval_ts))
        eval_cmd = "cd {} && .venv/Scripts/python.exe monitoring/evaluate_current_model.py".format(workspace)
        eval_output = run_cmd(eval_cmd)

        metrics = {}
        for line in eval_output.split('\n'):
            if 'Accuracy:' in line:
                metrics['accuracy'] = float(line.split(':')[1].strip())
            elif 'Precision:' in line:
                metrics['precision'] = float(line.split(':')[1].strip())
            elif 'Recall:' in line:
                metrics['recall'] = float(line.split(':')[1].strip())
            elif 'F1-Score:' in line or 'F1-score:' in line:
                metrics['f1'] = float(line.split(':')[1].strip())
            elif 'ROC-AUC:' in line:
                metrics['roc_auc'] = float(line.split(':')[1].strip())

        timeline["post_retrain_evaluation"] = record_event("Post-retraining evaluation", metrics)

        print("\n" + "=" * 80)
        print("RESULTS COMPARISON")
        print("=" * 80)
        print("Metric          Before      After       Improvement")
        print("-" * 80)

        acc = metrics.get('accuracy', 0)
        prec = metrics.get('precision', 0)
        rec = metrics.get('recall', 0)
        f1 = metrics.get('f1', 0)
        roc = metrics.get('roc_auc', 0)

        print("Accuracy        0.510       {:6.3f}      {:+.3f}".format(acc, acc - 0.510))
        print("Precision       0.561       {:6.3f}      {:+.3f}".format(prec, prec - 0.561))
        print("Recall          0.542       {:6.3f}      {:+.3f}".format(rec, rec - 0.542))
        print("F1-Score        0.551       {:6.3f}      {:+.3f}".format(f1, f1 - 0.551))
        print("ROC-AUC         0.506       {:6.3f}      {:+.3f}".format(roc, roc - 0.506))
        print("=" * 80)

        break

    time.sleep(check_interval)

# Save timeline
with open(timeline_file, 'w') as f:
    json.dump(timeline, f, indent=2)
print("\nTimeline saved to: {}".format(timeline_file))
