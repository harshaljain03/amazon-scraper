#!/bin/bash

set -e

# Build and deploy script for Amazon Scraper
# Usage: ./scripts/build-and-deploy.sh [environment] [tag]

# Configuration
ENVIRONMENT=${1:-development}
TAG=${2:-latest}
IMAGE_NAME="amazon-scraper"
REGISTRY=${DOCKER_REGISTRY:-"localhost:5000"}
NAMESPACE="amazon-scraper"

echo "=== Amazon Scraper Build and Deploy Script ==="
echo "Environment: $ENVIRONMENT"
echo "Tag: $TAG"
echo "Registry: $REGISTRY"
echo "Namespace: $NAMESPACE"
echo ""

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

print_status() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check prerequisites
check_prerequisites() {
    print_status "Checking prerequisites..."
    
    # Check Docker
    if ! command -v docker &> /dev/null; then
        print_error "Docker is not installed or not in PATH"
        exit 1
    fi
    
    # Check kubectl
    if ! command -v kubectl &> /dev/null; then
        print_error "kubectl is not installed or not in PATH"
        exit 1
    fi
    
    # Check Helm (optional)
    if ! command -v helm &> /dev/null; then
        print_warning "Helm is not installed - using kubectl apply instead"
        USE_HELM=false
    else
        USE_HELM=true
    fi
    
    print_success "Prerequisites check completed"
}

# Build Docker image
build_image() {
    print_status "Building Docker image..."
    
    # Determine build target based on environment
    if [ "$ENVIRONMENT" = "production" ]; then
        BUILD_TARGET="production"
    else
        BUILD_TARGET="development"
    fi
    
    docker build \
        --target $BUILD_TARGET \
        --tag $IMAGE_NAME:$TAG \
        --tag $IMAGE_NAME:latest \
        .
    
    if [ $? -eq 0 ]; then
        print_success "Docker image built successfully"
    else
        print_error "Docker image build failed"
        exit 1
    fi
}

# Run tests
run_tests() {
    print_status "Running tests..."
    
    # Run unit tests in container
    docker run --rm \
        --env PYTHONPATH=/app \
        $IMAGE_NAME:$TAG \
        python -m pytest tests/unit/ -v --tb=short
    
    if [ $? -eq 0 ]; then
        print_success "Unit tests passed"
    else
        print_error "Unit tests failed"
        exit 1
    fi
}

# Push image to registry
push_image() {
    if [ "$REGISTRY" != "localhost:5000" ] && [ "$ENVIRONMENT" = "production" ]; then
        print_status "Pushing image to registry..."
        
        # Tag for registry
        docker tag $IMAGE_NAME:$TAG $REGISTRY/$IMAGE_NAME:$TAG
        docker tag $IMAGE_NAME:$TAG $REGISTRY/$IMAGE_NAME:latest
        
        # Push to registry
        docker push $REGISTRY/$IMAGE_NAME:$TAG
        docker push $REGISTRY/$IMAGE_NAME:latest
        
        if [ $? -eq 0 ]; then
            print_success "Image pushed to registry"
        else
            print_error "Failed to push image to registry"
            exit 1
        fi
    else
        print_status "Skipping image push (local development or localhost registry)"
    fi
}

# Deploy to Kubernetes
deploy_kubernetes() {
    print_status "Deploying to Kubernetes..."
    
    # Create namespace if it doesn't exist
    kubectl create namespace $NAMESPACE --dry-run=client -o yaml | kubectl apply -f -
    
    if [ "$USE_HELM" = true ] && [ -d "helm/amazon-scraper" ]; then
        deploy_with_helm
    else
        deploy_with_kubectl
    fi
}

# Deploy using Helm
deploy_with_helm() {
    print_status "Deploying with Helm..."
    
    # Create values file for environment
    VALUES_FILE="helm/amazon-scraper/values-$ENVIRONMENT.yaml"
    
    if [ ! -f "$VALUES_FILE" ]; then
        VALUES_FILE="helm/amazon-scraper/values.yaml"
    fi
    
    helm upgrade --install amazon-scraper helm/amazon-scraper \
        --namespace $NAMESPACE \
        --values $VALUES_FILE \
        --set image.tag=$TAG \
        --set image.repository=$REGISTRY/$IMAGE_NAME \
        --wait --timeout=300s
    
    if [ $? -eq 0 ]; then
        print_success "Helm deployment completed"
    else
        print_error "Helm deployment failed"
        exit 1
    fi
}

# Deploy using kubectl
deploy_with_kubectl() {
    print_status "Deploying with kubectl..."
    
    # Update image tag in deployment
    sed -i.bak "s|image: amazon-scraper:latest|image: $REGISTRY/$IMAGE_NAME:$TAG|g" k8s/deployment.yaml
    
    # Apply Kubernetes manifests in order
    kubectl apply -f k8s/namespace.yaml
    kubectl apply -f k8s/configmap.yaml
    kubectl apply -f k8s/secrets.yaml
    kubectl apply -f k8s/postgres.yaml
    kubectl apply -f k8s/redis.yaml
    kubectl apply -f k8s/deployment.yaml
    kubectl apply -f k8s/service.yaml
    kubectl apply -f k8s/cronjob.yaml
    
    # Wait for deployment to be ready
    kubectl rollout status deployment/amazon-scraper-deployment -n $NAMESPACE --timeout=300s
    
    # Restore original deployment file
    mv k8s/deployment.yaml.bak k8s/deployment.yaml
    
    if [ $? -eq 0 ]; then
        print_success "kubectl deployment completed"
    else
        print_error "kubectl deployment failed"
        exit 1
    fi
}

# Verify deployment
verify_deployment() {
    print_status "Verifying deployment..."
    
    # Wait for pods to be ready
    sleep 10
    
    # Check pod status
    POD_STATUS=$(kubectl get pods -n $NAMESPACE -l app=amazon-scraper -o jsonpath='{.items[*].status.phase}')
    
    if echo "$POD_STATUS" | grep -q "Running"; then
        print_success "Pods are running"
    else
        print_error "Pods are not running properly"
        kubectl get pods -n $NAMESPACE -l app=amazon-scraper
        exit 1
    fi
    
    # Check service health
    print_status "Checking service health..."
    
    # Port forward for health check
    kubectl port-forward -n $NAMESPACE svc/amazon-scraper-service 8080:8080 &
    PORT_FORWARD_PID=$!
    
    sleep 5
    
    # Health check
    if curl -f -s http://localhost:8080/health > /dev/null; then
        print_success "Service health check passed"
    else
        print_error "Service health check failed"
        kill $PORT_FORWARD_PID 2>/dev/null
        exit 1
    fi
    
    # Clean up port forward
    kill $PORT_FORWARD_PID 2>/dev/null
    
    print_success "Deployment verification completed"
}

# Show deployment info
show_deployment_info() {
    print_status "Deployment Information:"
    echo ""
    
    # Show pods
    echo "Pods:"
    kubectl get pods -n $NAMESPACE -l app=amazon-scraper
    echo ""
    
    # Show services
    echo "Services:"
    kubectl get svc -n $NAMESPACE
    echo ""
    
    # Show ingress (if exists)
    if kubectl get ingress -n $NAMESPACE &> /dev/null; then
        echo "Ingress:"
        kubectl get ingress -n $NAMESPACE
        echo ""
    fi
    
    # Show cronjobs
    echo "CronJobs:"
    kubectl get cronjobs -n $NAMESPACE
    echo ""
    
    print_success "Deployment completed successfully!"
    echo ""
    echo "Access URLs:"
    if kubectl get ingress -n $NAMESPACE &> /dev/null; then
        INGRESS_HOST=$(kubectl get ingress amazon-scraper-ingress -n $NAMESPACE -o jsonpath='{.spec.rules[0].host}' 2>/dev/null)
        if [ -n "$INGRESS_HOST" ]; then
            echo "  - Application: https://$INGRESS_HOST"
            echo "  - Metrics: https://$INGRESS_HOST/metrics"
        fi
    fi
    echo "  - Port Forward: kubectl port-forward -n $NAMESPACE svc/amazon-scraper-service 8080:8080"
    echo ""
}

# Cleanup function
cleanup() {
    if [ -n "$PORT_FORWARD_PID" ]; then
        kill $PORT_FORWARD_PID 2>/dev/null
    fi
}

# Set trap for cleanup
trap cleanup EXIT

# Main execution
main() {
    print_status "Starting build and deployment process..."
    
    check_prerequisites
    build_image
    
    if [ "$ENVIRONMENT" = "production" ]; then
        run_tests
    fi
    
    push_image
    deploy_kubernetes
    verify_deployment
    show_deployment_info
}

# Parse command line arguments
case "${1:-}" in
    -h|--help)
        echo "Usage: $0 [environment] [tag]"
        echo ""
        echo "Arguments:"
        echo "  environment  deployment environment (development|production) [default: development]"
        echo "  tag         Docker image tag [default: latest]"
        echo ""
        echo "Environment Variables:"
        echo "  DOCKER_REGISTRY  Docker registry URL [default: localhost:5000]"
        echo ""
        echo "Examples:"
        echo "  $0 development latest"
        echo "  $0 production v1.2.3"
        echo "  DOCKER_REGISTRY=my-registry.com $0 production v1.2.3"
        exit 0
        ;;
    clean)
        print_status "Cleaning up deployment..."
        kubectl delete namespace $NAMESPACE --ignore-not-found=true
        docker rmi $IMAGE_NAME:$TAG 2>/dev/null || true
        docker rmi $IMAGE_NAME:latest 2>/dev/null || true
        print_success "Cleanup completed"
        exit 0
        ;;
    *)
        main
        ;;
esac
