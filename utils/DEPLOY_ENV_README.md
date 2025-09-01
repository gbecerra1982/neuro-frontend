# Azure App Service Environment Variables Deployment

Scripts to automatically deploy environment variables from your `.env` file to Azure App Service.

## Prerequisites

1. **Azure CLI** installed and configured
   - Install from: https://docs.microsoft.com/en-us/cli/azure/install-azure-cli
   - Login: `az login`

2. **Python 3.6+** (for Python script) or **PowerShell 5.1+** (for PowerShell script)

## Scripts Available

### 1. Python Script: `deploy_env_to_azure.py`

Cross-platform script that works on Windows, macOS, and Linux.

### 2. PowerShell Script: `Deploy-EnvToAzure.ps1`

Windows-optimized script with PowerShell features.

## Usage

### Quick Start

#### Python:
```bash
# List available App Services
python deploy_env_to_azure.py

# Deploy to specific App Service
python deploy_env_to_azure.py --app-name myapp --resource-group myresourcegroup

# Dry run (preview changes without applying)
python deploy_env_to_azure.py --app-name myapp --resource-group myresourcegroup --dry-run
```

#### PowerShell:
```powershell
# List available App Services
.\Deploy-EnvToAzure.ps1

# Deploy to specific App Service
.\Deploy-EnvToAzure.ps1 -AppName myapp -ResourceGroup myresourcegroup

# Dry run (preview changes without applying)
.\Deploy-EnvToAzure.ps1 -AppName myapp -ResourceGroup myresourcegroup -DryRun
```

### Advanced Options

#### Exclude Specific Variables
```bash
# Python
python deploy_env_to_azure.py --app-name myapp --resource-group myrg --exclude DEBUG LOG_LEVEL

# PowerShell
.\Deploy-EnvToAzure.ps1 -AppName myapp -ResourceGroup myrg -Exclude DEBUG,LOG_LEVEL
```

#### Include Only Specific Variables
```bash
# Python
python deploy_env_to_azure.py --app-name myapp --resource-group myrg --include-only AZURE_OPENAI_ENDPOINT AZURE_OPENAI_API_KEY

# PowerShell
.\Deploy-EnvToAzure.ps1 -AppName myapp -ResourceGroup myrg -IncludeOnly AZURE_OPENAI_ENDPOINT,AZURE_OPENAI_API_KEY
```

#### Use Different .env File
```bash
# Python
python deploy_env_to_azure.py --env-file .env.production --app-name myapp --resource-group myrg

# PowerShell
.\Deploy-EnvToAzure.ps1 -EnvFile .env.production -AppName myapp -ResourceGroup myrg
```

## Features

- **Automatic parsing** of .env file format
- **Batch deployment** to handle Azure CLI command length limits
- **Sensitive data detection** and masking in output
- **Dry run mode** to preview changes before applying
- **Filtering options** to exclude or include specific variables
- **Interactive confirmation** before deployment
- **Progress tracking** for large deployments

## Security Considerations

1. **Sensitive Variables**: The scripts detect and mask sensitive variables (containing KEY, PASSWORD, SECRET, TOKEN, CREDENTIAL) in console output

2. **Confirmation Required**: Scripts require explicit confirmation before deploying (unless in dry-run mode)

3. **Azure Security**: All variables are transmitted securely to Azure using Azure CLI's secure channels

## Common Use Cases

### 1. Initial Deployment
Deploy all environment variables from `.env` to a new App Service:
```bash
python deploy_env_to_azure.py --app-name neuro-frontend-prod --resource-group ypf-resources
```

### 2. Update Production Settings
Deploy production-specific settings while excluding debug variables:
```bash
python deploy_env_to_azure.py \
    --env-file .env.production \
    --app-name neuro-frontend-prod \
    --resource-group ypf-resources \
    --exclude DEBUG DEBUG_MODE ENABLE_DETAILED_LOGGING
```

### 3. Deploy Only API Keys
Update only API keys and endpoints:
```bash
python deploy_env_to_azure.py \
    --app-name neuro-frontend-prod \
    --resource-group ypf-resources \
    --include-only AZURE_OPENAI_API_KEY AZURE_OPENAI_ENDPOINT SPEECH_KEY COGNITIVE_SEARCH_API_KEY
```

## Post-Deployment Steps

After successful deployment:

1. **Restart the App Service**:
   ```bash
   az webapp restart --name <app-name> --resource-group <resource-group>
   ```

2. **Verify Settings** in Azure Portal:
   - Navigate to your App Service
   - Go to Configuration > Application settings
   - Verify all variables are present

3. **Check Application Logs**:
   ```bash
   az webapp log tail --name <app-name> --resource-group <resource-group>
   ```

4. **Test Your Application**:
   - Access your application URL
   - Verify all features are working correctly

## Troubleshooting

### Azure CLI Not Found
- Ensure Azure CLI is installed: https://docs.microsoft.com/en-us/cli/azure/install-azure-cli
- Add Azure CLI to your PATH environment variable

### Not Logged In to Azure
Run: `az login`

### Permission Denied
Ensure you have Contributor or Owner role on the App Service

### Settings Not Applying
1. Restart the App Service after deployment
2. Check if the App Service is running on Linux or Windows (some settings may differ)
3. Verify no typos in variable names

### Command Too Long Error
The scripts automatically batch deployments to avoid this, but if it still occurs, use the exclude or include-only options to reduce the number of variables

## Support

For issues specific to these deployment scripts, check:
1. Azure CLI is up to date: `az upgrade`
2. You have the correct permissions in Azure
3. The .env file is properly formatted (KEY=VALUE format)

For application-specific issues after deployment, check:
1. Application logs in Azure Portal
2. Environment variable names match what the application expects
3. All required variables are present