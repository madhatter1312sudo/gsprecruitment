"""Quick test for auth system primitives."""
import sys
sys.path.insert(0, '/app')
from core.config import settings
from core.security import hash_password, verify_password, create_access_token, decode_token

print("Config OK:", settings.jwt_algorithm)
print("CORS origins:", settings.cors_origin_list)

# Test password hashing
h = hash_password("test1234!")
assert verify_password("test1234!", h)
print("Password hashing: OK")

# Test JWT
token = create_access_token({"sub": 1, "role": "admin"})
payload = decode_token(token)
assert payload["sub"] == 1
assert payload["role"] == "admin"
print("JWT: OK")

# Test with custom expiry
from datetime import timedelta
token2 = create_access_token({"sub": 2}, expires_delta=timedelta(hours=1))
assert decode_token(token2)["sub"] == 2
print("JWT custom expiry: OK")

print("All auth primitives verified successfully!")