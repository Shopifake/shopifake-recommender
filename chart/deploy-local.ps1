# Script de déploiement pour Docker Desktop Kubernetes (PowerShell)
# Ce script déploie Qdrant, Redis et le chart Helm pour shopifake-recommender

$ErrorActionPreference = 'Stop'
$NAMESPACE = 'py-test'
# Sauvegarder le répertoire courant (chart) et le répertoire parent
$SCRIPT_DIR = Split-Path -Parent $MyInvocation.MyCommand.Path
$CHART_DIR = $SCRIPT_DIR
$PARENT_DIR = Split-Path -Parent $CHART_DIR

Write-Host '🚀 Déploiement de shopifake-recommender sur Docker Desktop Kubernetes' -ForegroundColor Cyan
Write-Host '==========================================' -ForegroundColor Cyan

# Vérifier que kubectl est disponible
if (-not (Get-Command kubectl -ErrorAction SilentlyContinue)) {
    Write-Host '❌ kubectl n''est pas installé. Veuillez l''installer d''abord.' -ForegroundColor Red
    exit 1
}

# Vérifier que le cluster Kubernetes est accessible
try {
    kubectl cluster-info | Out-Null
    Write-Host '✅ Connexion au cluster Kubernetes réussie' -ForegroundColor Green
} catch {
    Write-Host '❌ Impossible de se connecter au cluster Kubernetes.' -ForegroundColor Red
    Write-Host '   Assurez-vous que Docker Desktop Kubernetes est activé et en cours d''exécution.' -ForegroundColor Yellow
    exit 1
}

# Créer le namespace s'il n'existe pas
Write-Host ''
Write-Host ('📁 Vérification du namespace ' + $NAMESPACE + '...') -ForegroundColor Cyan
$ErrorActionPreference = 'SilentlyContinue'
$namespaceCheck = kubectl get namespace $NAMESPACE 2>$null
$ErrorActionPreference = 'Stop'
if (-not $namespaceCheck) {
    Write-Host ('   Création du namespace ' + $NAMESPACE + '...') -ForegroundColor Yellow
    kubectl create namespace $NAMESPACE
    Write-Host '   ✅ Namespace créé' -ForegroundColor Green
} else {
    Write-Host '   ✅ Namespace existe déjà' -ForegroundColor Green
}

# Étape 1: Déployer Qdrant
Write-Host ""
Write-Host '📦 Étape 1: Déploiement de Qdrant...' -ForegroundColor Cyan
Write-Host '   Application de la configuration Qdrant...' -ForegroundColor Yellow
# Remplacer le namespace dans le fichier YAML et appliquer
$qdrantYaml = Get-Content ($CHART_DIR + '/qdrant-deployment.yaml') -Raw
$qdrantYaml = $qdrantYaml -replace 'namespace: default', ('namespace: ' + $NAMESPACE)
$qdrantYaml | kubectl apply -f - 2>&1 | Out-Null
if ($?) {
    Write-Host '   ✅ Qdrant déployé' -ForegroundColor Green
} else {
    Write-Host '   ⚠️  Erreur lors du déploiement de Qdrant' -ForegroundColor Yellow
}

# Attendre que Qdrant soit prêt
Write-Host '   Attente que Qdrant soit prêt...' -ForegroundColor Yellow
$ErrorActionPreference = 'Continue'
kubectl wait --for=condition=ready pod -l app=shopifake-qdrant -n $NAMESPACE --timeout=120s 2>&1 | Out-Null
if (-not $?) {
    Write-Host '   ⚠️  Timeout, mais continuons...' -ForegroundColor Yellow
}
$ErrorActionPreference = 'Stop'

# Étape 2: Déployer Redis
Write-Host ''
Write-Host '📦 Étape 2: Déploiement de Redis...' -ForegroundColor Cyan
Write-Host '   Application de la configuration Redis...' -ForegroundColor Yellow
# Remplacer le namespace dans le fichier YAML et appliquer
$redisYaml = Get-Content ($CHART_DIR + '/redis-deployment.yaml') -Raw
$redisYaml = $redisYaml -replace 'namespace: default', ('namespace: ' + $NAMESPACE)
$redisYaml | kubectl apply -f - 2>&1 | Out-Null
if ($?) {
    Write-Host '   ✅ Redis déployé' -ForegroundColor Green
} else {
    Write-Host '   ⚠️  Erreur lors du déploiement de Redis' -ForegroundColor Yellow
}

# Attendre que Redis soit prêt
Write-Host '   Attente que Redis soit prêt...' -ForegroundColor Yellow
$ErrorActionPreference = 'Continue'
kubectl wait --for=condition=ready pod -l app=shopifake-redis -n $NAMESPACE --timeout=120s 2>&1 | Out-Null
if (-not $?) {
    Write-Host '   ⚠️  Timeout, mais continuons...' -ForegroundColor Yellow
}
$ErrorActionPreference = 'Stop'

# Étape 3: Construire l'image Docker
Write-Host ''
Write-Host '🐳 Étape 3: Construction de l''image Docker...' -ForegroundColor Cyan
Set-Location $PARENT_DIR
if (docker build -t shopifake-recommender:latest .) {
    Write-Host '   ✅ Image construite avec succès' -ForegroundColor Green
    Write-Host '   ✅ Image disponible localement (Docker Desktop utilise les images locales)' -ForegroundColor Green
} else {
    Write-Host '   ❌ Échec de la construction de l''image' -ForegroundColor Red
    exit 1
}

# Étape 4: Déployer avec Helm
Write-Host ''
Write-Host '📦 Étape 4: Déploiement avec Helm...' -ForegroundColor Cyan

# Vérifier que Helm est installé
if (-not (Get-Command helm -ErrorAction SilentlyContinue)) {
    Write-Host '   ❌ Helm n''est pas installé.' -ForegroundColor Red
    Write-Host '   Veuillez installer Helm: https://helm.sh/docs/intro/install/' -ForegroundColor Yellow
    exit 1
}

Set-Location $CHART_DIR

# Vérifier si le release existe déjà
$helmList = helm list -n $NAMESPACE 2>$null
if ($helmList -match 'shopifake-recommender') {
    Write-Host '   Mise à jour du déploiement existant...' -ForegroundColor Yellow
    helm upgrade shopifake-recommender . `
        -f values-local.yaml `
        -n $NAMESPACE `
        --wait `
        --timeout 5m
} else {
    Write-Host '   Installation du nouveau déploiement...' -ForegroundColor Green
    helm install shopifake-recommender . `
        -f values-local.yaml `
        -n $NAMESPACE `
        --wait `
        --timeout 5m
}

# Forcer le redémarrage des pods pour utiliser la nouvelle image
Write-Host ''
Write-Host '🔄 Redémarrage des pods pour utiliser la nouvelle image...' -ForegroundColor Cyan
$ErrorActionPreference = 'SilentlyContinue'

# Vérifier et redémarrer le déploiement services s'il existe
$servicesDeployment = kubectl get deployment shopifake-recommender-chart-services -n $NAMESPACE 2>$null
if ($servicesDeployment) {
    Write-Host '   Redémarrage de shopifake-recommender-chart-services...' -ForegroundColor Yellow
    kubectl rollout restart deployment/shopifake-recommender-chart-services -n $NAMESPACE 2>&1 | Out-Null
    Write-Host '   ✅ Redémarrage de services déclenché' -ForegroundColor Green
} else {
    Write-Host '   ⚠️  Déploiement services non trouvé (sera créé par Helm)' -ForegroundColor Yellow
}

# Vérifier et redémarrer le déploiement queue s'il existe
$queueDeployment = kubectl get deployment shopifake-recommender-chart-queue -n $NAMESPACE 2>$null
if ($queueDeployment) {
    Write-Host '   Redémarrage de shopifake-recommender-chart-queue...' -ForegroundColor Yellow
    kubectl rollout restart deployment/shopifake-recommender-chart-queue -n $NAMESPACE 2>&1 | Out-Null
    Write-Host '   ✅ Redémarrage de queue déclenché' -ForegroundColor Green
} else {
    Write-Host '   ⚠️  Déploiement queue non trouvé (sera créé par Helm)' -ForegroundColor Yellow
}

# Attendre que les pods soient prêts
if ($servicesDeployment -or $queueDeployment) {
    Write-Host '   Attente que les pods soient prêts...' -ForegroundColor Yellow
    $ErrorActionPreference = 'Continue'
    if ($servicesDeployment) {
        kubectl rollout status deployment/shopifake-recommender-chart-services -n $NAMESPACE --timeout=120s 2>&1 | Out-Null
    }
    if ($queueDeployment) {
        kubectl rollout status deployment/shopifake-recommender-chart-queue -n $NAMESPACE --timeout=120s 2>&1 | Out-Null
    }
}
$ErrorActionPreference = 'Stop'

Write-Host ''
Write-Host '✅ Déploiement terminé!' -ForegroundColor Green
Write-Host ''
Write-Host '📊 Statut des pods:' -ForegroundColor Cyan
kubectl get pods -n $NAMESPACE | Select-String -Pattern 'shopifake|NAME'

Write-Host ''
Write-Host '🌐 Accès au service:' -ForegroundColor Cyan
Write-Host '   - Recommender API: http://localhost:30080' -ForegroundColor Yellow
Write-Host '   - Qdrant: http://localhost:6333 (port-forward nécessaire)' -ForegroundColor Yellow
Write-Host '   - Redis: localhost:6379 (port-forward nécessaire)' -ForegroundColor Yellow
Write-Host ''
Write-Host 'Pour accéder à Qdrant:' -ForegroundColor Cyan
$qdrantCmd = '   kubectl port-forward svc/shopifake-qdrant 6333:6333 -n ' + $NAMESPACE
Write-Host $qdrantCmd -ForegroundColor White
Write-Host ''
Write-Host 'Pour accéder à Redis:' -ForegroundColor Cyan
$redisCmd = '   kubectl port-forward svc/shopifake-redis 6379:6379 -n ' + $NAMESPACE
Write-Host $redisCmd -ForegroundColor White
Write-Host ''
Write-Host 'Pour voir les logs:' -ForegroundColor Cyan
$servicesLogsCmd = '   kubectl logs -f deployment/shopifake-recommender-chart-services -n ' + $NAMESPACE
Write-Host $servicesLogsCmd -ForegroundColor White
$queueLogsCmd = '   kubectl logs -f deployment/shopifake-recommender-chart-queue -n ' + $NAMESPACE
Write-Host $queueLogsCmd -ForegroundColor White
