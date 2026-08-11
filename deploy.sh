#!/bin/bash
# AIOps Kubernetes Deployment Script
# Builds Docker images and deploys all components to Kubernetes with rollback on failed health probes

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
REGISTRY="aiops"  # Local registry name (Docker Desktop)
IMAGE_TAG="${1:-latest}"
NAMESPACE="aiops"

rollback() {
    echo ""
    echo "❌ Deployment failed, rolling back affected deployments..."
    kubectl rollout undo deployment/aiops-engine -n "$NAMESPACE" || true
    kubectl rollout undo deployment/echo-server -n "$NAMESPACE" || true
    kubectl rollout undo deployment/traffic-gen -n "$NAMESPACE" || true
    echo "Rollback requested."
}

trap rollback ERR

echo "========================================"
echo "🚀 AIOps Kubernetes Deployment"
echo "========================================"

# Step 1: Build Docker Images
echo ""
echo "📦 Step 1: Building Docker images..."
echo ""

components=(
    "echo-server"
    "traffic-gen"
    "aiops-engine"
)

for component in "${components[@]}"; do
    echo "Building $component..."
    docker build -t "$REGISTRY/$component:$IMAGE_TAG" "$PROJECT_ROOT/$component"
    echo "✅ $component built successfully"
done

echo ""
echo "📦 All images built!"
docker images | grep "$REGISTRY"

# Step 2: Create namespace
echo ""
echo "🏗️  Step 2: Creating Kubernetes namespace..."
kubectl apply -f "$SCRIPT_DIR/01-namespace.yaml"
echo "✅ Namespace created"

# Step 3: Deploy Prometheus
echo ""
echo "🔍 Step 3: Deploying Prometheus..."
kubectl apply -f "$SCRIPT_DIR/02-prometheus-config.yaml"
kubectl apply -f "$SCRIPT_DIR/03-pvc.yaml"
kubectl apply -f "$SCRIPT_DIR/04-prometheus.yaml"
echo "✅ Prometheus deployed"
echo "⏳ Waiting for Prometheus to be ready..."
kubectl wait --for=condition=ready pod -l app=prometheus -n aiops --timeout=300s

# Step 4: Deploy Echo Server
echo ""
echo "🎯 Step 4: Deploying Echo Server..."
kubectl apply -f "$SCRIPT_DIR/05-echo-server.yaml"
echo "✅ Echo Server deployed"
kubectl set image deployment/echo-server echo-server="$REGISTRY/echo-server:$IMAGE_TAG" -n "$NAMESPACE"
echo "⏳ Waiting for Echo Server to be ready..."
kubectl wait --for=condition=ready pod -l app=echo-server -n aiops --timeout=60s
kubectl rollout status deployment/echo-server -n "$NAMESPACE" --timeout=90s

# Step 5: Deploy Traffic Generator
echo ""
echo "🔄 Step 5: Deploying Traffic Generator..."
kubectl apply -f "$SCRIPT_DIR/06-traffic-gen.yaml"
echo "✅ Traffic Generator deployed"
kubectl set image deployment/traffic-gen locust="$REGISTRY/traffic-gen:$IMAGE_TAG" -n "$NAMESPACE"
echo "⏳ Waiting for Traffic Generator to be ready..."
sleepfor=120
echo "Waiting $sleepfor seconds for Locust to start generating load..."
sleep $sleepfor
kubectl rollout status deployment/traffic-gen -n "$NAMESPACE" --timeout=120s

# Step 6: Deploy AIOps Engine
echo ""
echo "🧠 Step 6: Deploying AIOps Engine (Data Pipeline)..."
kubectl apply -f "$SCRIPT_DIR/07-aiops-engine.yaml"
echo "✅ AIOps Engine deployed"
kubectl set image deployment/aiops-engine aiops-engine="$REGISTRY/aiops-engine:$IMAGE_TAG" -n "$NAMESPACE"
kubectl set image cronjob/aiops-drift-detection drift-detector="$REGISTRY/aiops-engine:$IMAGE_TAG" -n "$NAMESPACE"
kubectl rollout status deployment/aiops-engine -n "$NAMESPACE" --timeout=180s

echo "⏳ Verifying health probes..."
kubectl wait --for=condition=available deployment/aiops-engine -n "$NAMESPACE" --timeout=180s
kubectl wait --for=condition=ready pod -l app=aiops-engine -n "$NAMESPACE" --timeout=180s

echo ""
echo "========================================"
echo "✨ Deployment Complete!"
echo "========================================"
echo ""
echo "📊 Cluster Status:"
kubectl get all -n aiops --no-headers

echo ""
echo "🔗 Service Endpoints:"
echo "  - Prometheus: http://localhost:9090"
echo "  - Echo Server: http://localhost:5000"
echo ""
echo "📈 Monitor logs:"
echo "  kubectl logs -f deployment/aiops-engine -n aiops"
echo ""
echo "💾 Get cleaned dataset:"
echo "  kubectl cp aiops/<pod-name>:/data/cleaned_dataset.csv ./cleaned_dataset.csv"
echo ""
echo "🗑️  Cleanup:"
echo "  kubectl delete namespace aiops"
