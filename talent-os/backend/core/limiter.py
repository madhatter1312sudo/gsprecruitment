"""Talent OS — Shared rate limiter instance for SlowAPI.
Import this in both main.py and any router that needs @limiter.limit() decorators.
"""
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)