import os
import httpx
import secrets
from jose import jwt, jwk
from jose.exceptions import ExpiredSignatureError, JWTClaimsError, JWTError
from fastapi import Request, HTTPException
from fastapi.responses import RedirectResponse
from urllib.parse import quote_plus, urlencode, parse_qs
from datetime import datetime, timedelta
import base64
import json
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# --- Azure AD Configuration ---
TENANT_ID = os.getenv("AZURE_TENANT_ID")
CLIENT_ID = os.getenv("AZURE_CLIENT_ID")
CLIENT_SECRET = os.getenv("AZURE_CLIENT_SECRET")
REDIRECT_URI = os.getenv("AZURE_REDIRECT_URI")
ALLOWED_SECURITY_GROUP_ID = os.getenv("AZURE_ALLOWED_GROUP_ID")

IS_PRODUCTION_ENV = os.getenv("ENV") == "production"

if not all([TENANT_ID, CLIENT_ID, CLIENT_SECRET, REDIRECT_URI, ALLOWED_SECURITY_GROUP_ID]):
    raise ValueError("One or more Azure AD environment variables are not set.")

# Azure AD Endpoints
AUTHORITY = f"https://login.microsoftonline.com/{TENANT_ID}"
AUTHORIZE_ENDPOINT = f"{AUTHORITY}/oauth2/v2.0/authorize"
TOKEN_ENDPOINT = f"{AUTHORITY}/oauth2/v2.0/token"
JWKS_URI = f"{AUTHORITY}/discovery/v2.0/keys"
GRAPH_API_URL_ME_MEMBEROF = "https://graph.microsoft.com/v1.0/me/memberOf"

# Cache for public keys
_cached_jwks_keys = None
_jwks_last_updated = None
JWKS_CACHE_DURATION = timedelta(hours=24)

# In-memory session store (use Redis/database in production)
# Format: {session_id: {"user_claims": {...}, "expires_at": datetime, "access_token": "..."}}
user_sessions = {}

def cleanup_expired_sessions():
    """Remove expired sessions from memory"""
    current_time = datetime.now()
    expired_sessions = [sid for sid, session in user_sessions.items() 
                       if session.get("expires_at", current_time) < current_time]
    for sid in expired_sessions:
        del user_sessions[sid]
        print(f"[DEBUG] Cleaned up expired session: {sid}")

async def _get_public_keys() -> list[dict]:
    """
    Fetches and caches public keys from Azure AD's JWKS URI.
    Returns a list of JWK dictionaries.
    """
    global _cached_jwks_keys, _jwks_last_updated

    if _cached_jwks_keys and _jwks_last_updated and (datetime.now() - _jwks_last_updated < JWKS_CACHE_DURATION):
        return _cached_jwks_keys

    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(JWKS_URI)
            response.raise_for_status()
            jwks_data = response.json()
            _cached_jwks_keys = jwks_data.get("keys")
            _jwks_last_updated = datetime.now()
            if not _cached_jwks_keys:
                raise ValueError("No keys found in JWKS response.")
            return _cached_jwks_keys
        except httpx.HTTPStatusError as e:
            print(f"Error fetching JWKS: {e.response.status_code} - {e.response.text}")
            raise HTTPException(status_code=500, detail="Could not fetch public keys for token validation.")
        except httpx.RequestError as e:
            print(f"Network error fetching JWKS: {e}")
            raise HTTPException(status_code=500, detail="Network error fetching public keys.")
        except ValueError as e:
            print(f"Error processing JWKS response: {e}")
            raise HTTPException(status_code=500, detail=f"Error processing public keys: {e}")

async def verify_token(token: str) -> dict:
    """
    Verifies the JWT (ID token) against Azure AD's public keys.
    """
    try:
        print(f"[DEBUG] Starting token verification")
        jwks_list = await _get_public_keys()
        print(f"[DEBUG] Retrieved {len(jwks_list)} public keys for verification")

        payload = jwt.decode(
            token,
            key=jwks_list,
            algorithms=["RS256"],
            audience=CLIENT_ID,
            issuer=f"https://login.microsoftonline.com/{TENANT_ID}/v2.0",
            options={
                "verify_signature": True,
                "verify_aud": True,
                "verify_iss": True,
                "verify_exp": True,
                "verify_at_hash": False
            }
        )
        print(f"[DEBUG] Token verification successful")
        return payload
        
    except ExpiredSignatureError as e:
        print(f"[ERROR] Token has expired: {e}")
        raise HTTPException(status_code=401, detail="Token has expired.")
    except JWTClaimsError as e:
        print(f"[ERROR] Invalid token claims: {e}")
        raise HTTPException(status_code=401, detail=f"Invalid token claims: {e}")
    except JWTError as e:
        print(f"[ERROR] JWT error during verification: {e}")
        raise HTTPException(status_code=401, detail=f"Invalid token: {e}")
    except Exception as e:
        print(f"[ERROR] Unexpected error during token verification: {type(e).__name__}: {e}")
        raise HTTPException(status_code=401, detail=f"Token verification failed: {type(e).__name__}")

async def login(request: Request):
    """Initiates the Azure AD login flow."""
    # Clean up expired sessions periodically
    cleanup_expired_sessions()
    
    original_target_url = request.query_params.get("redirect_to", "/")
    
    state_data = {
        "nonce": base64.urlsafe_b64encode(os.urandom(16)).decode('utf-8'),
        "original_path": original_target_url
    }
    state = base64.urlsafe_b64encode(json.dumps(state_data).encode('utf-8')).decode('utf-8')

    auth_params = {
        "client_id": CLIENT_ID,
        "response_type": "code",
        "redirect_uri": REDIRECT_URI,
        "response_mode": "query",
        "scope": "openid profile email User.Read GroupMember.Read.All offline_access",
        "state": state,
        "prompt": "select_account"
    }
    authorization_url = f"{AUTHORIZE_ENDPOINT}?{urlencode(auth_params, quote_via=quote_plus)}"
    
    response = RedirectResponse(url=authorization_url)
    response.set_cookie(
        key="oauth_state",
        value=state,
        httponly=True,
        max_age=300,
        samesite="Lax",
        secure=IS_PRODUCTION_ENV
    )
    return response

async def auth_callback(request: Request):
    """Handles the callback from Azure AD after authentication."""
    try:
        print(f"[DEBUG] Starting auth_callback processing")
        
        # Clean up expired sessions
        cleanup_expired_sessions()
        
        query_params = request.query_params
        error = query_params.get("error")
        error_description = query_params.get("error_description")

        if error:
            print(f"[ERROR] Authentication error during callback: {error_description or error}")
            raise HTTPException(status_code=400, detail=f"Authentication error: {error_description or error}")

        code = query_params.get("code")
        received_state = query_params.get("state")
        expected_state_cookie = request.cookies.get("oauth_state")

        print(f"[DEBUG] Received state: {received_state}")
        print(f"[DEBUG] Expected state from cookie: {expected_state_cookie}")
        print(f"[DEBUG] Authorization code received: {bool(code)}")

        if not code or not received_state or received_state != expected_state_cookie:
            print(f"[ERROR] State mismatch or missing code")
            raise HTTPException(status_code=400, detail="Invalid state or missing authorization code.")

        print(f"[DEBUG] State validation passed, proceeding with token exchange")

        # Decode original path from state
        original_path = "/"
        try:
            state_data_decoded = json.loads(base64.urlsafe_b64decode(received_state).decode('utf-8'))
            original_path = state_data_decoded.get("original_path", "/")
            print(f"[DEBUG] Decoded original path: {original_path}")
        except Exception as e:
            print(f"[WARNING] Error decoding state parameter: {e}")

        # Exchange authorization code for tokens
        token_params = {
            "client_id": CLIENT_ID,
            "scope": "openid profile email User.Read GroupMember.Read.All offline_access",
            "code": code,
            "redirect_uri": REDIRECT_URI,
            "grant_type": "authorization_code",
            "client_secret": CLIENT_SECRET,
        }

        print(f"[DEBUG] Making token exchange request")

        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                token_response = await client.post(TOKEN_ENDPOINT, data=token_params)
                print(f"[DEBUG] Token exchange response status: {token_response.status_code}")
                token_response.raise_for_status()
                token_data = token_response.json()
                print(f"[DEBUG] Token exchange successful")
            except Exception as e:
                print(f"[ERROR] Token exchange failed: {type(e).__name__}: {e}")
                raise HTTPException(status_code=500, detail="Failed to exchange authorization code for tokens.")

        id_token = token_data.get("id_token")
        access_token = token_data.get("access_token")

        if not id_token or not access_token:
            raise HTTPException(status_code=500, detail="Missing ID token or Access token in response.")

        # Log token sizes
        id_token_size = len(id_token)
        access_token_size = len(access_token)
        print(f"[DEBUG] ID Token size: {id_token_size} chars")
        print(f"[DEBUG] Access Token size: {access_token_size} chars")

        # Verify ID Token
        try:
            id_token_claims = await verify_token(id_token)
            print(f"[DEBUG] Token verification successful for user: {id_token_claims.get('preferred_username')}")
        except HTTPException as e:
            print(f"[ERROR] ID Token verification failed: {e.detail}")
            raise

        # Process user groups
        user_groups = id_token_claims.get("groups", [])
        print(f"[DEBUG] Groups in ID token: {len(user_groups)}")
        
        if not user_groups:
            try:
                print(f"[DEBUG] Querying Graph API for groups")
                user_groups = await get_user_groups(access_token)
                print(f"[DEBUG] Retrieved {len(user_groups)} groups from Graph API")
            except HTTPException as e:
                print(f"[ERROR] Failed to fetch user groups: {e.detail}")
                raise

        if ALLOWED_SECURITY_GROUP_ID not in user_groups:
            print(f"[ERROR] User not in allowed group")
            raise HTTPException(status_code=403, detail="User not in allowed group.")

        print(f"[DEBUG] User authorized, creating session")

        # CREATE SESSION INSTEAD OF LARGE COOKIE
        session_id = secrets.token_urlsafe(32)
        session_expires = datetime.now() + timedelta(hours=1)
        
        # Store user data in session
        user_sessions[session_id] = {
            "user_claims": id_token_claims,
            "access_token": access_token,
            "expires_at": session_expires,
            "created_at": datetime.now()
        }
        
        print(f"[DEBUG] Created session {session_id} for user {id_token_claims.get('preferred_username')}")
        print(f"[DEBUG] Total active sessions: {len(user_sessions)}")

        # Create response and set small session cookie
        response = RedirectResponse(url=original_path)
        
        # Determine domain
        host = request.headers.get("host", "").lower()
        cookie_domain = None
        if "sitecore.net" in host:
            cookie_domain = ".sitecore.net"
        
        print(f"[DEBUG] Setting session cookie - Host: {host}, Domain: {cookie_domain}, Secure: {IS_PRODUCTION_ENV}")

        # Set small session ID cookie instead of large token
        cookie_params = {
            "key": "session_id",  # Changed from "id_token" to "session_id"
            "value": session_id,  # Small session ID instead of large token
            "httponly": True,
            "max_age": 3600,
            "samesite": "Lax",
            "secure": IS_PRODUCTION_ENV
        }
        
        if cookie_domain:
            cookie_params["domain"] = cookie_domain
            
        response.set_cookie(**cookie_params)
        
        # Clear the oauth_state cookie
        delete_params = {"key": "oauth_state", "secure": IS_PRODUCTION_ENV}
        if cookie_domain:
            delete_params["domain"] = cookie_domain
        response.delete_cookie(**delete_params)
        
        print(f"[DEBUG] Session cookie set successfully (size: {len(session_id)} chars)")
        print(f"[DEBUG] Authentication completed successfully for {id_token_claims.get('preferred_username')}")
        
        return response

    except HTTPException:
        raise
    except Exception as e:
        print(f"[CRITICAL ERROR] Unhandled exception in auth_callback: {type(e).__name__}: {e}")
        import traceback
        print(f"[CRITICAL ERROR] Traceback: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Internal authentication error: {type(e).__name__}")

async def get_user_groups(access_token: str) -> list[str]:
    """
    Fetches the user's group memberships using the Microsoft Graph API.
    """
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }
    graph_url = f"{GRAPH_API_URL_ME_MEMBEROF}?$select=id&$top=999"

    async with httpx.AsyncClient() as client:
        try:
            resp = await client.get(graph_url, headers=headers)
            resp.raise_for_status()
            data = resp.json()
            groups = []
            for entry in data.get("value", []):
                if entry.get("@odata.type") == "#microsoft.graph.group":
                    groups.append(entry.get("id"))
            return groups
        except httpx.HTTPStatusError as e:
            print(f"Graph API call failed: HTTP Status {e.response.status_code} - {e.response.text}")
            raise HTTPException(status_code=e.response.status_code, detail=f"Failed to get user groups from Graph API: {e.response.text}")
        except httpx.RequestError as e:
            print(f"Network error during Graph API call: {e}")
            raise HTTPException(status_code=500, detail=f"Network error during Graph API call: {e}")

async def get_current_user(request: Request) -> dict | RedirectResponse:
    """
    FastAPI dependency to retrieve current user from session instead of cookie token.
    """
    session_id = request.cookies.get("session_id")  # Changed from "id_token" to "session_id"
    print(f"[DEBUG] Session ID from cookie: {session_id}")
    
    if not session_id:
        print("[DEBUG] No session ID found in cookies. Redirecting to login.")
        return RedirectResponse(url=f"/login?redirect_to={quote_plus(str(request.url))}")

    # Clean up expired sessions
    cleanup_expired_sessions()
    
    # Check if session exists and is valid
    session_data = user_sessions.get(session_id)
    if not session_data:
        print(f"[DEBUG] Session {session_id} not found. Redirecting to login.")
        return RedirectResponse(url=f"/login?redirect_to={quote_plus(str(request.url))}")
    
    # Check if session is expired
    if session_data.get("expires_at", datetime.now()) < datetime.now():
        print(f"[DEBUG] Session {session_id} expired. Cleaning up and redirecting to login.")
        del user_sessions[session_id]
        return RedirectResponse(url=f"/login?redirect_to={quote_plus(str(request.url))}")
    
    # Return user claims from session
    user_claims = session_data.get("user_claims", {})
    print(f"[DEBUG] Retrieved user from session: {user_claims.get('preferred_username')}")
    return user_claims

# Optional: Add endpoint to check session status
async def session_status(request: Request):
    """Debug endpoint to check session status"""
    session_id = request.cookies.get("session_id")
    if not session_id:
        return {"session_id": None, "status": "no_session"}
    
    session_data = user_sessions.get(session_id)
    if not session_data:
        return {"session_id": session_id, "status": "session_not_found"}
    
    return {
        "session_id": session_id,
        "status": "active",
        "user": session_data.get("user_claims", {}).get("preferred_username"),
        "expires_at": session_data.get("expires_at").isoformat() if session_data.get("expires_at") else None,
        "total_sessions": len(user_sessions)
    }