# AIOps Platform - Quick Start Guide

Get the AIOps anomaly detection platform running in minutes.

---

## Table of Contents

1. [Fresh Computer Setup](#fresh-computer-setup)
2. [First-Time Deployment](#first-time-deployment)
3. [Daily Operations](#daily-operations)
4. [Common Commands](#common-commands)
5. [Monitoring & Logs](#monitoring--logs)
6. [Data Management](#data-management)
7. [Troubleshooting](#troubleshooting)

---

## Fresh Computer Setup

### Prerequisites

Before you start, ensure you have:

- **Docker Desktop** installed (includes Kubernetes)
  - Download: https://www.docker.com/products/docker-desktop
  - Version: 4.0+ recommended

- **Kubernetes enabled in Docker Desktop**
  - Open Docker Desktop Settings
  - Go to Settings → Kubernetes
  - Check "Enable Kubernetes"
  - Wait 2-3 minutes for cluster to start

- **kubectl configured** (comes with Docker Desktop)

### Verify Setup

```bash
# Check Docker
docker --version
# Expected: Docker version 24.0+

# Check Kubernetes
kubectl cluster-info
# Expected: Kubernetes control plane is running

# Check nodes
kubectl get nodes
# Expected: One node named "docker-desktop" with status Ready
```

---

## First-Time Deployment

### Step 1: Build Docker Images (5-10 minutes)

Your team has built custom Docker images. New computers don't have them yet.

```bash
# From project root: C:\Users\WINDOWS\Desktop\AiOPs

# Build echo-server (simulated application)
docker build -t aiops/echo-server:latest echo-server/

# Build traffic-gen (load generator)
docker build -t aiops/traffic-gen:latest traffic-gen/

# Build aiops-engine (ML pipeline)
docker build -t aiops/aiops-engine:latest aiops-engine/

# Verify all 3 images were created
docker images | grep aiops
# Should show:
#   aiops/echo-server       latest
#   aiops/traffic-gen       latest
#   aiops/aiops-engine      latest
```

**What each image contains:**

| Image                       | Purpose                                               | Size  | Build Time |
| --------------------------- | ----------------------------------------------------- | ----- | ---------- |
| `aiops/echo-server:latest`  | Flask HTTP server that simulates application behavior | 200MB | 2 min      |
| `aiops/traffic-gen:latest`  | Locust load generator (creates HTTP traffic)          | 250MB | 3 min      |
| `aiops/aiops-engine:latest` | ML pipeline (scikit-learn, pandas, prometheus_client) | 600MB | 5 min      |

**Build fails?**

```bash
# Make sure you're in project root directory
cd C:\Users\WINDOWS\Desktop\AiOPs
pwd  # Should show AiOPs folder

# If docker build fails: "dockerfile not found"
# Verify echo-server/Dockerfile exists
ls echo-server/Dockerfile
```

---

### Step 2: Deploy to Kubernetes (2-3 minutes)

```bash
# Apply all Kubernetes manifests
kubectl apply -f k8s/

# Expected output:
# namespace/aiops created
# configmap/prometheus-config created
# deployment.apps/prometheus created
# service/prometheus created
# ...
# deployment.apps/aiops-engine created
```

**What gets created:**

```
Namespace:    aiops (isolated environment)
Deployments:  echo-server, traffic-gen, aiops-engine, prometheus, grafana
Services:     Internal (port 5000, 8000, 8089, 9090) + External (30300, 30090)
PersistentVolumes: for Prometheus data, pipeline data
ConfigMaps:   Prometheus scrape config
```

---

### Step 3: Wait for Pods to Be Ready (2-3 minutes)

```bash
# Watch pods until all show "Running" and "1/1" ready
kubectl get pods -n aiops -w

# Expected output (wait for this):
NAME                           READY   STATUS    RESTARTS   AGE
aiops-engine-xxxxx             1/1     Running   0          2m
echo-server-xxxxx              1/1     Running   0          2m
traffic-gen-xxxxx              1/1     Running   0          2m
grafana-xxxxx                  1/1     Running   0          2m
prometheus-xxxxx               1/1     Running   0          2m
node-exporter-xxxxx            1/1     Running   0          2m

# Press Ctrl+C to exit watch mode
```

**If pods stuck in "Pending" or "ImagePullBackOff":**

```bash
# Check what's wrong
kubectl describe pod -n aiops <pod-name>

# Common issues:
# - "ImagePullBackOff" = Docker image not built yet
#   Run: docker build commands from Step 1
# - "Pending" = Not enough resources
#   Increase Docker Desktop memory: Settings → Resources → Memory 4GB+
```

---

### Step 4: Verify Deployment

```bash
# Check all pods are running
kubectl get pods -n aiops
# All should show: 1/1 Running

# Check services are accessible
kubectl get svc -n aiops
# Should show:
#   echo-server        5000/TCP
#   aiops-engine       8000/TCP
#   traffic-gen        8089/TCP
#   prometheus         9090/TCP
#   grafana            30300:30300/TCP

# Test Prometheus
curl http://localhost:9090
# Should respond with HTML page

# Test Grafana
curl http://localhost:30300
# Should respond with Grafana login page
```

---

## First Access

### Access Grafana Dashboard

```bash
# Open in browser
http://localhost:30300

# Or open via PowerShell
Start-Process "http://localhost:30300"

# Login credentials
Username: admin
Password: admin

# Navigate to dashboard
Home → Dashboards → AIOps → AIOps Platform
```

### View Real-Time Logs

```bash
# Watch aiops-engine predictions as they happen
kubectl logs -n aiops -f deployment/aiops-engine

# Expected output (every 5 seconds):
# window=1 score=0.1523 NORMAL
# window=2 score=0.1487 NORMAL
# window=3 score=0.1512 NORMAL
# window=15 score=0.8934 ANOMALY (DDoS)
#   Top causes: request_rate (0.41), network_rx (0.18)

# Press Ctrl+C to stop following logs
```

### Check Data Collection Progress

````bash
# See how many samples collected so far
kubectl exec -n aiops deployment/aiops-engine -- python -c "
## Daily Operations

### Start the Pipeline

```bash
# Deploy all pods
kubectl apply -f k8s/

# Wait for ready
kubectl get pods -n aiops -w
````

### Stop the Pipeline

**Option 1: Scale to 0 (keeps deployment, stops pods)**

```bash
kubectl scale deployment/aiops-engine -n aiops --replicas=0
kubectl scale deployment/echo-server -n aiops --replicas=0
kubectl scale deployment/traffic-gen -n aiops --replicas=0
```

**Option 2: Delete entire namespace (removes everything)**

```bash
kubectl delete namespace aiops
```

### Restart Individual Components

```bash
# Restart aiops-engine (ML pipeline)
kubectl rollout restart deployment/aiops-engine -n aiops

# Restart echo-server
kubectl rollout restart deployment/echo-server -n aiops

# Restart traffic-gen
kubectl rollout restart deployment/traffic-gen -n aiops

# Verify restart
kubectl rollout status deployment/aiops-engine -n aiops
```

---

## Common Commands

### Pod Management

```bash
# List all pods
kubectl get pods -n aiops

# Get detailed pod info
kubectl describe pod -n aiops <pod-name>

# View pod logs
kubectl logs -n aiops deployment/aiops-engine

# Follow logs in real-time
kubectl logs -n aiops -f deployment/aiops-engine

# Execute command in pod
kubectl exec -n aiops deployment/aiops-engine -- python --version

# Open shell in pod
kubectl exec -n aiops -it deployment/aiops-engine -- /bin/bash
# Type: exit to leave
```

### Service Access

```bash
# List all services
kubectl get svc -n aiops

# Port-forward to local machine (if NodePort doesn't work)
kubectl port-forward -n aiops svc/grafana 30300:3000

# Access via port-forward
http://localhost:30300
```

### Namespace Management

```bash
# List namespaces
kubectl get ns

# See all resources in aiops namespace
kubectl get all -n aiops

# Delete entire namespace (WARNING: cannot undo)
kubectl delete namespace aiops
```

---

## Monitoring & Logs

### Real-Time Anomaly Detection

```bash
# Watch predictions as they stream
kubectl logs -n aiops -f deployment/aiops-engine

# Output format:
# window=1 score=0.1523 NORMAL
# window=2 score=0.8934 ANOMALY (DDoS)
#   Top features: request_rate (0.41), network_rx (0.18)
# window=3 score=0.1487 NORMAL

# Understand the output:
# - window=N: which 5-second window (increments every 5s)
# - score=X: confidence 0.0-1.0 (higher = more anomalous)
# - Type: NORMAL, DDoS, SLOW, ERROR, or CPU
# - Top features: what caused the prediction
```

### Check Service Health

```bash
# Echo server endpoint
curl http://localhost:5000/health
# Response: {"status": "healthy"}

# Prometheus metrics
curl http://localhost:9090
# Response: Prometheus home page

# Grafana
curl http://localhost:30300
# Response: Grafana login page

# aiops-engine metrics
curl http://localhost:8000/metrics
# Response: Prometheus metrics about anomalies
```

### View Dashboard Panels

**In Grafana (http://localhost:30300):**

1. **HTTP Request Rate (req/s)**
   - Shows HTTP requests per second
   - Normal: 2-20 req/s (flat line)
   - DDoS phase: 60-120 req/s (spikes up)
   - What to watch: sudden spikes = traffic surge

2. **HTTP p95 / p99 Latency (ms)**
   - Shows tail response times
   - Normal: 200-250ms
   - Slow phase: 500-2000ms
   - What to watch: creeping latency = memory leak

3. **HTTP Error Rate**
   - Shows % of failed requests
   - Normal: <0.1%
   - Error phase: 50%
   - What to watch: >1% sustained = problem

4. **Anomaly Rate (rolling 60 windows)**
   - Shows % of time system is anomalous
   - Should match fault injection schedule
   - What to watch: high rate when no faults = false positive

5. **Raw Anomaly Score**
   - Model confidence: 0.0 (normal) to 1.0 (anomalous)
   - Smooth curve = consistent anomalies
   - Spiky curve = unpredictable patterns

6. **Root Cause Features**
   - Top 3 metrics driving anomaly prediction
   - DDoS: request_rate, network_rx high
   - Slow: latency, cpu_user high
   - What to watch: helps diagnose root causes

---

## Data Management

### Save Dataset Locally

```bash
# Get the current pod name
$POD = kubectl get pod -n aiops -l app=aiops-engine -o jsonpath='{.items[0].metadata.name}'

# Copy dataset from pod to local machine
kubectl cp aiops/${POD}:/data/cleaned_dataset.csv "data/live_dataset_$(Get-Date -Format 'yyyy-MM-dd_HHmm').csv"

# Verify file was saved
Get-ChildItem data/live_dataset_*.csv | Sort-Object Name -Descending | Select-Object Name, Length

# Example output:
# Name                              Length
# live_dataset_2026-02-22_1530.csv  1245632
# live_dataset_2026-02-21_2146.csv  893216
# live_dataset_2026-02-20_1400.csv  647382
```

### Check Dataset Size

```bash
# From inside the pod
kubectl exec -n aiops deployment/aiops-engine -- python -c "
import pandas as pd
import os

csv_path = '/data/cleaned_dataset.csv'
file_size_mb = os.path.getsize(csv_path) / 1024 / 1024
df = pd.read_csv(csv_path, parse_dates=['timestamp'])

print(f'File size: {file_size_mb:.2f} MB')
print(f'Total rows: {len(df)}')
print(f'Date range: {df[\"timestamp\"].min()} to {df[\"timestamp\"].max()}')
print(f'Elapsed time: {(df[\"timestamp\"].max() - df[\"timestamp\"].min()).total_seconds() / 3600:.1f} hours')
print(f'Anomalies: {df[\"is_anomaly\"].sum()} ({df[\"is_anomaly\"].mean()*100:.1f}%)')
"
```

### Collect Data Monitoring

**Real-time progress (updates every 5 seconds):**

```bash
kubectl exec -n aiops deployment/aiops-engine -- python -c "
import pandas as pd
df = pd.read_csv('/data/cleaned_dataset.csv', parse_dates=['timestamp'])
mins = (df['timestamp'].max() - df['timestamp'].min()).total_seconds() / 60
print(f'Rows: {len(df)}, Elapsed: {mins:.1f} min ({mins/60:.1f} hrs), Cycles: {mins/9:.0f}')
"
```

**Expected output:**

```
Rows: 2520, Elapsed: 1347.4 min (22.5 hrs), Cycles: 150
```

- **Rows**: Number of 5-second windows collected
- **Elapsed**: Total time in minutes and hours
- **Cycles**: Number of complete load cycles (9 minutes per cycle)

**Collection guidelines:**

- 100+ rows = enough for testing (5+ minutes)
- 500+ rows = good baseline (40+ minutes)
- 1000+ rows = solid dataset (3+ hours)
- 2000+ rows = excellent for generalization test (6+ hours)

---

## Retraining Workflow

### When to Retrain

Retrain the model when:

- You've collected 2+ days of new data
- Grafana shows drift score > 2.0
- Model accuracy drops (check precision/recall)

### Retrain Steps

```bash
# Step 1: Save current dataset
$POD = kubectl get pod -n aiops -l app=aiops-engine -o jsonpath='{.items[0].metadata.name}'
kubectl cp aiops/${POD}:/data/cleaned_dataset.csv "data/live_dataset_$(Get-Date -Format 'yyyy-MM-dd_HHmm').csv"

# Step 2: Prepare and label data
python training/prepare_dataset.py
# Creates: data/training_dataset.csv

# Step 3: Train new model
python training/train_model.py
# Expected output:
# Training: 2115 samples split into 1692 train / 423 test
# ROC-AUC: 0.995
# Precision: 0.97, Recall: 0.95

# Step 4: Copy model files
Copy-Item training/models/* aiops-engine/models/ -Force

# Step 5: Rebuild Docker image
docker build -t aiops/aiops-engine:latest aiops-engine/

# Step 6: Restart deployment (pulls new image)
kubectl rollout restart deployment/aiops-engine -n aiops

# Step 7: Verify new model loaded
kubectl logs -n aiops deployment/aiops-engine | grep "Model loaded"
# Expected: "Model loaded: 2.0 (1692 training samples, 96 features)"
```

---

## Troubleshooting

### Pods Not Starting

**Symptom:** Pods stuck in "Pending" or "CrashLoopBackOff"

```bash
# Check what's wrong
kubectl describe pod -n aiops <pod-name>

# Solutions:

# 1. Increase Docker Desktop resources
# Settings → Resources → Memory: 4GB → 6GB, CPU: 4 → 6

# 2. Check CPU/Memory usage
kubectl top nodes
kubectl top pods -n aiops

# 3. Check logs for errors
kubectl logs -n aiops <pod-name>

# 4. Delete namespace and redeploy
kubectl delete namespace aiops
kubectl apply -f k8s/
```

### Docker Image Not Found

**Symptom:** ImagePullBackOff error

```bash
# Images were not built
docker images | grep aiops
# Should show 3 images

# If empty, run build commands:
docker build -t aiops/echo-server:latest echo-server/
docker build -t aiops/traffic-gen:latest traffic-gen/
docker build -t aiops/aiops-engine:latest aiops-engine/

# Then redeploy:
kubectl delete namespace aiops
kubectl apply -f k8s/
```

### Grafana Shows "No Data"

**Symptom:** Grafana dashboard has no metrics

```bash
# Wait for data collection (takes 5-10 min to accumulate)
kubectl exec -n aiops deployment/aiops-engine -- python -c "
import pandas as pd
df = pd.read_csv('/data/cleaned_dataset.csv')
print(f'Rows collected: {len(df)}')
"

# If still no data, check pipeline is running:
kubectl logs -n aiops deployment/aiops-engine | tail -20

# If errors, check Prometheus is scraping:
curl http://localhost:9090/api/v1/targets
# Should show 3 targets: echo-server (up), aiops-engine (up), node-exporter (up)
```

### High Memory Usage

**Symptom:** Docker Desktop using 6+ GB RAM

```bash
# 1. Check pod memory
kubectl top pods -n aiops

# 2. Prometheus stores 30 days of data (takes 2-4 GB)
# This is normal. To clear:
kubectl delete pvc -n aiops prometheus-data

# 3. Reduce Prometheus retention
kubectl edit configmap -n aiops prometheus-config
# Change: retention: 30d → retention: 7d
kubectl rollout restart deployment/prometheus -n aiops
```

### Pipeline Logs Show Errors

**Symptom:** aiops-engine logs show exceptions

```bash
# View full error
kubectl logs -n aiops deployment/aiops-engine --all-containers=true

# Common errors:

# 1. "FileNotFoundError: cleaned_dataset.csv"
# Pipeline just started, wait 1-2 min for first data

# 2. "ConnectionRefusedError: Prometheus"
# Prometheus not ready yet, wait 2-3 min

# 3. "Model not loaded"
# Copy model to pod:
kubectl cp training/models/anomaly_detector.pkl aiops/$(kubectl get pod -n aiops -l app=aiops-engine -o jsonpath='{.items[0].metadata.name}'):/app/models/
kubectl rollout restart deployment/aiops-engine -n aiops
```

### Can't Connect to Grafana

**Symptom:** localhost:30300 refuses connection

```bash
# Check Grafana pod is running
kubectl get pod -n aiops -l app=grafana

# Check service
kubectl get svc -n aiops grafana

# Port-forward as alternative (if NodePort not working)
kubectl port-forward -n aiops svc/grafana 30300:3000
# Then access: http://localhost:30300

# Check logs
kubectl logs -n aiops deployment/grafana
```

---

## Reference

### File Locations

```
Project root: C:\Users\WINDOWS\Desktop\AiOPs

Key files:
├─ k8s/                          Kubernetes manifests (deploy here)
│  ├─ 01-namespace.yaml
│  ├─ 02-prometheus-config.yaml
│  ├─ 03-pvc.yaml
│  ├─ 04-prometheus.yaml
│  ├─ 05-echo-server.yaml
│  ├─ 06-traffic-gen.yaml
│  ├─ 07-aiops-engine.yaml
│  ├─ 08-node-exporter.yaml
│  ├─ 09-grafana.yaml
│  └─ 10-grafana-dashboard.yaml
│
├─ echo-server/
│  ├─ Dockerfile               Build this first
│  ├─ app.py                   Flask application
│  └─ requirements.txt
│
├─ traffic-gen/
│  ├─ Dockerfile
│  ├─ locustfile.py            Load generator
│  └─ requirements.txt
│
├─ aiops-engine/
│  ├─ Dockerfile
│  ├─ pipeline.py              ML scoring
│  ├─ models/
│  │  ├─ anomaly_detector.pkl
│  │  ├─ scaler.pkl
│  │  └─ feature_list.json
│  └─ requirements.txt
│
├─ training/
│  ├─ prepare_dataset.py       Format data for training
│  ├─ train_model.py           Train RandomForest
│  └─ models/                  Trained models (copy to aiops-engine/)
│
└─ data/
   ├─ cleaned_dataset.csv      (from pod, growing daily)
   ├─ live_dataset_2026-02-22_1530.csv
   ├─ live_dataset_2026-02-21_2146.csv
   └─ training_dataset.csv     (prepared data for retraining)
```

### Network Ports

```
Internal (Pod-to-Pod):
5000   - echo-server (HTTP)
8000   - aiops-engine (metrics)
8089   - traffic-gen (Locust UI)
9090   - prometheus (API)

External (Host Access):
30300  - Grafana (UI)
30090  - Prometheus (optional)
```

---

## Support

### Common Issues

| Issue                  | Solution                                       |
| ---------------------- | ---------------------------------------------- |
| Pods won't start       | Increase Docker memory to 6GB                  |
| Grafana has no data    | Wait 5-10 min, then refresh                    |
| Model retraining fails | Ensure training/ folder has script permissions |
| High disk usage        | Delete old csv files in data/                  |
| Logs show errors       | Run kubectl describe pod for details           |

### Getting Help

```bash
# Comprehensive system status
kubectl get all -n aiops

# Detailed pod information
kubectl describe pod -n aiops <pod-name>

# See recent events
kubectl get events -n aiops --sort-by='.lastTimestamp'

# Export pod logs
kubectl logs -n aiops deployment/aiops-engine > aiops_logs.txt

# Check resource limits
kubectl describe node docker-desktop
```

---

**Last Updated:** February 22, 2026  
**Version:** 2.0  
**Status:** Production Baseline
