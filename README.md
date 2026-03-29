# AIOps Anomaly Detection & Auto-Retraining Platform

A production-ready end-to-end Machine Learning Operations (MLOps) system that **automatically detects model degradation, triggers retraining, and deploys improved models** without manual intervention. Deployed on Kubernetes with automated drift detection, real-time inference, and comprehensive monitoring via Grafana.

**Current Model Performance:** ROC-AUC **95.61%** | Accuracy **88.31%** | 11,700+ samples collected

---

## Table of Contents

1. [System Architecture](#system-architecture)
2. [Key Features](#key-features)
3. [Quick Start](#quick-start)
4. [Project Structure](#project-structure)
5. [Drift Detection & Auto-Retraining](#drift-detection--auto-retraining)
6. [Problems Faced & Solutions](#problems-faced--solutions)
7. [Useful Commands](#useful-commands)
8. [Verification & Monitoring](#verification--monitoring)
9. [Technical Details](#technical-details)

---

## System Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                   AIOps ANOMALY DETECTION PLATFORM                       │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                            │
│ WORKLOAD GENERATION (Simulates traffic + anomalies)                     │
│ ┌────────────────────────┐         ┌──────────────────────┐             │
│ │   echo-server:5000     │←────────│   traffic-gen        │             │
│ │  Simulated HTTP app    │ (5s)    │  Load generator      │             │
│ │  Exposes metrics on    │         │  7-phase cycle:      │             │
│ │  /metrics endpoint     │         │   - warm-up (60s)    │             │
│ │                        │         │   - steady (120s)    │             │
│ └────────┬───────────────┘         │   - DDoS (60s)       │             │
│          │                         │   - slow (60s)       │             │
│          └─────────────────────────│   - errors (60s)     │             │
│                                    │   - drop (60s)       │             │
│ METRICS AGGREGATION                │   - CPU_spike (120s) │             │
│ ┌────────────────────────────────┐ └──────────────────────┘             │
│ │ Prometheus:9090 (5s scrape)    │ [Repeats every 540 seconds]         │
│ │ ┌──────────────────────────────┤                                      │
│ │ │ • Time-series database       │                                      │
│ │ │ • Scrapes from 4 endpoints   │                                      │
│ │ │ • Stores 40+ metric types    │                                      │
│ │ │ • 11,700+ samples × 96       │                                      │
│ │ │   features collected         │                                      │
│ │ └──────────────────────────────┘                                      │
│ └─────────────┬──────────────────────────────────────────────┘          │
│               │                                                           │
│ ML INFERENCE (Real-time anomaly detection)                              │
│ ┌──────────────▼────────────────────────────────────────────┐          │
│ │ aiops-engine:8000 (Python inference service)              │          │
│ │ ┌──────────────────────────────────────────────────────┐ │          │
│ │ │ Every 5 seconds:                                     │ │          │
│ │ │ 1. Query Prometheus API → collect metrics           │ │          │
│ │ │ 2. Maintain sliding window (12 samples = ~1 min)    │ │          │
│ │ │ 3. Engineer features (96 dimensions)                │ │          │
│ │ │ 4. Load trained RandomForest model                  │ │          │
│ │ │ 5. Predict: is_anomaly + anomaly_score             │ │          │
│ │ │ 6. Identify root cause (top-3 features)             │ │          │
│ │ │ 7. Persist to CSV (audit trail)                     │ │          │
│ │ │ 8. Export metrics to Prometheus                     │ │          │
│ │ └──────────────────────────────────────────────────────┘ │          │
│ └──────────────────────────────────────────────────────────┘          │
│               │                                                          │
│ DRIFT DETECTION (Every 5 minutes via CronJob)                          │
│ ┌──────────────▼────────────────────────────────────────────┐          │
│ │ detect_and_trigger_retrain.py (CronJob: */5 * * * *)     │          │
│ │ ┌──────────────────────────────────────────────────────┐ │          │
│ │ │ 1. Load trained model from /data/models/            │ │          │
│ │ │ 2. Extract last 24 hours of data from CSV           │ │          │
│ │ │ 3. Evaluate model performance (ROC-AUC)             │ │          │
│ │ │ 4. Check: ROC-AUC < 0.80? (drift detected)          │ │          │
│ │ │ 5. Check: Have 200+ samples? (sufficient data)      │ │          │
│ │ │ 6. Check: >24h since last retrain? (not too freq)   │ │          │
│ │ │ 7. If ALL conditions met → trigger retraining job   │ │          │
│ │ │ 8. Log everything to mlops_status.json              │ │          │
│ │ └──────────────────────────────────────────────────────┘ │          │
│ └──────────────────────────────────────────────────────────┘          │
│               │                                                          │
│ AUTO-RETRAINING (Triggered when drift detected)                        │
│ ┌──────────────▼────────────────────────────────────────────┐          │
│ │ auto_retrain_pipeline.py (Kubernetes Job)                 │          │
│ │ ┌──────────────────────────────────────────────────────┐ │          │
│ │ │ 1. Load recent data from CSV                        │ │          │
│ │ │ 2. Engineer features (same 96 dimensions)           │ │          │
│ │ │ 3. Split: 80% train / 20% test                      │ │          │
│ │ │ 4. Train new RandomForest (300 trees)               │ │          │
│ │ │ 5. Evaluate on test set (ROC-AUC, accuracy)         │ │          │
│ │ │ 6. Compare vs old model (improve = accept)          │ │          │
│ │ │ 7. Save to /data/models/anomaly_detector.pkl        │ │          │
│ │ │ 8. Service picks up new model automatically         │ │          │
│ │ └──────────────────────────────────────────────────────┘ │          │
│ └──────────────────────────────────────────────────────────┘          │
│               │                                                          │
│ VISUALIZATION (Human-friendly dashboards)                              │
│ ┌──────────────▼────────────────────────────────────────────┐          │
│ │ Grafana Dashboard                                          │          │
│ │ (visible at: http://localhost:3000)                      │          │
│ │ ┌──────────────────────────────────────────────────────┐ │          │
│ │ │ Panels included:                                     │ │          │
│ │ │ • HTTP Request Rate (req/s over time)               │ │          │
│ │ │ • Response Latency (p50/p95/p99 ms)                │ │          │
│ │ │ • Error Rate (% failed requests)                    │ │          │
│ │ │ • CPU Usage (%)                                     │ │          │
│ │ │ • ANOMALY SCORE (0-1, real-time prediction)        │ │          │
│ │ │ • Anomaly Type (DDoS/Slow/Error/CPU labeled)       │ │          │
│ │ │ • Root Cause Features (top-3 contributing)         │ │          │
│ │ │ • Retraining Status (Idle/Running/Success)         │ │          │
│ │ │ • Model Performance (ROC-AUC history)              │ │          │
│ │ └──────────────────────────────────────────────────────┘ │          │
│ └──────────────────────────────────────────────────────────┘          │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘

KUBERNETES INFRASTRUCTURE (Namespace: aiops)
├─ Deployments:
│  ├─ aiops-engine (inference + monitoring)
│  ├─ echo-server (load target)
│  ├─ traffic-gen (load generator)
│  ├─ prometheus (metrics DB)
│  ├─ grafana (dashboards)
│  └─ node-exporter (system metrics)
├─ CronJobs:
│  ├─ aiops-drift-detection (every 5 minutes)
│  │  Triggers retraining job if drift detected
├─ Persistent Volumes:
│  ├─ pipeline-data (1Gi) → /data/cleaned_dataset.csv
│  └─ aiops-shared (5Gi) → /shared/mlops_status.json
```

---

## Key Features

### ✅ Automated Drift Detection

- **Every 5 minutes**: Evaluates model performance on recent data
- **ROC-AUC threshold: 0.80** - If model performance drops below, triggers retraining
- **Comprehensive logging**: Every check is logged to `mlops_status.json` for audit trail

### ✅ Intelligent Auto-Retraining

- **Data-aware gates**: Only retrains if:
  - Drift detected (ROC-AUC < 0.80)
  - ≥ 200 samples collected (prevents training on too few samples)
  - ≥ 24 hours since last retrain (prevents thrashing)
- **Automatic deployment**: New model hot-reloads in production service
- **Safety net**: Falls back to old model if new model worse

### ✅ Real-Time Inference

- **5-second latency**: Processes metrics window → features → prediction → metrics export
- **96 features**: Comprehensive statistics extracted from raw metrics
- **Root cause analysis**: Shows top-3 features causing anomaly flag
- **Adaptive scoring**: Returns both binary classification and probability score

### ✅ Production Monitoring

- **Prometheus integration**: 40+ metric types scraped & stored
- **Grafana dashboards**: Real-time visualization of metrics & anomalies
- **Status tracking**: `/shared/mlops_status.json` tracks all drift/retrain events

### ✅ Fully Automated MLOps Pipeline

- **CronJob-based drift detection**: No manual intervention needed
- **Kubernetes-native retraining**: Uses K8s Jobs for scalable training
- **Audit trail**: Complete history of all checks, retrains, and model versions
- **Production-safe**: Validates improvements before deployment

---

## Quick Start

### Prerequisites

- Docker Desktop with Kubernetes enabled
- kubectl configured to access Docker Desktop cluster
- 8GB+ RAM recommended

### Deploy in 2 Commands

```bash
# 1. Clone the repository
git clone <repo-url>
cd AiOPs

# 2. Deploy to Kubernetes
kubectl apply -f k8s/

# 3. Wait for pods to stabilize (2-3 minutes)
kubectl get pods -n aiops -w

# 4. Access Grafana Dashboard
kubectl port-forward -n aiops svc/grafana 3000:3000
# Open http://localhost:3000 (username: admin / password: admin)
```

### Verify Everything Works

```bash
# Check all pods are Running
kubectl get pods -n aiops

# Tail logs from inference service
kubectl logs -n aiops deployment/aiops-engine -f

# Check drift detection logs (runs every 5 minutes)
kubectl logs -n aiops cronjob/aiops-drift-detection

# Verify CSV data is growing
kubectl exec -n aiops deployment/aiops-engine -- wc -l /data/cleaned_dataset.csv

# View latest model metrics
kubectl exec -n aiops deployment/aiops-engine -- cat /shared/mlops_status.json | grep -i "roc_auc\|accuracy"
```

---

## Project Structure

```
AiOPs/
├── README.md                           # This file - Production overview
├── aiops-engine/
│   ├── pipeline.py                     # Real-time inference service
│   ├── detect_and_trigger_retrain.py   # Drift detection (every 5 min via CronJob)
│   ├── auto_retrain_pipeline.py        # Auto-retraining orchestration
│   ├── model_monitor.py                # Prometheus metrics exporter
│   ├── mlops_status_exporter.py        # Audit trail & status tracking
│   ├── Dockerfile
│   ├── requirements.txt
│   └── models/feature_list.json
├── echo-server/                        # Mock HTTP service
│   ├── app.py
│   └── Dockerfile
├── traffic-gen/                        # Load generator (Locust)
│   ├── locustfile.py
│   └── Dockerfile
├── monitoring/                         # Data exploration scripts
│   ├── drift_analysis.py
│   ├── evaluate_current_model.py
│   └── get_data_for_retraining.py
├── training/                           # Initial model training
│   ├── prepare_dataset.py
│   └── train_model.py
└── k8s/                                # Kubernetes manifests
    ├── 01-namespace.yaml
    ├── 02-prometheus-config.yaml
    ├── 03-pvc.yaml
    ├── 04-prometheus.yaml
    ├── 05-echo-server.yaml
    ├── 06-traffic-gen.yaml
    ├── 07-aiops-engine.yaml
    ├── 08-node-exporter.yaml
    ├── 09-grafana.yaml
    ├── 13-drift-detection-cronjob.yaml
    ├── 14-retraining-job.yaml
    ├── 15-grafana-mlops-dashboard.yaml
    └── 16-mlops-config.yaml
```

---

## Drift Detection & Auto-Retraining

### Architecture

Every 5 minutes, `aiops-drift-detection` CronJob checks if the model needs retraining:

```
┌─────────────────────────────────────────┐
│ Load saved model from persistent volume │
└──────────────────┬──────────────────────┘
                   ↓
┌─────────────────────────────────────────┐
│ Extract data from last 24 hours         │
│ Filter: timestamp >= (now - 24h)        │
└──────────────────┬──────────────────────┘
                   ↓
┌─────────────────────────────────────────┐
│ Evaluate model on 24h window            │
│ Calculate: ROC-AUC, Accuracy, Precision │
└──────────────────┬──────────────────────┘
                   ↓
┌─────────────────────────────────────────┐
│ Check all retraining gates:             │
│                                          │
│ Gate 1: Drift detected?                 │
│   Is ROC-AUC < 0.80?                   │
│                                          │
│ Gate 2: Sufficient samples?             │
│   Are there >= 200 samples?             │
│                                          │
│ Gate 3: Rate limiting?                  │
│   Is it > 24h since last retrain?      │
│                                          │
│ ALL gates must be YES for retraining    │
└──────────────────┬──────────────────────┘
                   ↓
          ┌────────┴────────┐
          ↓                 ↓
    [Drift Found]    [No Drift/Gates Blocked]
          ↓                 ↓
   Trigger Job        Log to mlops_status.json
         ↓
┌─────────────────────────────────────────┐
│ auto_retrain_pipeline.py runs:          │
│ 1. Load recent data                     │
│ 2. Train new model                      │
│ 3. Evaluate on test set                 │
│ 4. Deploy if better than current        │
│ 5. Service hot-reloads automatically    │
└─────────────────────────────────────────┘
```

### Code Example

```python
# From detect_and_trigger_retrain.py
def check_drift(self):
    # Step 1: Load trained model
    model = joblib.load(self.model_path)

    # Step 2: Get last 24 hours of data
    df = self._extract_last_24h()  # Filters: timestamp >= (now - 24h)

    # Step 3: Evaluate performance
    roc_auc = self._evaluate_model(model, df)  # Calculates ROC-AUC

    # Step 4: Check all gates
    drift_detected = roc_auc < 0.80              # Gate 1
    enough_samples = len(df) >= 200              # Gate 2
    old_enough = self._hours_since_retrain() > 24  # Gate 3

    # Step 5: Trigger if all gates pass
    if drift_detected and enough_samples and old_enough:
        logger.info("🔄 Triggering retraining...")
        self._launch_retraining_job()
    else:
        logger.info(f"✓ Model health good. ROC-AUC={roc_auc:.4f}")
```

---

## Problems Faced & Solutions

### Problem 1: "Why isn't the model retraining?"

**What We Observed:**

- Drift detection showed score stuck at ~54% for hours
- Retraining status remained "Idle"
- Console shows "No data available from last 24h"

**Root Cause:**

- Local PC was paused for 2 days
- When rebooted, only 175 samples had been collected in the window
- `MIN_SAMPLES_FOR_RETRAIN=200` blocked training as a safety gate

**Solution:**

- Added comprehensive debug logging to `_extract_last_24h()` method showing:
  - Total rows loaded
  - Raw timestamp samples
  - Cutoff time (24h ago UTC)
  - Min/max timestamps in data
  - Filtered row count after time filtering
- Verified system correctly accumulated 250→445 samples when running continuously
- System CORRECTLY blocked retraining on insufficient data (safety feature)

**Lesson:** The implementation of the the safety gates are intentional features to prevent overfitting on small datasets. The system was working as designed.

### Problem 2: "CronJob job shows 0 samples but deployment sees 250+"

**What We Observed:**

- Manual drift detection job from CronJob template showed "No data available from last 24h"
- But the same CSV mounted on deployment pod had 250+ samples
- Both used identical `pipeline-data` PVC

**Root Cause:**

- Docker image was cached with old code
- CronJob was using old Python script without debug logging
- Kubernetes uses `imagePullPolicy: IfNotPresent`, so doesn't auto-update local images

**Solution:**

1. Rebuilt Docker image without cache:
   ```bash
   docker build --no-cache -t aiops-engine:latest .
   ```
2. Deleted pods to force new image pull:
   ```bash
   kubectl delete pod -n aiops -l app=aiops-engine
   ```
3. Redeployed with updated code:
   ```bash
   kubectl apply -f k8s/
   ```
4. Verified new code by checking logs for debug output

**Lesson:** to always rebuild without cache after code changes in development. We Considered using `imagePullPolicy: Always` during iteration, `IfNotPresent` for production stability.

### Problem 3: "Storage running low - CSV is 17.8 MB taking too much space"

**What We Observed:**

- PC storage nearly full
- CSV at 11,700 rows × 96 features ≈ 17.8 MB
- Docker images consuming 20+ GB

**Root Cause:**

- Docker cached 36 images with layers
- 9.957 GB build cache from iterations
- CSV data intentionally growing (needed for model evaluation)

**Solution:**

1. Cleaned Docker storage (NOT the CSV):

   ```bash
   docker system prune -a --volumes -f
   ```

   - Freed ~24.9 GB (73% of image storage)
   - Freed ~9.957 GB build cache
   - Kept only 18 active images needed for system

2. Kept CSV intact for:
   - Audit trail (production-critical)
   - Retraining data source (more samples = better models)
   - Historical analysis (drift tracking across weeks)

3. We could optionally add data retention later:
   ```python
   # Keep only last 30 days of data
   retention_cutoff = datetime.utcnow() - timedelta(days=30)
   ```

**Lesson:** A docker cleanup is often better than deleting active data. We opted to use storage cleanup regularly. CSV is an asset, not a liability.

---

## Useful Commands

### Deployment & Status

```bash
# Overall status
kubectl get all -n aiops

# Watch deployments in real-time
kubectl get pods -n aiops -w

# Detailed pod info (debugging init failures)
kubectl describe pod -n aiops <pod-name>

# Check resource usage
kubectl top pods -n aiops
```

### Logs & Debugging

```bash
# Real-time logs from inference service
kubectl logs -n aiops deployment/aiops-engine -f

# Last 100 lines from a pod
kubectl logs -n aiops deployment/aiops-engine --tail=100

# Logs from all containers in pod (useful if multiple containers)
kubectl logs -n aiops <pod-name> --all-containers=true

# If pod crashed, see previous logs
kubectl logs -n aiops <pod-name> --previous
```

### Manual Drift Detection

```powershell
# Trigger drift detection immediately (normally every 5 min)
$timestamp = (Get-Date).ToUniversalTime().ToString('yyyyMMddHHmmss')
kubectl create job --from=cronjob/aiops-drift-detection manual-check-$timestamp -n aiops

# Wait for it to complete
Start-Sleep -Seconds 30

# Check results (Windows PowerShell)
kubectl logs -n aiops -l job-name=manual-check-$timestamp --tail=50
```

### Data Access

```powershell
# Check CSV row count
kubectl exec -n aiops deployment/aiops-engine -- wc -l /data/cleaned_dataset.csv
# OR on Windows: kubectl exec -n aiops deployment/aiops-engine -- sh -c "cat /data/cleaned_dataset.csv | wc -l"

# View last 5 rows
kubectl exec -n aiops deployment/aiops-engine -- tail -5 /data/cleaned_dataset.csv

# Get model metrics (Windows PowerShell)
kubectl exec -n aiops deployment/aiops-engine -- cat /shared/mlops_status.json | Select-String "roc_auc|accuracy"

# Download status file locally
kubectl cp aiops/$(kubectl get pod -n aiops -l app=aiops-engine -o jsonpath='{.items[0].metadata.name}'):/shared/mlops_status.json ./backup.json
```

### Configuration Changes

```powershell
# View CronJob schedule (Windows PowerShell)
kubectl get cronjob aiops-drift-detection -n aiops -o yaml | Select-String -Pattern "schedule"

# Temporarily change drift threshold (demo only)
kubectl set env cronjob/aiops-drift-detection DRIFT_THRESHOLD=0.70 -n aiops

# Reset to default
kubectl set env cronjob/aiops-drift-detection DRIFT_THRESHOLD=0.80 -n aiops
```

### Cleanup

```bash
# Delete entire namespace (WARNING: loses data)
kubectl delete namespace aiops

# Clean Docker storage (frees ~25 GB)
docker system prune -a --volumes -f

# Remove only unused images (safer)
docker image prune -a
```

---

## Verification & Monitoring

### ✅ Step 1: Verify All Pods Running

```bash
kubectl get pods -n aiops

NAME                                   READY   STATUS    AGE
aiops-engine-79dcc495db-pxsng          1/1     Running   5m
echo-server-65d4f95bdd-p284r           1/1     Running   5m
grafana-65d9685c5b-86n7z               1/1     Running   5m
prometheus-7d544d7c46-hr62c            1/1     Running   5m
node-exporter-28r54                    1/1     Running   5m
traffic-gen-fbb8f7d85-rjnhn            1/1     Running   5m
```

**Expected:** All pods `Running` with `READY 1/1` ✓

### ✅ Step 2: Verify Data Collection

```bash
kubectl exec -n aiops deployment/aiops-engine -- wc -l /data/cleaned_dataset.csv

11701
```

**Expected:** Growing row count (started ~100, now 11,700+) ✓

### ✅ Step 3: Check Model Performance

```powershell
# Windows PowerShell
kubectl exec -n aiops deployment/aiops-engine -- cat /shared/mlops_status.json | Select-String -Pattern "roc_auc"

# Output:
# "current_roc_auc": 0.9561
# "latest_roc_auc": 0.9561
```

**Expected:** ROC-AUC > 0.80, currently **95.61%** ✓

### ✅ Step 4: Verify Drift Detection Working

```powershell
# Windows PowerShell
kubectl logs -n aiops -l app=aiops-engine | Select-String -Pattern "drift|samples" | Select-Object -Last 5

# Output:
# CSV loaded: 11701 total rows
# After filtering for last 24h: 445 rows
# Model performance: ROC-AUC=0.9561
# Drift detected: False (threshold: 0.80)
# ✓ Model health is good, no action needed
```

**Expected:** Drift False, ROC-AUC > 0.80, samples > 200 ✓

### ✅ Step 5: View Live Dashboard

```bash
kubectl port-forward -n aiops svc/grafana 3000:3000
# Open http://localhost:3000
# Login: admin / admin
# Dashboard: "AIOps Platform"
```

**Expected panels:**

- HTTP Request Rate (spikes during DDoS phase)
- Response Latency (p95 milliseconds)
- Error Rate (jumps during error injection phase)
- System CPU Usage (spikes during CPU phase)
- **ANOMALY SCORE** (0-1, peaks during anomalies)
- Anomaly Type (NORMAL/DDoS/SLOW/ERROR/CPU labels)
- Root Cause Features (top-3 contributing metrics)

### ✅ Step 6: Verify Prometheus API

```bash
kubectl port-forward -n aiops svc/prometheus 9090:9090
# Open http://localhost:9090/targets
```

**Expected targets UP:**

- echo-server
- aiops-engine
- prometheus
- node-exporter
- kubelet-cadvisor

### ✅ Step 7: Manual Drift Check

```powershell
# Windows PowerShell
kubectl create job --from=cronjob/aiops-drift-detection test-drift-now -n aiops
Start-Sleep -Seconds 30
kubectl logs -n aiops -l job-name=test-drift-now

# Expected output:
# CSV loaded: 11701 total rows
# After filtering for last 24h: 445 rows
# Model performance: ROC-AUC=0.9561, Accuracy=0.8831
# Drift detected: False
# ✓ Model health is good
```

---

## Technical Details

### Feature Engineering (96 Dimensions)

For each 5-second metric window, we maintain a sliding 12-sample history (~1 minute) and calculate:

**16 raw metric types × 6 statistics per metric = 96 features**

**Raw metrics:**
1-6: HTTP metrics (rate, p50/p95/p99 latency, error rate, trend)
7-12: System metrics (CPU, memory, load, network in/out)
13-16: Container/Node metrics (storage, disk I/O)

**Statistics per metric:**

- Mean, StdDev, Min, Max, P95, Trend (linear slope)

### Model Architecture

**Algorithm:** RandomForestClassifier (scikit-learn)

- **Trees:** 300
- **Max depth:** 20
- **Min samples/leaf:** 2
- **Class weights:** Balanced

**Training data:**

- **Samples:** 1,692 labeled windows
- **Features:** 96 dimensions
- **Labels:** 0 (normal) / 1 (anomaly)
- **Split:** 80% train, 20% test

**Performance:**

- ROC-AUC: 0.9561
- Accuracy: 0.8831
- Precision: High (few false positives)
- Recall: High (catches most anomalies)

### Kubernetes Configuration

**Namespace:** aiops
**Storage:**

- Pipeline data: 1Gi PVC
- Shared status: 5Gi PVC

**CronJob schedule:** `*/5 * * * *` (every 5 minutes)
**Retraining frequency:** On-demand (when drift detected)
**Data retention:** Indefinite (audit trail important)

---

## Extending the System

### Add New Metrics

1. Edit `echo-server/app.py` to expose new `/metrics`
2. Add scrape config to `k8s/02-prometheus-config.yaml`
3. Update feature engineering in `aiops-engine/pipeline.py`
4. Retrain model with new features

### Change Model Algorithm

1. Replace RandomForest with your model in `auto_retrain_pipeline.py`
2. Update performance metrics calculation
3. Rebuild and test with: `docker build --no-cache -t aiops-engine:latest .`
4. Restart pods: `kubectl delete pod -n aiops -l app=aiops-engine`

### Adjust Drift Thresholds

1. Edit `k8s/13-drift-detection-cronjob.yaml`
2. Update `DRIFT_THRESHOLD`, `MIN_SAMPLES_FOR_RETRAIN`, `MIN_HOURS_BETWEEN_RETRAIN`
3. Apply: `kubectl apply -f k8s/13-drift-detection-cronjob.yaml`

### Custom Grafana Dashboard

1. Export current: Settings → Save as → Export JSON
2. Edit `grafana-mlops-dashboard.json`
3. Reimport to Grafana

---

## Support

**Q: Model stuck, nothing changes for hours?**
A: Check if 200+ samples collected. If <200, system blocks retrain intentionally.

**Q: 0 samples error but deployment sees data?**
A: Docker image cached. Run: `docker build --no-cache -t aiops-engine:latest aiops-engine/` and delete pods.

**Q: Grafana shows no data?**
A: Wait 2-3 minutes for Prometheus scrapes. Check targets at `http://localhost:9090/targets`

**Q: How to change drift threshold?**
A: Update `DRIFT_THRESHOLD` in `k8s/13-drift-detection-cronjob.yaml` and reapply.

---

**Status:** Production-Ready ✅
**Last Updated:** March 29, 2026
**Model Version:** v2.0 (RandomForest, 300 estimators)
**Samples Collected:** 11,700+
**Current ROC-AUC:** 95.61%

**Hello legends, it's Rayane Again, I tried my best to summarize the project for easy reproduction, The retrain logic took me some time to understand and to implement correctly without errors, especially since I've been constantly running out of storage in my local pc, which complicated the dev process. Next iteration of would be on the traffic genetor, by using probablistic methods to randomize the traffic by add more unpredictability to challenge the model more, and make it more robust, and force it to generalize better**
