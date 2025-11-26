#!/bin/bash

# Script de déploiement pour Docker Desktop Kubernetes
# Ce script déploie Qdrant, Redis et le chart Helm pour shopifake-recommender

set -e

NAMESPACE="default"
CHART_DIR="./chart"

echo "🚀 Déploiement de shopifake-recommender sur Docker Desktop Kubernetes"
echo "=========================================="

# Vérifier que kubectl est disponible
if ! command -v kubectl &> /dev/null; then
    echo "❌ kubectl n'est pas installé. Veuillez l'installer d'abord."
    exit 1
fi

# Vérifier que le cluster Kubernetes est accessible
if ! kubectl cluster-info &> /dev/null; then
    echo "❌ Impossible de se connecter au cluster Kubernetes."
    echo "   Assurez-vous que Docker Desktop Kubernetes est activé et en cours d'exécution."
    exit 1
fi

echo "✅ Connexion au cluster Kubernetes réussie"

# Étape 1: Déployer Qdrant
echo ""
echo "📦 Étape 1: Déploiement de Qdrant..."
if kubectl get deployment shopifake-qdrant -n $NAMESPACE &> /dev/null; then
    echo "   Qdrant existe déjà, mise à jour..."
    kubectl apply -f $CHART_DIR/qdrant-deployment.yaml
else
    echo "   Création de Qdrant..."
    kubectl apply -f $CHART_DIR/qdrant-deployment.yaml
fi

# Attendre que Qdrant soit prêt
echo "   Attente que Qdrant soit prêt..."
kubectl wait --for=condition=ready pod -l app=shopifake-qdrant \
    -n $NAMESPACE --timeout=120s || echo "   ⚠️  Timeout, mais continuons..."

# Étape 2: Déployer Redis
echo ""
echo "📦 Étape 2: Déploiement de Redis..."
if kubectl get deployment shopifake-redis -n $NAMESPACE &> /dev/null; then
    echo "   Redis existe déjà, mise à jour..."
    kubectl apply -f $CHART_DIR/redis-deployment.yaml
else
    echo "   Création de Redis..."
    kubectl apply -f $CHART_DIR/redis-deployment.yaml
fi

# Attendre que Redis soit prêt
echo "   Attente que Redis soit prêt..."
kubectl wait --for=condition=ready pod -l app=shopifake-redis \
    -n $NAMESPACE --timeout=120s || echo "   ⚠️  Timeout, mais continuons..."

# Étape 3: Construire l'image Docker
echo ""
echo "🐳 Étape 3: Construction de l'image Docker..."
cd ..
if docker build -t shopifake-recommender:latest .; then
    echo "   ✅ Image construite avec succès"
    
    # Charger l'image dans le cluster Kubernetes de Docker Desktop
    echo "   Chargement de l'image dans le cluster..."
    if command -v docker &> /dev/null; then
        # Pour Docker Desktop, on peut utiliser directement l'image locale
        echo "   ✅ Image disponible localement (Docker Desktop utilise les images locales)"
    fi
else
    echo "   ❌ Échec de la construction de l'image"
    exit 1
fi

# Étape 4: Déployer avec Helm
echo ""
echo "📦 Étape 4: Déploiement avec Helm..."

# Vérifier que Helm est installé
if ! command -v helm &> /dev/null; then
    echo "   ❌ Helm n'est pas installé. Installation..."
    echo "   Veuillez installer Helm: https://helm.sh/docs/intro/install/"
    exit 1
fi

cd $CHART_DIR

# Vérifier si le release existe déjà
if helm list -n $NAMESPACE | grep -q "shopifake-recommender"; then
    echo "   Mise à jour du déploiement existant..."
    helm upgrade shopifake-recommender . \
        -f values-local.yaml \
        -n $NAMESPACE \
        --wait \
        --timeout 5m
else
    echo "   Installation du nouveau déploiement..."
    helm install shopifake-recommender . \
        -f values-local.yaml \
        -n $NAMESPACE \
        --wait \
        --timeout 5m
fi

echo ""
echo "✅ Déploiement terminé!"
echo ""
echo "📊 Statut des pods:"
kubectl get pods -n $NAMESPACE | grep -E "shopifake|NAME"

echo ""
echo "🌐 Accès au service:"
echo "   - Recommender API: http://localhost:30080"
echo "   - Qdrant: http://localhost:6333 (port-forward nécessaire)"
echo "   - Redis: localhost:6379 (port-forward nécessaire)"
echo ""
echo "Pour accéder à Qdrant:"
echo "   kubectl port-forward svc/shopifake-qdrant 6333:6333 -n $NAMESPACE"
echo ""
echo "Pour accéder à Redis:"
echo "   kubectl port-forward svc/shopifake-redis 6379:6379 -n $NAMESPACE"
echo ""
echo "Pour voir les logs:"
echo "   kubectl logs -f deployment/shopifake-recommender-services -n $NAMESPACE"
echo "   kubectl logs -f deployment/shopifake-recommender-queue -n $NAMESPACE"

