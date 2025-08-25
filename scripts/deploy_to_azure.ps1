# Azure Deployment Script for NEURO Project (PowerShell Version)
# This script automates the deployment process to Azure

# Set strict mode
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

# Color functions for output
function Write-Status {
    param([string]$Message)
    Write-Host "[INFO] $Message" -ForegroundColor Green
}

function Write-Error-Message {
    param([string]$Message)
    Write-Host "[ERROR] $Message" -ForegroundColor Red
}

function Write-Warning-Message {
    param([string]$Message)
    Write-Host "[WARNING] $Message" -ForegroundColor Yellow
}

# Load configuration from environment or use defaults
$ResourceGroup = if ($env:AZURE_RESOURCE_GROUP) { $env:AZURE_RESOURCE_GROUP } else { "neuro-rg" }
$AppServiceBackend = if ($env:AZURE_APP_SERVICE_BACKEND) { $env:AZURE_APP_SERVICE_BACKEND } else { "neuro-backend" }
$AppServiceFrontend = if ($env:AZURE_APP_SERVICE_FRONTEND) { $env:AZURE_APP_SERVICE_FRONTEND } else { "neuro-frontend" }
$AppServicePlan = if ($env:AZURE_APP_SERVICE_PLAN) { $env:AZURE_APP_SERVICE_PLAN } else { "neuro-plan" }
$SearchService = if ($env:AZURE_SEARCH_SERVICE) { $env:AZURE_SEARCH_SERVICE } else { "neuro-search" }
$Location = if ($env:AZURE_LOCATION) { $env:AZURE_LOCATION } else { "eastus" }

# Check if Azure CLI is installed
Write-Status "Checking Azure CLI installation..."
try {
    $azVersion = az version --output json | ConvertFrom-Json
    Write-Status "Azure CLI version: $($azVersion.'azure-cli')"
} catch {
    Write-Error-Message "Azure CLI is not installed. Please install it from https://aka.ms/installazurecli"
    exit 1
}

# Check if logged in to Azure
Write-Status "Checking Azure login status..."
try {
    $account = az account show --output json | ConvertFrom-Json
    Write-Status "Logged in as: $($account.user.name)"
    Write-Status "Subscription: $($account.name)"
} catch {
    Write-Error-Message "Not logged in to Azure. Please run 'az login' first."
    exit 1
}

# Display current configuration
Write-Status "Deployment Configuration:"
Write-Host "  Resource Group: $ResourceGroup"
Write-Host "  Backend App: $AppServiceBackend"
Write-Host "  Frontend App: $AppServiceFrontend"
Write-Host "  App Service Plan: $AppServicePlan"
Write-Host "  Location: $Location"
Write-Host ""

# Ask for confirmation
$confirmation = Read-Host "Do you want to proceed with deployment? (y/n)"
if ($confirmation -ne 'y') {
    Write-Warning-Message "Deployment cancelled."
    exit 0
}

# Step 1: Create Resource Group if it doesn't exist
Write-Status "Checking Resource Group..."
$rgExists = az group exists --name $ResourceGroup
if ($rgExists -eq "false") {
    Write-Status "Creating Resource Group..."
    az group create --name $ResourceGroup --location $Location --output none
    Write-Status "Resource Group created successfully."
} else {
    Write-Status "Resource Group already exists."
}

# Step 2: Create App Service Plan if it doesn't exist
Write-Status "Checking App Service Plan..."
try {
    az appservice plan show --name $AppServicePlan --resource-group $ResourceGroup --output none 2>$null
    Write-Status "App Service Plan already exists."
} catch {
    Write-Status "Creating App Service Plan..."
    az appservice plan create `
        --name $AppServicePlan `
        --resource-group $ResourceGroup `
        --location $Location `
        --sku P1V3 `
        --is-linux `
        --output none
    Write-Status "App Service Plan created successfully."
}

# Step 3: Create Backend Web App
Write-Status "Checking Backend Web App..."
try {
    az webapp show --name $AppServiceBackend --resource-group $ResourceGroup --output none 2>$null
    Write-Status "Backend Web App already exists."
} catch {
    Write-Status "Creating Backend Web App..."
    az webapp create `
        --name $AppServiceBackend `
        --resource-group $ResourceGroup `
        --plan $AppServicePlan `
        --runtime "PYTHON:3.11" `
        --output none
    Write-Status "Backend Web App created successfully."
}

# Step 4: Create Frontend Web App
Write-Status "Checking Frontend Web App..."
try {
    az webapp show --name $AppServiceFrontend --resource-group $ResourceGroup --output none 2>$null
    Write-Status "Frontend Web App already exists."
} catch {
    Write-Status "Creating Frontend Web App..."
    az webapp create `
        --name $AppServiceFrontend `
        --resource-group $ResourceGroup `
        --plan $AppServicePlan `
        --runtime "PYTHON:3.11" `
        --output none
    Write-Status "Frontend Web App created successfully."
}

# Step 5: Configure Backend Environment Variables
Write-Status "Configuring Backend environment variables..."
$envFile = "NEURO_RAG_BACKEND\.env"
if (Test-Path $envFile) {
    Write-Status "Reading environment variables from .env file..."
    
    $envVars = @{}
    Get-Content $envFile | ForEach-Object {
        if ($_ -notmatch '^#' -and $_ -match '=') {
            $parts = $_ -split '=', 2
            $key = $parts[0].Trim()
            $value = $parts[1].Trim().Trim('"')
            if ($key) {
                $envVars[$key] = $value
            }
        }
    }
    
    # Convert to settings string
    $settings = @()
    foreach ($key in $envVars.Keys) {
        $settings += "$key=$($envVars[$key])"
    }
    
    if ($settings.Count -gt 0) {
        az webapp config appsettings set `
            --resource-group $ResourceGroup `
            --name $AppServiceBackend `
            --settings $settings `
            --output none
        Write-Status "Environment variables configured."
    }
} else {
    Write-Warning-Message ".env file not found. Please configure environment variables manually."
}

# Step 6: Configure Frontend Environment Variables
Write-Status "Configuring Frontend environment variables..."
az webapp config appsettings set `
    --resource-group $ResourceGroup `
    --name $AppServiceFrontend `
    --settings `
    "BACKEND_URL=https://$AppServiceBackend.azurewebsites.net" `
    "ENVIRONMENT=production" `
    --output none

# Step 7: Enable Managed Identity
Write-Status "Enabling Managed Identity for Backend..."
$identity = az webapp identity assign `
    --resource-group $ResourceGroup `
    --name $AppServiceBackend `
    --output json | ConvertFrom-Json
$backendIdentity = $identity.principalId
Write-Status "Backend Managed Identity: $backendIdentity"

# Step 8: Configure CORS
Write-Status "Configuring CORS..."
az webapp cors add `
    --resource-group $ResourceGroup `
    --name $AppServiceBackend `
    --allowed-origins "https://$AppServiceFrontend.azurewebsites.net" "http://localhost:3000" `
    --output none

# Step 9: Enable Always On
Write-Status "Enabling Always On for better performance..."
az webapp config set `
    --resource-group $ResourceGroup `
    --name $AppServiceBackend `
    --always-on true `
    --output none

# Step 10: Configure startup command for backend
Write-Status "Setting Backend startup command..."
az webapp config set `
    --resource-group $ResourceGroup `
    --name $AppServiceBackend `
    --startup-file "startup.sh" `
    --output none

# Step 11: Create startup.sh for backend
$startupFile = "NEURO_RAG_BACKEND\startup.sh"
if (-not (Test-Path $startupFile)) {
    Write-Status "Creating startup.sh..."
    @'
#!/bin/bash
gunicorn -w 4 -k uvicorn.workers.UvicornWorker \
  --bind 0.0.0.0:8000 \
  --timeout 120 \
  --access-logfile '-' \
  --error-logfile '-' \
  src.api.main:app
'@ | Out-File -FilePath $startupFile -Encoding UTF8 -NoNewline
}

# Step 12: Create app_service.py for frontend
$appServiceFile = "app_service.py"
if (-not (Test-Path $appServiceFile)) {
    Write-Status "Creating app_service.py..."
    @'
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
'@ | Out-File -FilePath $appServiceFile -Encoding UTF8
}

# Step 13: Create requirements for frontend
$requirementsFrontend = "requirements-frontend.txt"
if (-not (Test-Path $requirementsFrontend)) {
    Write-Status "Creating requirements-frontend.txt..."
    @'
Flask==3.0.0
flask-cors==4.0.0
gunicorn==21.2.0
'@ | Out-File -FilePath $requirementsFrontend -Encoding UTF8
}

# Step 14: Package and Deploy Backend
Write-Status "Packaging Backend application..."
Push-Location NEURO_RAG_BACKEND

# Create ZIP file for backend
$backendZip = "..\backend-deploy.zip"
if (Test-Path $backendZip) { Remove-Item $backendZip }

# Use PowerShell compression
Compress-Archive -Path * -DestinationPath $backendZip -Force `
    -CompressionLevel Optimal

Pop-Location

Write-Status "Deploying Backend to Azure..."
az webapp deployment source config-zip `
    --resource-group $ResourceGroup `
    --name $AppServiceBackend `
    --src backend-deploy.zip `
    --output none

# Step 15: Package and Deploy Frontend
Write-Status "Packaging Frontend application..."

# Create ZIP file for frontend
$frontendZip = "frontend-deploy.zip"
if (Test-Path $frontendZip) { Remove-Item $frontendZip }

# Create archive with specific files
Compress-Archive -Path templates, app_service.py, requirements-frontend.txt `
    -DestinationPath $frontendZip -Force `
    -CompressionLevel Optimal

Write-Status "Deploying Frontend to Azure..."
az webapp deployment source config-zip `
    --resource-group $ResourceGroup `
    --name $AppServiceFrontend `
    --src frontend-deploy.zip `
    --output none

# Step 16: Test deployment
Write-Status "Testing deployment..."
Write-Status "Waiting for applications to start (30 seconds)..."
Start-Sleep -Seconds 30

$backendUrl = "https://$AppServiceBackend.azurewebsites.net"
$frontendUrl = "https://$AppServiceFrontend.azurewebsites.net"

# Test backend health
Write-Status "Testing Backend health..."
try {
    $response = Invoke-WebRequest -Uri "$backendUrl/health" -UseBasicParsing -TimeoutSec 30
    if ($response.StatusCode -eq 200) {
        Write-Status "Backend is healthy!"
    }
} catch {
    Write-Warning-Message "Backend health check failed. Please check logs."
}

# Test frontend
Write-Status "Testing Frontend..."
try {
    $response = Invoke-WebRequest -Uri $frontendUrl -UseBasicParsing -TimeoutSec 30
    if ($response.StatusCode -eq 200) {
        Write-Status "Frontend is accessible!"
    }
} catch {
    Write-Warning-Message "Frontend check failed. Please check logs."
}

# Step 17: Display deployment information
Write-Host ""
Write-Host "=========================================" -ForegroundColor Cyan
Write-Host "Deployment Information:" -ForegroundColor Cyan
Write-Host "=========================================" -ForegroundColor Cyan
Write-Host "Resource Group: $ResourceGroup"
Write-Host "Backend URL: $backendUrl"
Write-Host "Frontend URL: $frontendUrl"
Write-Host ""
Write-Host "Next Steps:" -ForegroundColor Yellow
Write-Host "1. Configure AI Foundry with Document Layout Skill"
Write-Host "2. Import documents to create semantic chunks"
Write-Host "3. Run validation: python scripts/validate_chunks.py"
Write-Host "4. Monitor logs: az webapp log tail --name $AppServiceBackend --resource-group $ResourceGroup"
Write-Host ""
Write-Host "To view logs:" -ForegroundColor Yellow
Write-Host "  Backend: az webapp log tail --name $AppServiceBackend --resource-group $ResourceGroup"
Write-Host "  Frontend: az webapp log tail --name $AppServiceFrontend --resource-group $ResourceGroup"
Write-Host "=========================================" -ForegroundColor Cyan

# Cleanup
if (Test-Path "backend-deploy.zip") { Remove-Item "backend-deploy.zip" }
if (Test-Path "frontend-deploy.zip") { Remove-Item "frontend-deploy.zip" }

Write-Status "Deployment script completed successfully!"