#!/usr/bin/env python3
"""
Azure App Service Environment Variables Deployment Script
Reads .env file and sets all variables as App Service application settings
"""

import os
import sys
import subprocess
import argparse
from pathlib import Path
from typing import Dict, List, Tuple


def parse_env_file(env_path: str) -> Dict[str, str]:
    """
    Parse .env file and return dictionary of environment variables
    
    Args:
        env_path: Path to .env file
        
    Returns:
        Dictionary of environment variable names and values
    """
    env_vars = {}
    
    if not os.path.exists(env_path):
        print(f"Error: .env file not found at {env_path}")
        sys.exit(1)
    
    with open(env_path, 'r', encoding='utf-8') as f:
        for line_num, line in enumerate(f, 1):
            # Skip empty lines and comments
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            
            # Parse KEY=VALUE format
            if '=' in line:
                # Handle values with equals signs
                parts = line.split('=', 1)
                if len(parts) == 2:
                    key = parts[0].strip()
                    value = parts[1].strip()
                    
                    # Remove quotes if present
                    if value.startswith('"') and value.endswith('"'):
                        value = value[1:-1]
                    elif value.startswith("'") and value.endswith("'"):
                        value = value[1:-1]
                    
                    env_vars[key] = value
                else:
                    print(f"Warning: Skipping malformed line {line_num}: {line}")
    
    return env_vars


def check_azure_cli() -> bool:
    """
    Check if Azure CLI is installed and user is logged in
    
    Returns:
        True if Azure CLI is ready, False otherwise
    """
    try:
        # Check if az CLI is installed
        result = subprocess.run(['az', '--version'], 
                              capture_output=True, 
                              text=True, 
                              check=False)
        if result.returncode != 0:
            print("Error: Azure CLI is not installed")
            print("Install it from: https://docs.microsoft.com/en-us/cli/azure/install-azure-cli")
            return False
        
        # Check if logged in
        result = subprocess.run(['az', 'account', 'show'], 
                              capture_output=True, 
                              text=True, 
                              check=False)
        if result.returncode != 0:
            print("Error: Not logged in to Azure")
            print("Run: az login")
            return False
        
        return True
    except FileNotFoundError:
        print("Error: Azure CLI is not installed")
        print("Install it from: https://docs.microsoft.com/en-us/cli/azure/install-azure-cli")
        return False


def get_app_services(resource_group: str = None) -> List[Tuple[str, str]]:
    """
    Get list of App Services in subscription or resource group
    
    Args:
        resource_group: Optional resource group name to filter
        
    Returns:
        List of tuples (app_name, resource_group)
    """
    cmd = ['az', 'webapp', 'list', '--output', 'json']
    if resource_group:
        cmd.extend(['--resource-group', resource_group])
    
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        print(f"Error listing App Services: {result.stderr}")
        return []
    
    import json
    try:
        apps = json.loads(result.stdout)
        return [(app['name'], app['resourceGroup']) for app in apps]
    except json.JSONDecodeError:
        print("Error parsing App Service list")
        return []


def set_app_settings(app_name: str, resource_group: str, env_vars: Dict[str, str], 
                    dry_run: bool = False) -> bool:
    """
    Set application settings for an App Service
    
    Args:
        app_name: Name of the App Service
        resource_group: Resource group name
        env_vars: Dictionary of environment variables
        dry_run: If True, only show what would be done
        
    Returns:
        True if successful, False otherwise
    """
    if dry_run:
        print(f"\n[DRY RUN] Would set {len(env_vars)} settings for {app_name} in {resource_group}")
        print("\nSettings to be applied:")
        for key, value in env_vars.items():
            # Mask sensitive values in dry run
            if any(sensitive in key.upper() for sensitive in ['KEY', 'PASSWORD', 'SECRET', 'TOKEN', 'CREDENTIAL']):
                display_value = value[:4] + '***' if len(value) > 4 else '***'
            else:
                display_value = value if len(value) <= 50 else value[:50] + '...'
            print(f"  {key} = {display_value}")
        return True
    
    # Build settings string for az webapp config
    settings_list = []
    for key, value in env_vars.items():
        # Escape special characters for shell
        value = value.replace('"', '\\"')
        settings_list.append(f'{key}="{value}"')
    
    # Azure CLI has a limit on command length, so we'll batch if needed
    batch_size = 20
    total_settings = len(settings_list)
    
    for i in range(0, total_settings, batch_size):
        batch = settings_list[i:i + batch_size]
        settings_str = ' '.join(batch)
        
        print(f"\nDeploying batch {i//batch_size + 1}/{(total_settings + batch_size - 1)//batch_size}...")
        
        cmd = [
            'az', 'webapp', 'config', 'appsettings', 'set',
            '--name', app_name,
            '--resource-group', resource_group,
            '--settings', settings_str,
            '--output', 'none'
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if result.returncode != 0:
            print(f"Error setting application settings: {result.stderr}")
            return False
    
    print(f"\nSuccessfully set {len(env_vars)} settings for {app_name}")
    return True


def main():
    """Main execution function"""
    parser = argparse.ArgumentParser(
        description='Deploy environment variables from .env file to Azure App Service'
    )
    parser.add_argument(
        '--env-file',
        default='../.env',
        help='Path to .env file (default: ../.env)'
    )
    parser.add_argument(
        '--app-name',
        help='App Service name (if not provided, will show list)'
    )
    parser.add_argument(
        '--resource-group',
        help='Resource group name (required if app-name is provided)'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Show what would be done without making changes'
    )
    parser.add_argument(
        '--exclude',
        nargs='*',
        default=[],
        help='Environment variables to exclude (e.g., --exclude DEBUG LOG_LEVEL)'
    )
    parser.add_argument(
        '--include-only',
        nargs='*',
        default=[],
        help='Only include these environment variables'
    )
    
    args = parser.parse_args()
    
    print("Azure App Service Environment Variables Deployment")
    print("=" * 50)
    
    # Check Azure CLI
    if not check_azure_cli():
        sys.exit(1)
    
    # Parse .env file
    print(f"\nReading environment variables from: {args.env_file}")
    env_vars = parse_env_file(args.env_file)
    print(f"Found {len(env_vars)} environment variables")
    
    # Apply filters
    if args.include_only:
        env_vars = {k: v for k, v in env_vars.items() if k in args.include_only}
        print(f"Filtered to {len(env_vars)} variables (include-only filter)")
    
    if args.exclude:
        env_vars = {k: v for k, v in env_vars.items() if k not in args.exclude}
        print(f"Filtered to {len(env_vars)} variables (exclude filter)")
    
    # If no app name provided, show list
    if not args.app_name:
        print("\nAvailable App Services:")
        apps = get_app_services(args.resource_group)
        if not apps:
            print("No App Services found")
            sys.exit(1)
        
        for i, (name, rg) in enumerate(apps, 1):
            print(f"{i}. {name} (Resource Group: {rg})")
        
        print("\nRe-run with --app-name and --resource-group to deploy")
        print(f"Example: python {sys.argv[0]} --app-name {apps[0][0]} --resource-group {apps[0][1]}")
        sys.exit(0)
    
    # Validate required parameters
    if not args.resource_group:
        print("Error: --resource-group is required when --app-name is provided")
        sys.exit(1)
    
    # Confirm before deployment
    if not args.dry_run:
        print(f"\nTarget App Service: {args.app_name}")
        print(f"Resource Group: {args.resource_group}")
        print(f"Variables to deploy: {len(env_vars)}")
        
        # Show sensitive variable warning
        sensitive_keys = [k for k in env_vars.keys() 
                         if any(s in k.upper() for s in ['KEY', 'PASSWORD', 'SECRET', 'TOKEN', 'CREDENTIAL'])]
        if sensitive_keys:
            print(f"\nWarning: {len(sensitive_keys)} sensitive variables detected:")
            for key in sensitive_keys[:5]:  # Show first 5
                print(f"  - {key}")
            if len(sensitive_keys) > 5:
                print(f"  ... and {len(sensitive_keys) - 5} more")
        
        response = input("\nDo you want to continue? (yes/no): ")
        if response.lower() not in ['yes', 'y']:
            print("Deployment cancelled")
            sys.exit(0)
    
    # Deploy settings
    success = set_app_settings(args.app_name, args.resource_group, env_vars, args.dry_run)
    
    if success:
        if args.dry_run:
            print("\n[DRY RUN] Completed successfully")
            print("Run without --dry-run to apply changes")
        else:
            print("\nDeployment completed successfully!")
            print(f"\nNext steps:")
            print(f"1. Restart the App Service:")
            print(f"   az webapp restart --name {args.app_name} --resource-group {args.resource_group}")
            print(f"2. View the settings in Azure Portal:")
            print(f"   https://portal.azure.com")
            print(f"3. Check application logs for any issues")
    else:
        print("\nDeployment failed. Check the errors above.")
        sys.exit(1)


if __name__ == "__main__":
    main()