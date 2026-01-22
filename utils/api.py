import os
import aiohttp
import secrets
import string
from typing import Optional, Dict, Any, Tuple, List

PANEL_URL = os.getenv("PTERODACTYL_PANEL_URL", "").rstrip("/")
API_KEY = os.getenv("PTERODACTYL_API_KEY", "")
DEFAULT_USER_PASSWORD_LENGTH = int(os.getenv("DEFAULT_USER_PASSWORD_LENGTH", 16))

if not PANEL_URL or not API_KEY:
    raise RuntimeError("PTERODACTYL_PANEL_URL and PTERODACTYL_API_KEY must be set in environment")

HEADERS = {
    "Authorization": f"Bearer {API_KEY}",
    "Accept": "Application/vnd.pterodactyl.v1+json",
    "Content-Type": "application/json"
}

_session: Optional[aiohttp.ClientSession] = None

def _get_session() -> aiohttp.ClientSession:
    global _session
    if _session is None or _session.closed:
        _session = aiohttp.ClientSession()
    return _session

async def close_session():
    global _session
    if _session:
        await _session.close()
        _session = None

def random_password(length: int = DEFAULT_USER_PASSWORD_LENGTH) -> str:
    alphabet = string.ascii_letters + string.digits + "-_"
    return ''.join(secrets.choice(alphabet) for _ in range(length))

# -----------------
# Node / Egg
# -----------------
async def get_node(node_id: int) -> Dict[str, Any]:
    url = f"{PANEL_URL}/api/application/nodes/{node_id}"
    async with _get_session().get(url, headers=HEADERS) as resp:
        data = await resp.json()
        return {"status": resp.status, "data": data}

async def list_nodes() -> Dict[str, Any]:
    url = f"{PANEL_URL}/api/application/nodes"
    async with _get_session().get(url, headers=HEADERS) as resp:
        data = await resp.json()
        return {"status": resp.status, "data": data}

async def get_egg(egg_id: int) -> Dict[str, Any]:
    url = f"{PANEL_URL}/api/application/eggs/{egg_id}"
    async with _get_session().get(url, headers=HEADERS) as resp:
        data = await resp.json()
        return {"status": resp.status, "data": data}

async def list_eggs() -> Dict[str, Any]:
    url = f"{PANEL_URL}/api/application/nests"
    # Many panels list eggs nested under nests; for simplicity, fetch nests then eggs per nest
    async with _get_session().get(url, headers=HEADERS) as resp:
        nests = await resp.json()
        return {"status": resp.status, "data": nests}

# -----------------
# Users
# -----------------
async def find_user_by_email(email: str) -> Optional[Dict[str, Any]]:
    # Try filter endpoint
    url = f"{PANEL_URL}/api/application/users?filter[email]={email}"
    async with _get_session().get(url, headers=HEADERS) as resp:
        if resp.status != 200:
            return None
        data = await resp.json()
        if isinstance(data, dict) and data.get("data"):
            # return first user's attributes
            return data["data"][0].get("attributes", data["data"][0])
    return None

async def list_users() -> Dict[str, Any]:
    url = f"{PANEL_URL}/api/application/users"
    async with _get_session().get(url, headers=HEADERS) as resp:
        data = await resp.json()
        return {"status": resp.status, "data": data}

async def search_users(query: str) -> Dict[str, Any]:
    # No standardized search; filter by username or email if supported
    # Try email filter first
    url = f"{PANEL_URL}/api/application/users?filter[email]={query}"
    async with _get_session().get(url, headers=HEADERS) as resp:
        data = await resp.json()
        return {"status": resp.status, "data": data}

async def create_user(email: str, username: str, first_name: str = "Panel", last_name: str = "User", password: Optional[str] = None) -> Dict[str, Any]:
    if password is None:
        password = random_password()
    payload = {
        "email": email,
        "username": username,
        "first_name": first_name,
        "last_name": last_name,
        "password": password
    }
    url = f"{PANEL_URL}/api/application/users"
    async with _get_session().post(url, json=payload, headers=HEADERS) as resp:
        try:
            data = await resp.json()
        except Exception:
            data = {}
        return {"status": resp.status, "data": data, "password": password if resp.status in (200,201) else None}

async def delete_user(user_id: int) -> Dict[str, Any]:
    url = f"{PANEL_URL}/api/application/users/{user_id}"
    async with _get_session().delete(url, headers=HEADERS) as resp:
        if resp.status in (204, 200):
            return {"status": resp.status, "data": {}}
        data = await resp.json()
        return {"status": resp.status, "data": data}

async def change_user_password(user_id: int, new_password: Optional[str] = None) -> Dict[str, Any]:
    if new_password is None:
        new_password = random_password()
    payload = {"password": new_password}
    url = f"{PANEL_URL}/api/application/users/{user_id}/reset-password"
    # Some panel versions use different endpoints; try a generic PUT to user endpoint if reset fails.
    async with _get_session().post(url, json=payload, headers=HEADERS) as resp:
        # If panel doesn't support, return fallback
        if resp.status in (200, 204):
            return {"status": resp.status, "data": {}, "password": new_password}
        try:
            data = await resp.json()
        except Exception:
            data = {}
        return {"status": resp.status, "data": data}

# -----------------
# Servers
# -----------------
async def get_node_allocations(node_id: int) -> Tuple[int, Optional[Dict[str, Any]]]:
    url = f"{PANEL_URL}/api/application/nodes/{node_id}/allocations"
    async with _get_session().get(url, headers=HEADERS) as resp:
        data = await resp.json()
        return resp.status, data

async def create_server(
    name: str,
    user_id: int,
    node_id: int,
    egg_id: int,
    ram: int,
    cpu: int,
    disk: int,
    version: str,
    startup: Optional[str] = None
) -> Dict[str, Any]:
    # Get allocations for node
    alloc_status, alloc_data = await get_node_allocations(node_id)
    if alloc_status != 200:
        return {"status": alloc_status, "error": "Failed to fetch node allocations", "data": alloc_data}
    allocations = alloc_data.get("data", []) if isinstance(alloc_data, dict) else []
    if not allocations:
        return {"status": 400, "error": "No allocations available on node", "data": alloc_data}
    alloc_id = allocations[0]["attributes"]["id"]

    payload = {
        "name": name,
        "user": user_id,
        "egg": egg_id,
        "startup": startup or "",
        "docker_image": None,
        "environment": {},
        "limits": {
            "memory": ram,
            "swap": 0,
            "disk": disk,
            "io": 500,
            "cpu": cpu
        },
        "feature_limits": {
            "databases": 0,
            "backups": 0
        },
        "allocation": {
            "default": alloc_id
        }
    }
    url = f"{PANEL_URL}/api/application/servers"
    async with _get_session().post(url, json=payload, headers=HEADERS) as resp:
        try:
            data = await resp.json()
        except Exception:
            data = {}
        return {"status": resp.status, "data": data}

async def delete_server(server_id: str) -> Dict[str, Any]:
    url = f"{PANEL_URL}/api/application/servers/{server_id}"
    async with _get_session().delete(url, headers=HEADERS) as resp:
        if resp.status in (204, 200):
            return {"status": resp.status, "data": {}}
        data = await resp.json()
        return {"status": resp.status, "data": data}

async def suspend_server(server_id: str) -> Dict[str, Any]:
    url = f"{PANEL_URL}/api/application/servers/{server_id}/suspend"
    async with _get_session().post(url, headers=HEADERS) as resp:
        try:
            data = await resp.json()
        except Exception:
            data = {}
        return {"status": resp.status, "data": data}

async def unsuspend_server(server_id: str) -> Dict[str, Any]:
    url = f"{PANEL_URL}/api/application/servers/{server_id}/unsuspend"
    async with _get_session().post(url, headers=HEADERS) as resp:
        try:
            data = await resp.json()
        except Exception:
            data = {}
        return {"status": resp.status, "data": data}

async def set_server_resources(server_id: str, memory: Optional[int] = None, cpu: Optional[int] = None, disk: Optional[int] = None) -> Dict[str, Any]:
    payload = {"limits": {}}
    if memory is not None:
        payload["limits"]["memory"] = memory
    if cpu is not None:
        payload["limits"]["cpu"] = cpu
    if disk is not None:
        payload["limits"]["disk"] = disk
    url = f"{PANEL_URL}/api/application/servers/{server_id}/build"
    async with _get_session().put(url, json=payload, headers=HEADERS) as resp:
        try:
            data = await resp.json()
        except Exception:
            data = {}
        return {"status": resp.status, "data": data}

async def get_server(server_id: str) -> Dict[str, Any]:
    url = f"{PANEL_URL}/api/application/servers/{server_id}"
    async with _get_session().get(url, headers=HEADERS) as resp:
        try:
            data = await resp.json()
        except Exception:
            data = {}
        return {"status": resp.status, "data": data}

async def list_servers() -> Dict[str, Any]:
    url = f"{PANEL_URL}/api/application/servers"
    async with _get_session().get(url, headers=HEADERS) as resp:
        try:
            data = await resp.json()
        except Exception:
            data = {}
        return {"status": resp.status, "data": data}

# -----------------
# Backups
# -----------------
async def list_backups(server_id: str) -> Dict[str, Any]:
    url = f"{PANEL_URL}/api/application/servers/{server_id}/backups"
    async with _get_session().get(url, headers=HEADERS) as resp:
        try:
            data = await resp.json()
        except Exception:
            data = {}
        return {"status": resp.status, "data": data}

# -----------------
# Utility / Health
# -----------------
async def ping_panel() -> bool:
    url = f"{PANEL_URL}/api/application"
    try:
        async with _get_session().get(url, headers=HEADERS, timeout=10) as resp:
            return resp.status == 200
    except Exception:
        return False
