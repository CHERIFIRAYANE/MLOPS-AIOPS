# Plateforme AIOps pour détection d'anomalies et réentraînement automatique

Ce dépôt présente une chaîne MLOps complète sur Kubernetes. Le projet montre la collecte de métriques, l'inférence en temps réel, la détection de dérive, le réentraînement automatique et la publication d'un pipeline CI/CD exploitable.

L'objectif n'est pas de faire joli sur un CV. L'objectif est de montrer un travail concret, lisible et vérifiable.

## Ce que contient le projet

- `aiops-engine/` pour l'inférence, le suivi des anomalies et l'export Prometheus.
- `echo-server/` pour simuler une application cible.
- `traffic-gen/` pour générer de la charge avec Locust.
- `training/` pour préparer les données et entraîner le modèle.
- `monitoring/` pour analyser les dérives et produire des rapports.
- `k8s/` pour le déploiement Kubernetes.

## Architecture

Le flux est simple:

1. `traffic-gen` envoie du trafic vers `echo-server`.
2. Prometheus collecte les métriques du service cible et du moteur AIOps.
3. `aiops-engine` lit les métriques, construit une fenêtre temporelle, calcule les features et produit une prédiction.
4. Un CronJob Kubernetes vérifie la dérive et peut déclencher un réentraînement.
5. Grafana affiche les métriques, les scores d'anomalie et l'état des jobs.

## CI et CD

Le dépôt inclut une vraie pipeline GitHub Actions:

- tests automatisés avec `pytest`
- contrôle de sécurité avec `bandit` et `pip-audit`
- scan de secrets avec `scripts/scan_secrets.py`
- build des images Docker pour les trois services
- déploiement continu via un workflow séparé `cd.yml`
- rollback automatique si les probes Kubernetes ne passent pas pendant le déploiement

Le déploiement est orchestré par `deploy.sh`. Le script applique les manifests, met à jour les images avec le tag construit, attend le statut des rollouts et lance un rollback si une étape échoue.

## Exécution locale

Prérequis:

- Docker Desktop avec Kubernetes activé, ou un cluster Kubernetes accessible
- `kubectl` configuré
- Python 3.12 pour les scripts et les tests

Pour démarrer localement:

```bash
git clone <repo-url>
cd AiOPs
docker build -t aiops-engine:local ./aiops-engine
docker build -t echo-server:local ./echo-server
docker build -t traffic-gen:local ./traffic-gen
kubectl apply -f k8s/
```

Pour lancer le déploiement complet avec le script:

```bash
bash deploy.sh latest
```

## Qualité et sécurité

Les modèles binaires `*.pkl` ne sont pas conservés dans le dépôt public. Ils sont régénérés localement ou stockés à part. Le dépôt garde aussi une `.gitignore` propre pour éviter les fichiers d'environnement, les logs et les artefacts runtime.

Un test de fumée est présent dans `tests/test_repo_smoke.py` pour vérifier que le README, la CI et le CD restent cohérents avec le dépôt.

## Validation rapide

```bash
python -m pytest -q tests/test_repo_smoke.py
bash -n deploy.sh
```

## À retenir

Ce projet met en avant une base sérieuse pour un poste DevSecOps ou MLOps: automatisation, sécurité, déploiement Kubernetes, rollback et documentation claire.
