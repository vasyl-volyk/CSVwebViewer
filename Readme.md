# CSV Web Viewer
  
This project provides a secure web application for viewing CSV files, featuring user authentication via Azure Active Directory (Azure Entra ID) and file storage in Azure Blob Storage. The application is built with FastAPI and designed for easy deployment using Docker and Azure services.
    
## Table of Contents

-   [Features](#features)
-   [Prerequisites](#prerequisites)
-   [Local Development Setup](#local-development-setup)
    -   [Clone the Repository](#clone-the-repository)
    -   [Set up Local Environment Variables](#set-up-local-environment-variables)
    -   [Run with Docker Compose](#run-with-docker-compose)
-   [Azure Deployment Setup](#azure-deployment-setup)
    -   [Azure Container Registry (ACR) Setup](#azure-container-registry-acr-setup)
    -   [Azure Storage Account Setup](#azure-storage-account-setup)
    -   [Azure Entra ID (App Registration) Setup](#azure-entra-id-app-registration-setup)
    -   [Azure App Service Creation](#azure-app-service-creation)
    -   [Azure App Service Application Settings Configuration](#azure-app-service-application-settings-configuration)
    -   [Custom Domain and HTTPS Configuration](#custom-domain-and-https-configuration)
-   [Deployment with Azure DevOps Pipeline (CI/CD)](#deployment-with-azure-devops-pipeline-cicd)
    -   [Service Connection Setup](#service-connection-setup)
        -   [Pipeline Variables](#pipeline-variables)
        -   [Pipeline YAML (`azure-pipelines.yml`)](#pipeline-yaml-azure-pipelinesyml)
        -   [Run the Pipeline](#run-the-pipeline)
-   [Usage](#usage)
-   [Troubleshooting Common Issues](#troubleshooting-common-issues)
-   [Folder Structure](#folder-structure)
-   [Contributing](#contributing)
-   [License](#license)
    
## Features
   
* **Secure CSV Viewing:** Upload and display CSV file content directly in the browser.
* **Azure Entra ID Authentication:** Secure access to the application using your organization's Azure Active Directory.
* **Azure Blob Storage:** Persistent and scalable storage for all uploaded CSV files.
* **FastAPI Backend:** High-performance Python web framework for the API.
* **Dockerized Application:** Containerized for consistent deployment across environments.
* **CI/CD Ready:** Integration with Azure DevOps Pipelines for automated build and deployment.
* **HTTPS Enabled:** Secure communication with TLS/SSL.
    
## Prerequisites
    
Before you begin, ensure you have the following:
    
* **Azure Subscription:** With permissions to create Azure resources (Resource Groups, ACR, App Service, Storage Account, Entra ID App Registrations).
* **Azure CLI:** Installed and logged in (`az login`).
* **Docker Desktop:** Installed and running on your local machine.
* **Python 3.11+:** For local development and dependency management.
* **Azure DevOps Organization:** (Optional, but recommended for CI/CD) If you plan to use Azure Pipelines.
* **Custom Domain:** (Optional) If you want to use your own domain name (e.g., `csvviewer.yourcompany.com`).
    
## Local Development Setup
  
### Clone the Repository
    
```bash
    git clone [https://github.com/your-username/CSVwebViewer.git](https://github.com/your-username/CSVwebViewer.git) # Replace with your repo URL
    cd CSVwebViewer
```

### Set up Local Environment Variables

Create a `.env` file in the root directory of your project with the following content. These variables are for local testing with your Azure Entra ID application.

    
```
# Azure AD / Entra ID Authentication
    AZURE_TENANT_ID="YOUR_AZURE_TENANT_ID" # Your Azure AD Tenant ID (Directory ID)
    AZURE_CLIENT_ID="YOUR_AZURE_CLIENT_ID" # Application (client) ID of your Entra ID App Registration
    AZURE_CLIENT_SECRET="YOUR_AZURE_CLIENT_SECRET" # Value of the client secret you generate
    AZURE_REDIRECT_URI="http://localhost:8000/auth/callback" # Must be registered in Entra ID App Registration
    AZURE_ALLOWED_GROUP_ID="YOUR_AZURE_AD_GROUP_ID" # Optional: ID of the Entra ID group for access control. Leave empty if not needed.
    
    # Azure Blob Storage
    AZURE_STORAGE_ACCOUNT_NAME="YOUR_STORAGE_ACCOUNT_NAME" # Name of your Azure Storage Account
    AZURE_STORAGE_CONTAINER_NAME="csv-files" # Name of the container in your storage account (e.g., 'csv-files')
    
    # Application Environment (for cookie 'secure' flag)
    ENV="development" # Set to 'development' for local testing (allows HTTP cookies)
```


### Run with Docker Compose

Ensure Docker Desktop is running.
```Bash
docker-compose up --build
```

Access the application in your browser at `http://localhost:8000`. You will be redirected to Azure AD for authentication.

Azure Deployment Setup
----------------------

### Azure Container Registry (ACR) Setup

ACR will host your Docker images.
1.  **Create an ACR:**
    Bash
    
        az acr create --resource-group YOUR_RESOURCE_GROUP --name etreportacr --sku Basic --admin-enabled true
    Replace `YOUR_RESOURCE_GROUP` and `etreportacr` with your desired values. Note down the full login server name (e.g., `etreportacr.azurecr.io`).
    
2.  **Login to ACR:**
    Bash
    
        az acr login --name etreportacr
    

### Azure Storage Account Setup

This will store your CSV files.
1.  **Create a Storage Account:**
    Bash
    
        az storage account create --name YOURSTORAGEACCOUNT --resource-group YOUR_RESOURCE_GROUP --location YOUR_LOCATION --sku Standard_LRS
    Replace `YOURSTORAGEACCOUNT`.
    
2.  **Create a Blob Container:**
    Bash
    
        az storage container create --name csv-files --account-name YOURSTORAGEACCOUNT --public-access off
    `csv-files` should match `AZURE_STORAGE_CONTAINER_NAME`.
    

### Azure Entra ID (App Registration) Setup

This enables authentication for your application.
1.  **Register a New Application:**
    *   Go to Azure Portal > Azure Active Directory (or Azure Entra ID) > App registrations.
        
    *   Click "New registration".
        
    *   Give it a name (e.g., `CSVViewerApp`).
        
    *   For "Supported account types", choose "Accounts in this organizational directory only (Default Directory only - Single tenant)".
        
    *   For "Redirect URI", select "Web" and add:
        *   `http://localhost:8000/auth/callback` (for local development)
            
        *   `https://YOUR_APP_SERVICE_DEFAULT_DOMAIN.azurewebsites.net/auth/callback` (e.g., `https://et-csv-viewer.azurewebsites.net/auth/callback`)
            
        *   If using a custom domain later: `https://YOUR_CUSTOM_DOMAIN.com/auth/callback` (e.g., `https://csvviewer.yourcompany.com/auth/callback`)
            
    *   Click "Register".
        
2.  **Record Application (client) ID and Directory (tenant) ID:** You'll find these on the application's "Overview" page. These are your `AZURE_CLIENT_ID` and `AZURE_TENANT_ID`.
    
3.  **Create a Client Secret:**
    *   Go to "Certificates & secrets" > "Client secrets".
        
    *   Click "New client secret", give it a description, and set an expiry.
        
    *   **Immediately copy the "Value"** (not the Secret ID). This is your `AZURE_CLIENT_SECRET`. This value is only shown once.
        
4.  **Grant API Permissions:**
    *   Go to "API permissions".
        
    *   Click "Add a permission" > "Microsoft Graph" > "Delegated permissions".
        
    *   Add `User.Read` (for basic profile info) and `Group.Read.All` (if you are using `AZURE_ALLOWED_GROUP_ID` for group-based access).
        
    *   Click "Grant admin consent for YOUR_TENANT_NAME".
        
5.  **Identify Azure AD Group ID (Optional):** If you wish to restrict access to a specific Azure AD group:
    *   Go to Azure Portal > Azure Active Directory (or Azure Entra ID) > Groups.
        
    *   Find your target group and copy its "Object ID". This is your `AZURE_ALLOWED_GROUP_ID`.
        

### Azure App Service Creation

This will host your containerized application.
1.  **Create a Web App for Containers:**
    *   Go to Azure Portal > App Services > Create > Web App.
        
    *   Select your subscription and resource group.
        
    *   Give it a unique name (e.g., `et-csv-viewer`).
        
    *   Publish: `Docker Container`.
        
    *   Operating System: `Linux`.
        
    *   Region: Choose your desired region.
        
    *   App Service Plan: Create a new one or select an existing.
        
    *   Click "Review + create" then "Create".
        
2.  **Configure Docker Image (Initial Setup - will be managed by pipeline later):**
    *   After creation, go to your new App Service.
        
    *   In the left menu, go to "Deployment" > "Deployment Center".
        
    *   Under "Registry settings", select:
        *   Registry Source: `Azure Container Registry`
            
        *   Registry: Select your ACR (`etreportacr`)
            
        *   Image: `csv-viewer`
            
        *   Tag: `latest`
            
    *   Click "Save". (This might be read-only if you immediately connect a pipeline).
        

### Azure App Service Application Settings Configuration

These are the environment variables for your deployed application.
1.  Go to your **App Service** > **Configuration** > **Application settings**.
    
2.  Add the following settings (matching your `.env` but with production values):
    

| Name<br> | Value<br> | Notes<br> |
| --- | --- | --- |
| `AZURE_TENANT_ID`<br> | (Your Azure AD Tenant ID)<br> | From Entra ID App Registration.<br> |
| `AZURE_CLIENT_ID`<br> | (Your Azure AD Client ID)<br> | From Entra ID App Registration.<br> |
| `AZURE_CLIENT_SECRET`<br> | (Your Azure AD Client Secret Value)<br> | **Crucial:** Paste the value you copied earlier.<br> |
| `AZURE_REDIRECT_URI`<br> | `https://YOUR_APP_SERVICE_DEFAULT_DOMAIN.azurewebsites.net/auth/callback` or `https://YOUR_CUSTOM_DOMAIN.com/auth/callback`<br> | This MUST match one of the Redirect URIs in your Entra ID App Registration (and use HTTPS). No port numbers.<br> |
| `AZURE_ALLOWED_GROUP_ID`<br> | (Your Azure AD Group Object ID)<br> | Optional. Leave empty or unset if not using group-based access.<br> |
| `AZURE_STORAGE_ACCOUNT_NAME`<br> | (Your Storage Account Name)<br> |  |
| `AZURE_STORAGE_CONTAINER_NAME`<br> | `csv-files`<br> | Should match the container you created.<br> |
| `WEBSITES_PORT`<br> | `8000`<br> | **Crucial for FastAPI/Uvicorn:** Tells App Service that your container listens on port 8000.<br> |
| `ENV`<br> | `production`<br> | Set to `production` to ensure `secure=True` for cookies.<br> |

Export to Sheets

3.  Click "Save".
    

### Custom Domain and HTTPS Configuration (Optional but Recommended)

1.  **Add Custom Domain:**
    *   In your App Service, go to **"Custom domains"**.
        
    *   Click "Add custom domain".
        
    *   Select "All other domain services".
        
    *   Enter your FQDN (e.g., `csvviewer.yourcompany.com`).
        
    *   Azure will provide DNS records (CNAME, TXT) you need to add at your DNS provider.
        
    *   Verify the domain in Azure.
        
2.  **Bind App Service Managed Certificate:**
    *   In your App Service, go to **"TLS/SSL settings"**.
        
    *   Under "Certificates", select "Create App Service Managed Certificate". Choose your custom domain.
        
    *   Once issued, go to "Bindings" and click "Add TLS/SSL binding".
        
    *   Select your custom domain, choose the managed certificate, and set "TLS/SSL Type" to "SNI SSL". Click "Add Binding".
        
3.  **Enable HTTPS Only:**
    *   In your App Service, go to **"TLS/SSL settings"**.
        
    *   Toggle "HTTPS Only" to **"On"**.
        
    *   This will redirect all HTTP traffic to HTTPS.
        
4.  **UPDATE `AZURE_REDIRECT_URI`:** If you added a custom domain, **you MUST update `AZURE_REDIRECT_URI` in both App Service Application Settings and Azure Entra ID App Registration** to use your custom domain with `https`.
    *   e.g., `https://csvviewer.yourcompany.com/auth/callback`
        
5.  **Review Cookie `domain` in `auth.py`:** If you have `domain="localhost"` in your `response.set_cookie` calls in `auth.py`, it might prevent cookies from being set correctly on your custom domain. It's often best to **remove the `domain` parameter entirely** so the cookie is implicitly set for the current host, or explicitly set it to your root domain (e.g., `domain="yourcompany.com"`).
    

Deployment with Azure DevOps Pipeline (CI/CD)
---------------------------------------------

This section assumes you have an Azure DevOps project and repository set up.

### Service Connection Setup

You need a service connection in Azure DevOps to interact with your Azure resources.
1.  In Azure DevOps, go to Project settings > Service connections.
    
2.  Create a "New service connection" of type "Azure Resource Manager".
    
3.  Select "Service principal (automatic)".
    
4.  Choose your subscription and the resource group containing your App Service, ACR, and Storage Account.
    
5.  Give it a descriptive name (e.g., `AzureSubscriptionServiceConnection`).
    

### Pipeline Variables

Define these variables in your pipeline's `variables` section or in the pipeline library.
YAML

    variables:
      # Azure Resource Names
      ACR_NAME: 'etreportacr' # Your Azure Container Registry name (e.g., etreportacr)
      IMAGE_NAME: 'csv-viewer' # The name of the Docker image (repository name in ACR)
      APP_SERVICE_NAME: 'et-csv-viewer' # Your Azure App Service name
      AZURE_RESOURCE_GROUP: 'YOUR_RESOURCE_GROUP' # The resource group where your resources are located
    
      # Azure DevOps Service Connection
      AZURE_SUBSCRIPTION_SERVICE_CONNECTION: 'AzureSubscriptionServiceConnection' # Name of your Azure DevOps Service Connection
    
      # Build related
      DOCKERFILE_PATH: 'Dockerfile' # Path to your Dockerfile from the repo root
      BUILD_CONTEXT: '.' # Build context for Docker (usually the repo root)
    
      # Optional: For group-based access, though AZURE_ALLOWED_GROUP_ID is set in App Service Config
      # AZURE_ALLOWED_GROUP_ID: 'YOUR_AZURE_AD_GROUP_ID'

### Pipeline YAML (`azure-pipelines.yml`)

Create or update your `azure-pipelines.yml` in your repository.
YAML

    # azure-pipelines.yml
    trigger:
      - master # Trigger pipeline on changes to the 'master' branch
    
    variables:
      # Azure Resource Names (ensure these match your actual resources)
      ACR_NAME: 'etreportacr'
      IMAGE_NAME: 'csv-viewer'
      APP_SERVICE_NAME: 'et-csv-viewer'
      AZURE_RESOURCE_GROUP: 'YOUR_RESOURCE_GROUP' # <--- IMPORTANT: Replace with your actual resource group name
    
      # Azure DevOps Service Connection
      AZURE_SUBSCRIPTION_SERVICE_CONNECTION: 'AzureSubscriptionServiceConnection' # <--- IMPORTANT: Replace with your actual service connection name
    
      # Build related
      DOCKERFILE_PATH: 'Dockerfile'
      BUILD_CONTEXT: '.'
    
    pool:
      vmImage: 'ubuntu-latest' # Or 'windows-latest' if preferred, but Linux is standard for Docker
    
    stages:
      - stage: BuildAndPush
        displayName: 'Build and push image to ACR'
        jobs:
          - job: Build
            displayName: 'Build Docker Image'
            steps:
              - task: Docker@2
                displayName: 'Build and push image to ACR'
                inputs:
                  containerRegistry: $(ACR_NAME) # This uses the ACR_NAME for authentication
                  repository: $(IMAGE_NAME)
                  command: 'buildAndPush'
                  Dockerfile: $(DOCKERFILE_PATH)
                  buildContext: $(BUILD_CONTEXT)
                  tags: |
                    $(Build.BuildId) # Unique tag for each build
                    latest # Always tag the latest successful build as 'latest'
    
      - stage: Deploy
        displayName: 'Deploy to App Service'
        dependsOn: BuildAndPush # Ensure build and push completes first
        jobs:
          - job: DeployJob
            displayName: 'Deploy Web App'
            steps:
              - task: AzureWebAppContainer@1
                displayName: 'Deploy Docker image to Azure App Service'
                inputs:
                  azureSubscription: $(AZURE_SUBSCRIPTION_SERVICE_CONNECTION)
                  appName: $(APP_SERVICE_NAME)
                  resourceGroupName: $(AZURE_RESOURCE_GROUP)
                  imageName: '$(ACR_NAME).azurecr.io/$(IMAGE_NAME):latest' # Full image name including ACR login server

### Run the Pipeline

Commit and push your `azure-pipelines.yml` file to your repository. This will typically trigger the pipeline automatically. You can monitor its progress in Azure DevOps.

Usage
-----

1.  Navigate to your App Service URL (e.g., `https://et-csv-viewer.azurewebsites.net` or `https://csvviewer.yourcompany.com`).
    
2.  You will be redirected to the Microsoft login page for authentication via Azure Entra ID.
    
3.  After successful authentication, you will be redirected back to the application.
    
4.  Use the interface to upload your CSV files.
    
5.  View the content of the uploaded CSVs.
    

Troubleshooting Common Issues
-----------------------------

*   **`Application Error` in App Service:**
    *   **Check App Service Log Stream:** Go to App Service > Log stream. Look for Python tracebacks or startup errors.
        
    *   **Verify `WEBSITES_PORT`:** Ensure `WEBSITES_PORT` is set to `8000` in App Service > Configuration > Application settings.
        
    *   **Check all Application Settings:** Ensure all required `AZURE_*` environment variables are correctly set and matched with your Azure Entra ID and Storage configurations.
        
    *   **Restart App Service:** After any configuration changes.
        
*   **`ERROR: invalid tag "*** /csv-viewer:151433 # Unique tag for each build": invalid reference format` during Docker build in pipeline:**
    *   **Solution:** Remove comments from the `tags:` section in your `azure-pipelines.yml`. Each tag should be on its own line without `#` symbols.
        YAML
        
            tags: |
              $(Build.BuildId)
              latest
        
*   **`DockerApiException: ... dial tcp: lookup yourcompanycsvacr.azurecr.io: no such host`:**
    *   **Cause:** Mismatch in your Azure Container Registry name. Your App Service or pipeline is trying to pull from an ACR name that doesn't exist or is misspelled.
        
    *   **Solution:**
        1.  Verify the exact "Login server" name of your ACR in Azure Portal (e.g., `etreportacr.azurecr.io`).
            
        2.  Ensure this exact name (or the part before `.azurecr.io` if using a variable like `ACR_NAME`) is used consistently in:
            *   Your Azure DevOps Pipeline variables (`ACR_NAME`).
                
            *   The `imageName` in the `AzureWebAppContainer@1` task (`$(ACR_NAME).azurecr.io/$(IMAGE_NAME):latest`).
                
            *   (If manually set) App Service > Deployment Center > Container settings.
                
*   **`AADSTS50011: The redirect URI 'http://...' specified in the request does not match the redirect URIs configured for the application ...`:**
    *   **Cause:** The Redirect URI your application sends to Azure Entra ID does not exactly match one configured in your Entra ID App Registration. Common issues are `http` vs `https`, incorrect domain, or including a port number (`:8000`).
        
    *   **Solution:**
        1.  **In App Service > Configuration > Application settings:** Update `AZURE_REDIRECT_URI` to `https://YOUR_APP_SERVICE_OR_CUSTOM_DOMAIN/auth/callback` (no port).
            
        2.  **In Azure Portal > Azure Active Directory > App registrations > Your App > Authentication:** Add the exact `https://YOUR_APP_SERVICE_OR_CUSTOM_DOMAIN/auth/callback` to the Redirect URIs list. Remove any incorrect entries.
            
*   **"Image name" in App Service Deployment Center is not clickable/editable:**
    *   **Cause:** Your App Service's container deployment is fully managed by Azure DevOps Pipeline.
        
    *   **Solution:** All changes to the image name or tag must be made in your `azure-pipelines.yml` file, as described in the "Deployment with Azure DevOps Pipeline" section.
        
*   **Cookies not working after deployment (e.g., authentication loop):**
    *   **Check `secure` flag:** Ensure `ENV` is set to `production` in App Service Application Settings. This will make `IS_PRODUCTION_ENV` True and ensure cookies are set with `secure=True`.
        
    *   **Check `domain` parameter in `response.set_cookie`:** If `domain="localhost"` is present in your `auth.py`, it will prevent cookies from being set for your App Service domain. It's usually best to remove the `domain` parameter so the cookie applies to the current host, or set it explicitly to your root custom domain.
        

Folder Structure
----------------

```
    ├── .azuredevops/             # Azure DevOps pipeline files (if separated)
    │   └── azure-pipelines.yml
    ├── .env                      # Environment variables for local development (ignored in git)
    ├── Dockerfile                # Defines the Docker image for the application
    ├── docker-compose.yml        # For local development with Docker Compose
    ├── main.py                   # Main FastAPI application entry point
    ├── auth.py                   # Authentication logic for Azure AD
    ├── config.py                 # Configuration loading (from env variables)
    ├── requirements.txt          # Python dependencies
    ├── static/                   # Static files (CSS, JS, images)
    │   └── ...
    ├── templates/                # Jinja2 HTML templates
    │   └── ...
    └── README.md                 # This file
```
Contributing
------------

Feel free to open issues or submit pull requests if you have suggestions or improvements.

License
-------

This project is licensed under the MIT License - see the `LICENSE` file for details (if you have one).