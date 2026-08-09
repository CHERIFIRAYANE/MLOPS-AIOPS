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

# Plateforme AIOps : détection d'anomalies et réentraînement automatique

Ce dépôt contient un projet de démonstration d'une chaîne MLOps déployée
sur Kubernetes. L'objectif est de présenter le flux complet : collecte de
métriques, inférence en temps réel, détection de dérive, réentraînement
automatique et visualisation.

Principes clés
---------------

- Collecte de métriques via Prometheus.
- Inférence en temps réel dans `aiops-engine`, qui exporte des métriques
   d'anomalie vers Prometheus.
- Détection de dérive périodique via un CronJob Kubernetes. Si plusieurs
   conditions sont réunies, un job de réentraînement est déclenché.
- Les modèles binaires sont exclus du contrôle de version pour garder le
   dépôt léger.

Prérequis
---------

- Docker Desktop (Kubernetes activé) ou un cluster Kubernetes accessible.
- `kubectl` configuré pour accéder au cluster.
- Python 3.11 pour exécuter les scripts de formation et d'inférence.

Installation rapide en local
---------------------------

1. Cloner le dépôt :

```bash
git clone <repo-url>
cd AiOPs
```

2. Construire les images Docker locales :

```bash
docker build -t aiops-engine:local ./aiops-engine
docker build -t echo-server:local ./echo-server
docker build -t traffic-gen:local ./traffic-gen
```

3. Déployer les manifests Kubernetes :

```bash
kubectl apply -f k8s/
kubectl get pods -n aiops -w
```

4. Pour accéder à Grafana :

```bash
kubectl port-forward -n aiops svc/grafana 3000:3000
# ouvrir http://localhost:3000 (identifiants par défaut fournis localement)
```

Remarques sur les modèles
-------------------------

Les fichiers `*.pkl` contenant les modèles et les scalers sont exclus du
contrôle de version. Pour régénérer les modèles localement :

```bash
python training/train_model.py
```

ou copier vos modèles compilés dans :

- `aiops-engine/models/`
- `training/models/`

CI et sécurité
---------------

Une pipeline CI GitHub Actions est incluse dans `.github/workflows/ci.yml`.
Elle exécute linting, analyses de sécurité statique et construit les images
Docker sans les pousser vers un registre. Un script `scripts/scan_secrets.py`
permet de vérifier rapidement l'absence de secrets avant publication.

Structure principale du dépôt
-----------------------------

- `aiops-engine/` : service d'inférence et d'export Prometheus.
- `training/` : scripts pour préparer les données et entraîner le modèle.
- `echo-server/` : application HTTP simulée pour générer trafic.
- `traffic-gen/` : générateur de charge (Locust).
- `k8s/` : manifests Kubernetes pour déploiement local.
- `monitoring/` : scripts d'analyse et génération de rapports.

Comment contribuer
------------------

1. Créer une branche pour vos modifications.
2. Exécuter `scripts/scan_secrets.py` avant de pousser pour éviter d'exposer
    des secrets.
3. Ouvrir une Pull Request vers `main`.

Contact
-------

Pour questions techniques ou instructions de déploiement supplémentaires,
ouvrez une issue dans le dépôt.


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
# Plateforme AIOps : détection d'anomalies et réentraînement automatique

Ce dépôt contient un projet de démonstration d'une chaîne MLOps déployée
sur Kubernetes. L'objectif est de montrer l'ensemble du flux : collecte de
métriques, inférence en temps réel, détection de dérive, réentraînement
automatique et visualisation.

Principes clés
---------------

- Collecte de métriques via Prometheus.
- Inférence en temps réel dans `aiops-engine`, qui exporte des métriques
   d'anomalie vers Prometheus.
- Détection de dérive périodique via un CronJob Kubernetes. Si plusieurs
   conditions sont réunies, un job de réentraînement est déclenché.
- Les modèles binaires ne sont pas inclus dans le dépôt final. Ils sont
   générés ou fournis séparément afin de garder le dépôt léger.

Prérequis
---------

- Docker Desktop (Kubernetes activé) ou un cluster Kubernetes accessible.
- `kubectl` configuré pour accéder au cluster.
- Python 3.11 pour exécuter les scripts de formation et d'inférence.

Installation rapide en local
---------------------------

1. Cloner le dépôt :

```bash
git clone <repo-url>
cd AiOPs
```

2. Construire les images Docker locales :

```bash
docker build -t aiops-engine:local ./aiops-engine
docker build -t echo-server:local ./echo-server
docker build -t traffic-gen:local ./traffic-gen
```

3. Déployer les manifests Kubernetes :

```bash
kubectl apply -f k8s/
kubectl get pods -n aiops -w
```

4. Pour accéder à Grafana :

```bash
kubectl port-forward -n aiops svc/grafana 3000:3000
# ouvrir http://localhost:3000 (identifiants par défaut fournis localement)
```

Remarques sur les modèles
-------------------------

Les fichiers `*.pkl` contenant les modèles et les scalers sont exclus du
contrôle de version. Pour régénérer les modèles localement :

```bash
python training/train_model.py
```

ou copier vos modèles compilés dans :

- `aiops-engine/models/`
- `training/models/`

CI et sécurité
---------------

Une pipeline CI GitHub Actions est incluse dans `.github/workflows/ci.yml`.
Elle exécute linting, analyses de sécurité statique et construit les images
Docker sans les pousser vers un registre. Un script `scripts/scan_secrets.py`
permet de vérifier rapidement l'absence de secrets avant publication.

Structure principale du dépôt
-----------------------------

- `aiops-engine/` : service d'inférence et d'export Prometheus.
- `training/` : scripts pour préparer les données et entraîner le modèle.
- `echo-server/` : application HTTP simulée pour générer trafic.
- `traffic-gen/` : générateur de charge (Locust).
- `k8s/` : manifests Kubernetes pour déploiement local.
- `monitoring/` : scripts d'analyse et génération de rapports.

Comment contribuer
------------------

1. Créer une branche pour vos modifications.
2. Exécuter `scripts/scan_secrets.py` avant de pousser pour éviter d'exposer
    des secrets.
3. Ouvrir une Pull Request vers `main`.

Contact
-------

Pour questions techniques ou instructions de déploiement supplémentaires,
ouvrez une issue dans le dépôt.


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
