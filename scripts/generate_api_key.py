"""Generate API key and its SHA-256 hash for use in API_KEYS environment variable."""
from __future__ import annotations

import argparse
import hashlib
import secrets
import sys


def generate_api_key(name: str, role: str) -> tuple[str, str]:
    key = secrets.token_urlsafe(32)
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
    return key, digest


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate an API key for the Extreme Weather AI API")
    parser.add_argument("--name", required=True, help="Name/label for this key (e.g. 'admin', 'frontend')")
    parser.add_argument("--role", required=True, choices=["viewer", "analyst", "admin"], help="Role to assign")
    args = parser.parse_args()

    key, digest = generate_api_key(args.name, args.role)

    print(f"Name:  {args.name}")
    print(f"Role:  {args.role}")
    print(f"Key:   {key}")
    print(f"Hash:  {digest}")
    print()
    print(f"API_KEYS entry: {args.name}:{args.role}:{digest}")
    print()
    print("Add to your .env or environment:")
    print(f'  API_KEYS="{args.name}:{args.role}:{digest}"')


if __name__ == "__main__":
    main()
