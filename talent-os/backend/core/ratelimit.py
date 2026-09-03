"""
Talent OS — WS-E.4: shared rate limiter + client-IP key function.

One slowapi Limiter instance is imported everywhere a route wants
`@limiter.limit(...)` (main.py, routers/auth.py, routers/public.py, ...).
Before this, main.py, routers/auth.py and routers/public.py each built
their *own* `Limiter(key_func=get_remote_address)` — three separate
in-memory counters that never saw each other's requests, so e.g. a client
alternating requests across auth and public endpoints was never actually
capped at the intended combined rate. There is exactly one Limiter object
now, built here, and every router imports `limiter` from this module.

IMPORTANT — in-memory limits are per worker process. Production runs the
API under `settings.backend_workers` (4) separate uvicorn worker
processes (see main.py's `uvicorn.run(..., workers=settings.backend_workers)`),
each with its own Python process memory and therefore its own independent
copy of this Limiter's counters. slowapi's default in-memory storage is
NOT shared across processes (no Redis backend is wired up here), so a
limit declared as "10/minute" is actually enforced as up to
"10 * backend_workers per minute" (worst case ~40/minute today) against
any given key, depending on which worker happens to handle each request.
This is accepted for WS-E.4 (matches the account-lockout counter below,
which IS shared cross-worker via the `users` table and is the real
backstop against credential stuffing) — a future step could point slowapi
at a shared Redis storage_uri to make the in-memory limits exact across
workers too, but that's out of scope here. The Cloudflare edge rate rule
documented in docs/M0-EIGENAAR-CHECKLIST.md is the actual cross-worker,
cross-restart backstop for /api/auth/*.

Key function precedence (see get_client_ip / rate_limit_key below):
  1. `CF-Connecting-IP` — Cloudflare's own header, set on every request
     that reaches origin through Cloudflare's proxy; the request never
     travels through Cloudflare's own network with a *forged* value of
     this header still attached (Cloudflare overwrites it), so this is
     trustworthy whenever present.
  2. `X-Forwarded-For` — ONLY the first (left-most, i.e. original client)
     hop, and ONLY when the immediate TCP peer (`request.client.host`) is
     itself in the configured trusted-proxy CIDR list (env
     `TRUSTED_PROXY_CIDRS`, comma-separated, defaults to Cloudflare's
     published IPv4/IPv6 ranges below). If the peer isn't a trusted
     proxy, X-Forwarded-For is attacker-controlled request data and using
     it would let anyone spoof their rate-limit key — so it's ignored
     and we fall through to the raw socket address instead.
  3. `request.client.host` — the raw socket peer address (slowapi's
     `get_remote_address`) as the final fallback.
"""
import ipaddress
import os
from typing import List, Optional

from fastapi import Request
from slowapi import Limiter
from slowapi.util import get_remote_address

# Cloudflare's published IP ranges (https://www.cloudflare.com/ips/) as of
# this writing. Override/extend via the TRUSTED_PROXY_CIDRS env var
# (comma-separated CIDRs) — e.g. to add an internal load balancer's range
# in front of Cloudflare, or to replace this list entirely if the
# deployment changes CDN/proxy provider.
_DEFAULT_TRUSTED_PROXY_CIDRS = [
    "173.245.48.0/20", "103.21.244.0/22", "103.22.200.0/22", "103.31.4.0/22",
    "141.101.64.0/18", "108.162.192.0/18", "190.93.240.0/20", "188.114.96.0/20",
    "197.234.240.0/22", "198.41.128.0/17", "162.158.0.0/15", "104.16.0.0/13",
    "104.24.0.0/14", "172.64.0.0/13", "131.0.72.0/22",
    "2400:cb00::/32", "2606:4700::/32", "2803:f800::/32", "2405:b500::/32",
    "2405:8100::/32", "2a06:98c0::/29", "2c0f:f248::/32",
]


def _load_trusted_proxy_networks() -> List:
    raw = os.getenv("TRUSTED_PROXY_CIDRS", "")
    cidrs = [c.strip() for c in raw.split(",") if c.strip()] or _DEFAULT_TRUSTED_PROXY_CIDRS
    networks = []
    for cidr in cidrs:
        try:
            networks.append(ipaddress.ip_network(cidr, strict=False))
        except ValueError:
            continue  # malformed entry in env — ignore rather than crash startup
    return networks


# Read once at import time (mirrors settings, which are also read once at
# import) — a running process picks up a changed TRUSTED_PROXY_CIDRS only
# on restart, same as every other env-backed setting here.
_TRUSTED_PROXY_NETWORKS = _load_trusted_proxy_networks()


def _is_trusted_proxy(peer_ip: Optional[str]) -> bool:
    if not peer_ip:
        return False
    try:
        addr = ipaddress.ip_address(peer_ip)
    except ValueError:
        return False
    return any(addr in net for net in _TRUSTED_PROXY_NETWORKS)


def get_client_ip(request: Request) -> str:
    """Best-effort real client IP, in the precedence documented above."""
    cf_ip = request.headers.get("CF-Connecting-IP")
    if cf_ip:
        return cf_ip.strip()

    peer_ip = request.client.host if request.client else None
    if _is_trusted_proxy(peer_ip):
        xff = request.headers.get("X-Forwarded-For")
        if xff:
            first_hop = xff.split(",")[0].strip()
            if first_hop:
                return first_hop

    return get_remote_address(request)


# The single shared Limiter — import this everywhere instead of building
# a new Limiter(...) per module.
limiter = Limiter(key_func=get_client_ip)
