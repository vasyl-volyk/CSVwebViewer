from fastapi import FastAPI, Request, Depends, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from starlette.templating import Jinja2Templates
import csv
import io
import os

from auth import login, auth_callback, get_current_user

# Import ASYNCHRONOUS versions of Azure Blob Storage and Azure Identity
from azure.storage.blob.aio import BlobServiceClient as AsyncBlobServiceClient
from azure.identity.aio import DefaultAzureCredential as AsyncDefaultAzureCredential
from dotenv import load_dotenv
from datetime import datetime # Import datetime for formatting

load_dotenv() # Load environment variables

app = FastAPI()
templates = Jinja2Templates(directory="templates")

# Azure Storage Configuration
AZURE_STORAGE_ACCOUNT_NAME = os.getenv("AZURE_STORAGE_ACCOUNT_NAME")
AZURE_STORAGE_CONTAINER_NAME = os.getenv("AZURE_STORAGE_CONTAINER_NAME")

if not all([AZURE_STORAGE_ACCOUNT_NAME, AZURE_STORAGE_CONTAINER_NAME]):
    raise ValueError(
        "One or more Azure Storage environment variables are not set. "
        "Please set AZURE_STORAGE_ACCOUNT_NAME and AZURE_STORAGE_CONTAINER_NAME."
    )

# Declare global variables to hold the async clients
global_blob_service_client = None
global_container_client = None
global_credential = None

@app.on_event("startup")
async def startup_event():
    global global_blob_service_client, global_container_client, global_credential
    try:
        global_credential = AsyncDefaultAzureCredential()
        global_blob_service_client = AsyncBlobServiceClient(
            account_url=f"https://{AZURE_STORAGE_ACCOUNT_NAME}.blob.core.windows.net",
            credential=global_credential
        )
        global_container_client = global_blob_service_client.get_container_client(AZURE_STORAGE_CONTAINER_NAME)
        print("Azure Blob Storage async clients initialized successfully.")
    except Exception as e:
        print(f"Failed to initialize Azure Blob Storage async clients: {e}")
        raise

@app.on_event("shutdown")
async def shutdown_event():
    global global_blob_service_client, global_container_client, global_credential
    if global_container_client:
        await global_container_client.close()
    if global_blob_service_client:
        await global_blob_service_client.close()
    if global_credential:
        await global_credential.close()
    print("Azure Blob Storage async clients closed.")


# --- Helper functions for Azure Blob Storage operations (use global clients) ---

async def list_blob_path_contents(path: str):
    """
    Lists directories and files (blobs) under a given path, including file metadata.
    Returns a list of dictionaries with 'name', 'is_dir', and 'last_modified' (for files).
    """
    path = path.strip('/')
    prefix = f"{path}/" if path else ""

    directories = set()
    files_info = [] # Store {"name": ..., "last_modified": ...}

    try:
        async for blob in global_container_client.list_blobs(name_starts_with=prefix):
            relative_name = blob.name[len(prefix):]

            if '/' in relative_name:
                dir_name = relative_name.split('/')[0]
                if dir_name:
                    directories.add(dir_name)
            else:
                # --- START OF CHANGE ---
                # Only add file if its name is not empty AND it ends with .csv
                if relative_name and relative_name.lower().endswith(".csv"):
                    last_modified_dt = blob.last_modified
                    last_modified_str = last_modified_dt.strftime("%Y-%m-%d %H:%M") if last_modified_dt else "N/A"
                    files_info.append({"name": relative_name, "last_modified": last_modified_str})
                # --- END OF CHANGE ---

        result_entries = []
        for dir_name in sorted(list(directories), key=str.lower):
            result_entries.append({"name": dir_name + "/", "is_dir": True, "last_modified": None})

        for file_info in sorted(files_info, key=lambda x: x["name"].lower()):
            result_entries.append({"name": file_info["name"], "is_dir": False, "last_modified": file_info["last_modified"]})

        return result_entries

    except Exception as e:
        print(f"Error listing blobs for path '{path}': {e}")
        raise HTTPException(status_code=500, detail=f"Error accessing Azure Blob Storage: {e}")

async def get_blob_content(blob_path: str) -> bytes:
    """
    Downloads the content of a blob from Azure Blob Storage.
    """
    if not blob_path:
        raise HTTPException(status_code=400, detail="Blob name cannot be empty.")
        
    try:
        blob_client = global_container_client.get_blob_client(blob_path)
        
        if not await blob_client.exists():
            raise HTTPException(status_code=404, detail="File not found in Azure Blob Storage.")
        
        download_stream = await blob_client.download_blob()
        return await download_stream.readall()
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error downloading blob '{blob_path}': {e}")
        raise HTTPException(status_code=500, detail=f"Error downloading file from Azure Blob Storage: {e}")

async def is_blob_path_directory(blob_path: str) -> bool:
    """
    Checks if a given path in Azure Blob Storage acts like a directory.
    If blob_path is empty, it means the root of the container.
    """
    prefix = f"{blob_path.strip('/')}/" if blob_path else ""
    try:
        async for _ in global_container_client.list_blobs(name_starts_with=prefix):
            return True
        return False
    except Exception as e:
        print(f"Error checking blob path '{blob_path}' for directory-like behavior: {e}")
        raise HTTPException(status_code=500, detail=f"Error checking path in Azure Blob Storage: {e}")

async def blob_exists(blob_path: str) -> bool:
    """
    Checks if a specific blob exists.
    """
    if not blob_path:
        return False
        
    try:
        blob_client = global_container_client.get_blob_client(blob_path)
        return await blob_client.exists()
    except Exception as e:
        print(f"Error checking blob existence for '{blob_path}': {e}")
        raise HTTPException(status_code=500, detail=f"Error checking file existence in Azure Blob Storage: {e}")


# --- FastAPI Routes ---

@app.get("/login")
async def login_route(request: Request):
    return await login(request)

@app.get("/auth/callback")
async def auth_callback_route(request: Request):
    return await auth_callback(request)

@app.get("/logout")
async def logout():
    response = RedirectResponse(url="/login")
    response.delete_cookie("id_token")
    return response

@app.get("/", response_class=HTMLResponse)
async def browse_root(request: Request):
    user = await get_current_user(request)
    if isinstance(user, RedirectResponse):
        return user
    return await browse_path(request, "")

@app.get("/browse/{full_path:path}", response_class=HTMLResponse)
async def browse_path(request: Request, full_path: str, user=Depends(get_current_user)):
    if isinstance(user, RedirectResponse):
        return user

    clean_full_path = full_path.strip("/")
    
    if not clean_full_path:
        is_dir = await is_blob_path_directory(clean_full_path)
        is_file = False
    else:
        is_dir = await is_blob_path_directory(clean_full_path)
        is_file = await blob_exists(clean_full_path)

    if not is_dir and not is_file:
        return HTMLResponse("Path not found", status_code=404)

    if is_dir:
        entries = await list_blob_path_contents(clean_full_path)
        
        parent_path = None
        if clean_full_path:
            parts = clean_full_path.split("/")
            if len(parts) > 1:
                parent_path = "/".join(parts[:-1])
            elif len(parts) == 1:
                parent_path = ""

        return templates.TemplateResponse("browse.html", {
            "request": request,
            "entries": entries,
            "current_path": clean_full_path,
            "parent_path": parent_path,
            "user": user
        })
    elif is_file and clean_full_path.endswith(".csv"):
        try:
            csv_content_bytes = await get_blob_content(clean_full_path)
            csv_content_str = csv_content_bytes.decode("utf-8")
            
            f = io.StringIO(csv_content_str)
            reader = csv.reader(f)
            rows = list(reader)

            if not rows:
                return HTMLResponse("CSV file is empty or malformed.", status_code=400)
            
            # FIXED: Extract current_path and filename separately
            path_parts = clean_full_path.split('/')
            current_path = '/'.join(path_parts[:-1]) if len(path_parts) > 1 else ''
            filename_only = path_parts[-1]
            
            return templates.TemplateResponse("csv_table.html", {
                "request": request,
                "filename": filename_only,  # Only filename
                "current_path": current_path,  # Path to folder
                "rows": rows,
                "user": user
            })
        except HTTPException as e:
            raise e
        except Exception as e:
            return HTMLResponse(f"Error reading CSV file from Azure Blob Storage: {e}", status_code=500)
    else:
        return HTMLResponse("Not a CSV file or a valid directory.", status_code=400)