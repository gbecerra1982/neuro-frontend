<#
.SYNOPSIS
    Deploy environment variables from .env file to Azure App Service
.DESCRIPTION
    Reads a .env file and sets all variables as App Service application settings
.PARAMETER EnvFile
    Path to .env file (default: .env)
.PARAMETER AppName
    App Service name (if not provided, will show list)
.PARAMETER ResourceGroup
    Resource group name (required if AppName is provided)
.PARAMETER DryRun
    Show what would be done without making changes
.PARAMETER Exclude
    Environment variables to exclude
.PARAMETER IncludeOnly
    Only include these environment variables
.EXAMPLE
    .\Deploy-EnvToAzure.ps1 -AppName myapp -ResourceGroup myrg
.EXAMPLE
    .\Deploy-EnvToAzure.ps1 -DryRun
#>

param(
    [string]$EnvFile = "../.env",
    [string]$AppName,
    [string]$ResourceGroup,
    [switch]$DryRun,
    [string[]]$Exclude = @(),
    [string[]]$IncludeOnly = @()
)

# Colors for output
$ErrorActionPreference = "Stop"

function Write-Header {
    param([string]$Text)
    Write-Host "`n$Text" -ForegroundColor Cyan
    Write-Host ("=" * $Text.Length) -ForegroundColor Cyan
}

function Write-Success {
    param([string]$Text)
    Write-Host $Text -ForegroundColor Green
}

function Write-Warning {
    param([string]$Text)
    Write-Host $Text -ForegroundColor Yellow
}

function Write-Error {
    param([string]$Text)
    Write-Host $Text -ForegroundColor Red
}

function Parse-EnvFile {
    param([string]$Path)
    
    $envVars = @{}
    
    if (-not (Test-Path $Path)) {
        Write-Error "Error: .env file not found at $Path"
        exit 1
    }
    
    $content = Get-Content $Path -Encoding UTF8
    $lineNum = 0
    
    foreach ($line in $content) {
        $lineNum++
        $line = $line.Trim()
        
        # Skip empty lines and comments
        if ([string]::IsNullOrWhiteSpace($line) -or $line.StartsWith("#")) {
            continue
        }
        
        # Parse KEY=VALUE format
        if ($line -match "^([^=]+)=(.*)$") {
            $key = $Matches[1].Trim()
            $value = $Matches[2].Trim()
            
            # Remove quotes if present
            if (($value.StartsWith('"') -and $value.EndsWith('"')) -or 
                ($value.StartsWith("'") -and $value.EndsWith("'"))) {
                $value = $value.Substring(1, $value.Length - 2)
            }
            
            $envVars[$key] = $value
        }
        else {
            Write-Warning "Warning: Skipping malformed line $lineNum : $line"
        }
    }
    
    return $envVars
}

function Test-AzureCLI {
    try {
        $null = az --version 2>&1
        $account = az account show 2>&1 | ConvertFrom-Json
        if ($null -eq $account) {
            Write-Error "Error: Not logged in to Azure"
            Write-Host "Run: az login"
            return $false
        }
        Write-Success "Azure CLI authenticated as: $($account.user.name)"
        return $true
    }
    catch {
        Write-Error "Error: Azure CLI is not installed or not in PATH"
        Write-Host "Install from: https://docs.microsoft.com/en-us/cli/azure/install-azure-cli"
        return $false
    }
}

function Get-AppServices {
    param([string]$ResourceGroup)
    
    $cmd = @("webapp", "list", "--output", "json")
    if ($ResourceGroup) {
        $cmd += "--resource-group", $ResourceGroup
    }
    
    try {
        $apps = az @cmd | ConvertFrom-Json
        return $apps | ForEach-Object { 
            [PSCustomObject]@{
                Name = $_.name
                ResourceGroup = $_.resourceGroup
                State = $_.state
                Location = $_.location
            }
        }
    }
    catch {
        Write-Error "Error listing App Services: $_"
        return @()
    }
}

function Set-AppServiceSettings {
    param(
        [string]$AppName,
        [string]$ResourceGroup,
        [hashtable]$EnvVars,
        [bool]$DryRun
    )
    
    if ($DryRun) {
        Write-Header "[DRY RUN] Would set $($EnvVars.Count) settings for $AppName in $ResourceGroup"
        Write-Host "`nSettings to be applied:"
        
        foreach ($key in $EnvVars.Keys) {
            $value = $EnvVars[$key]
            # Mask sensitive values
            $sensitiveKeys = @('KEY', 'PASSWORD', 'SECRET', 'TOKEN', 'CREDENTIAL', 'PASS')
            $isSensitive = $sensitiveKeys | Where-Object { $key.ToUpper().Contains($_) }
            
            if ($isSensitive) {
                $displayValue = if ($value.Length -gt 4) { $value.Substring(0, 4) + "***" } else { "***" }
            }
            else {
                $displayValue = if ($value.Length -le 50) { $value } else { $value.Substring(0, 50) + "..." }
            }
            Write-Host "  $key = $displayValue"
        }
        return $true
    }
    
    # Prepare settings for Azure CLI
    $settings = @()
    foreach ($key in $EnvVars.Keys) {
        $value = $EnvVars[$key]
        # Escape special characters
        $value = $value.Replace('"', '\"').Replace('`', '``')
        $settings += "$key=`"$value`""
    }
    
    # Azure CLI has command length limits, batch if needed
    $batchSize = 20
    $totalSettings = $settings.Count
    $batches = [Math]::Ceiling($totalSettings / $batchSize)
    
    for ($i = 0; $i -lt $totalSettings; $i += $batchSize) {
        $batchNum = [Math]::Floor($i / $batchSize) + 1
        $batch = $settings[$i..[Math]::Min($i + $batchSize - 1, $totalSettings - 1)]
        
        Write-Host "`nDeploying batch $batchNum/$batches ($(($batch.Count)) settings)..."
        
        try {
            # Use Azure CLI to set app settings
            $result = az webapp config appsettings set `
                --name $AppName `
                --resource-group $ResourceGroup `
                --settings @batch `
                --output none 2>&1
            
            if ($LASTEXITCODE -ne 0) {
                Write-Error "Error setting application settings: $result"
                return $false
            }
            
            Write-Success "Batch $batchNum deployed successfully"
        }
        catch {
            Write-Error "Error setting application settings: $_"
            return $false
        }
    }
    
    Write-Success "`nSuccessfully set $($EnvVars.Count) settings for $AppName"
    return $true
}

# Main execution
Write-Header "Azure App Service Environment Variables Deployment"

# Check Azure CLI
if (-not (Test-AzureCLI)) {
    exit 1
}

# Parse .env file
Write-Host "`nReading environment variables from: $EnvFile"
$envVars = Parse-EnvFile -Path $EnvFile
Write-Success "Found $($envVars.Count) environment variables"

# Apply filters
if ($IncludeOnly.Count -gt 0) {
    $filtered = @{}
    foreach ($key in $envVars.Keys) {
        if ($IncludeOnly -contains $key) {
            $filtered[$key] = $envVars[$key]
        }
    }
    $envVars = $filtered
    Write-Host "Filtered to $($envVars.Count) variables (include-only filter)"
}

if ($Exclude.Count -gt 0) {
    foreach ($excludeKey in $Exclude) {
        if ($envVars.ContainsKey($excludeKey)) {
            $envVars.Remove($excludeKey)
        }
    }
    Write-Host "Filtered to $($envVars.Count) variables (exclude filter)"
}

# If no app name provided, show list
if (-not $AppName) {
    Write-Header "Available App Services"
    $apps = Get-AppServices -ResourceGroup $ResourceGroup
    
    if ($apps.Count -eq 0) {
        Write-Warning "No App Services found"
        exit 1
    }
    
    $i = 1
    foreach ($app in $apps) {
        Write-Host "$i. $($app.Name) (RG: $($app.ResourceGroup), State: $($app.State), Location: $($app.Location))"
        $i++
    }
    
    Write-Host "`nRe-run with -AppName and -ResourceGroup to deploy"
    Write-Host "Example: .\$($MyInvocation.MyCommand.Name) -AppName $($apps[0].Name) -ResourceGroup $($apps[0].ResourceGroup)"
    exit 0
}

# Validate required parameters
if (-not $ResourceGroup) {
    Write-Error "Error: -ResourceGroup is required when -AppName is provided"
    exit 1
}

# Confirm before deployment
if (-not $DryRun) {
    Write-Header "Deployment Summary"
    Write-Host "Target App Service: $AppName"
    Write-Host "Resource Group: $ResourceGroup"
    Write-Host "Variables to deploy: $($envVars.Count)"
    
    # Show sensitive variable warning
    $sensitiveKeys = @('KEY', 'PASSWORD', 'SECRET', 'TOKEN', 'CREDENTIAL', 'PASS')
    $sensitiveVars = @()
    foreach ($key in $envVars.Keys) {
        foreach ($sensitive in $sensitiveKeys) {
            if ($key.ToUpper().Contains($sensitive)) {
                $sensitiveVars += $key
                break
            }
        }
    }
    
    if ($sensitiveVars.Count -gt 0) {
        Write-Warning "`nWarning: $($sensitiveVars.Count) sensitive variables detected:"
        $displayCount = [Math]::Min(5, $sensitiveVars.Count)
        for ($i = 0; $i -lt $displayCount; $i++) {
            Write-Host "  - $($sensitiveVars[$i])"
        }
        if ($sensitiveVars.Count -gt 5) {
            Write-Host "  ... and $($sensitiveVars.Count - 5) more"
        }
    }
    
    $response = Read-Host "`nDo you want to continue? (yes/no)"
    if ($response -notmatch "^(yes|y)$") {
        Write-Warning "Deployment cancelled"
        exit 0
    }
}

# Deploy settings
$success = Set-AppServiceSettings -AppName $AppName -ResourceGroup $ResourceGroup -EnvVars $envVars -DryRun $DryRun

if ($success) {
    if ($DryRun) {
        Write-Success "`n[DRY RUN] Completed successfully"
        Write-Host "Run without -DryRun to apply changes"
    }
    else {
        Write-Success "`nDeployment completed successfully!"
        Write-Header "Next Steps"
        Write-Host "1. Restart the App Service:"
        Write-Host "   az webapp restart --name $AppName --resource-group $ResourceGroup" -ForegroundColor Yellow
        Write-Host "2. View the settings in Azure Portal:"
        Write-Host "   https://portal.azure.com" -ForegroundColor Yellow
        Write-Host "3. Check application logs for any issues"
        Write-Host "4. Test your application endpoints"
    }
}
else {
    Write-Error "`nDeployment failed. Check the errors above."
    exit 1
}