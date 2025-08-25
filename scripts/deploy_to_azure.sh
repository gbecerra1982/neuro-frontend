#!/bin/bash
# Azure Deployment Script for NEURO Project
# This script automates the deployment process to Azure

set -e

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

# Load configuration from environment or use defaults
RESOURCE_GROUP=${AZURE_RESOURCE_GROUP:-"neuro-rg"}
APP_SERVICE_BACKEND=${AZURE_APP_SERVICE_BACKEND:-"neuro-backend"}
APP_SERVICE_FRONTEND=${AZURE_APP_SERVICE_FRONTEND:-"neuro-frontend"}
APP_SERVICE_PLAN=${AZURE_APP_SERVICE_PLAN:-"neuro-plan"}
SEARCH_SERVICE=${AZURE_SEARCH_SERVICE:-"neuro-search"}
LOCATION=${AZURE_LOCATION:-"eastus"}

# Check if Azure CLI is installed
if ! command -v az &> /dev/null; then
    print_error "Azure CLI is not installed. Please install it first."
    exit 1
fi

# Check if logged in to Azure
print_status "Checking Azure login status..."
if ! az account show &> /dev/null; then
    print_error "Not logged in to Azure. Please run 'az login' first."
    exit 1
fi

# Display current configuration
print_status "Deployment Configuration:"
echo "  Resource Group: $RESOURCE_GROUP"
echo "  Backend App: $APP_SERVICE_BACKEND"
echo "  Frontend App: $APP_SERVICE_FRONTEND"
echo "  Location: $LOCATION"
echo ""

# Ask for confirmation
read -p "Do you want to proceed with deployment? (y/n) " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    print_warning "Deployment cancelled."
    exit 0
fi

# Step 1: Create Resource Group if it doesn't exist
print_status "Checking Resource Group..."
if ! az group show --name $RESOURCE_GROUP &> /dev/null; then
    print_status "Creating Resource Group..."
    az group create --name $RESOURCE_GROUP --location $LOCATION
else
    print_status "Resource Group already exists."
fi

# Step 2: Create App Service Plan if it doesn't exist
print_status "Checking App Service Plan..."
if ! az appservice plan show --name $APP_SERVICE_PLAN --resource-group $RESOURCE_GROUP &> /dev/null; then
    print_status "Creating App Service Plan..."
    az appservice plan create \
        --name $APP_SERVICE_PLAN \
        --resource-group $RESOURCE_GROUP \
        --location $LOCATION \
        --sku P1V3 \
        --is-linux
else
    print_status "App Service Plan already exists."
fi

# Step 3: Create Backend Web App
print_status "Checking Backend Web App..."
if ! az webapp show --name $APP_SERVICE_BACKEND --resource-group $RESOURCE_GROUP &> /dev/null; then
    print_status "Creating Backend Web App..."
    az webapp create \
        --name $APP_SERVICE_BACKEND \
        --resource-group $RESOURCE_GROUP \
        --plan $APP_SERVICE_PLAN \
        --runtime "PYTHON:3.11"
else
    print_status "Backend Web App already exists."
fi

# Step 4: Create Frontend Web App
print_status "Checking Frontend Web App..."
if ! az webapp show --name $APP_SERVICE_FRONTEND --resource-group $RESOURCE_GROUP &> /dev/null; then
    print_status "Creating Frontend Web App..."
    az webapp create \
        --name $APP_SERVICE_FRONTEND \
        --resource-group $RESOURCE_GROUP \
        --plan $APP_SERVICE_PLAN \
        --runtime "PYTHON:3.11"
else
    print_status "Frontend Web App already exists."
fi

# Step 5: Configure Backend Environment Variables
print_status "Configuring Backend environment variables..."
if [ -f "NEURO_RAG_BACKEND/.env" ]; then
    print_status "Reading environment variables from .env file..."
    
    # Read .env file and set app settings
    while IFS='=' read -r key value; do
        # Skip comments and empty lines
        if [[ ! "$key" =~ ^# ]] && [[ -n "$key" ]]; then
            # Remove quotes from value
            value="${value%\"}"
            value="${value#\"}"
            
            # Set app setting
            az webapp config appsettings set \
                --resource-group $RESOURCE_GROUP \
                --name $APP_SERVICE_BACKEND \
                --settings "$key=$value" \
                --output none
        fi
    done < "NEURO_RAG_BACKEND/.env"
    
    print_status "Environment variables configured."
else
    print_warning ".env file not found. Please configure environment variables manually."
fi

# Step 6: Configure Frontend Environment Variables
print_status "Configuring Frontend environment variables..."
az webapp config appsettings set \
    --resource-group $RESOURCE_GROUP \
    --name $APP_SERVICE_FRONTEND \
    --settings \
    BACKEND_URL="https://$APP_SERVICE_BACKEND.azurewebsites.net" \
    ENVIRONMENT="production" \
    --output none

# Step 7: Enable Managed Identity
print_status "Enabling Managed Identity for Backend..."
BACKEND_IDENTITY=$(az webapp identity assign \
    --resource-group $RESOURCE_GROUP \
    --name $APP_SERVICE_BACKEND \
    --query principalId \
    --output tsv)

print_status "Backend Managed Identity: $BACKEND_IDENTITY"

# Step 8: Configure CORS
print_status "Configuring CORS..."
az webapp cors add \
    --resource-group $RESOURCE_GROUP \
    --name $APP_SERVICE_BACKEND \
    --allowed-origins "https://$APP_SERVICE_FRONTEND.azurewebsites.net" "http://localhost:3000" \
    --output none

# Step 9: Enable Always On
print_status "Enabling Always On for better performance..."
az webapp config set \
    --resource-group $RESOURCE_GROUP \
    --name $APP_SERVICE_BACKEND \
    --always-on true \
    --output none

# Step 10: Configure startup command for backend
print_status "Setting Backend startup command..."
az webapp config set \
    --resource-group $RESOURCE_GROUP \
    --name $APP_SERVICE_BACKEND \
    --startup-file "startup.sh" \
    --output none

# Step 11: Package and Deploy Backend
print_status "Packaging Backend application..."
cd NEURO_RAG_BACKEND

# Create startup.sh if it doesn't exist
if [ ! -f "startup.sh" ]; then
    cat > startup.sh << 'EOF'
#!/bin/bash
gunicorn -w 4 -k uvicorn.workers.UvicornWorker \
  --bind 0.0.0.0:8000 \
  --timeout 120 \
  --access-logfile '-' \
  --error-logfile '-' \
  src.api.main:app
EOF
    chmod +x startup.sh
fi

# Create deployment package
zip -r ../backend-deploy.zip . \
    -x "*.pyc" \
    -x "__pycache__/*" \
    -x ".env" \
    -x "data/*" \
    -x ".git/*" \
    -x "*.log"

cd ..

print_status "Deploying Backend to Azure..."
az webapp deployment source config-zip \
    --resource-group $RESOURCE_GROUP \
    --name $APP_SERVICE_BACKEND \
    --src backend-deploy.zip \
    --output none

# Step 12: Package and Deploy Frontend
print_status "Packaging Frontend application..."

# Create app_service.py if it doesn't exist
if [ ! -f "app_service.py" ]; then
    cat > app_service.py << 'EOF'
import os
from flask import Flask, render_template, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

BACKEND_URL = os.getenv('BACKEND_URL', 'https://neuro-backend.azurewebsites.net')

@app.route('/')
def index():
    return render_template('voice_live_interface_fede.html')

@app.route('/health')
def health():
    return jsonify({"status": "healthy", "service": "frontend"})

@app.route('/config')
def config():
    return jsonify({
        'backend_url': BACKEND_URL,
        'environment': os.getenv('ENVIRONMENT', 'production')
    })

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)
EOF
fi

# Create requirements.txt for frontend if it doesn't exist
if [ ! -f "requirements-frontend.txt" ]; then
    cat > requirements-frontend.txt << 'EOF'
Flask==3.0.0
flask-cors==4.0.0
gunicorn==21.2.0
EOF
fi

# Create deployment package
zip -r frontend-deploy.zip \
    templates \
    app_service.py \
    requirements-frontend.txt \
    -x "*.pyc" \
    -x "__pycache__/*" \
    -x ".git/*"

print_status "Deploying Frontend to Azure..."
az webapp deployment source config-zip \
    --resource-group $RESOURCE_GROUP \
    --name $APP_SERVICE_FRONTEND \
    --src frontend-deploy.zip \
    --output none

# Step 13: Test deployment
print_status "Testing deployment..."

# Wait for apps to start
print_status "Waiting for applications to start (30 seconds)..."
sleep 30

# Test backend health
BACKEND_URL="https://$APP_SERVICE_BACKEND.azurewebsites.net"
FRONTEND_URL="https://$APP_SERVICE_FRONTEND.azurewebsites.net"

print_status "Testing Backend health..."
if curl -f -s -o /dev/null -w "%{http_code}" "$BACKEND_URL/health" | grep -q "200"; then
    print_status "Backend is healthy!"
else
    print_warning "Backend health check failed. Please check logs."
fi

print_status "Testing Frontend..."
if curl -f -s -o /dev/null -w "%{http_code}" "$FRONTEND_URL" | grep -q "200"; then
    print_status "Frontend is accessible!"
else
    print_warning "Frontend check failed. Please check logs."
fi

# Step 14: Display deployment information
print_status "Deployment completed!"
echo ""
echo "========================================="
echo "Deployment Information:"
echo "========================================="
echo "Resource Group: $RESOURCE_GROUP"
echo "Backend URL: $BACKEND_URL"
echo "Frontend URL: $FRONTEND_URL"
echo ""
echo "Next Steps:"
echo "1. Configure AI Foundry with Document Layout Skill"
echo "2. Import documents to create semantic chunks"
echo "3. Run validation: python scripts/validate_chunks.py"
echo "4. Monitor logs: az webapp log tail --name $APP_SERVICE_BACKEND --resource-group $RESOURCE_GROUP"
echo ""
echo "To view logs:"
echo "  Backend: az webapp log tail --name $APP_SERVICE_BACKEND --resource-group $RESOURCE_GROUP"
echo "  Frontend: az webapp log tail --name $APP_SERVICE_FRONTEND --resource-group $RESOURCE_GROUP"
echo "========================================="

# Cleanup
rm -f backend-deploy.zip frontend-deploy.zip

print_status "Deployment script completed successfully!"