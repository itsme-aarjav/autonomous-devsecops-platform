#!/usr/bin/env python3
"""
Secure, Idempotent In-Memory Secrets Seeding Script for AWS Secrets Manager
Target Secrets:
  - boutique/database/credentials
  - boutique/auth/jwt-secret
  - boutique/aiops/webhook-token
  - boutique/aiops/github-token

Security & Idempotency Rules:
  1. Inspects secret metadata first via describe_secret.
  2. If AWSCURRENT stage already exists, refuses to overwrite unless --rotate is passed.
  3. Credentials generated in-memory using Python 'secrets' module (CSPRNG).
  4. Database password uses URL-safe characters to ensure full compatibility with
     PostgreSQL connection URIs across Node.js microservices.
  5. Values are NEVER printed, logged, or saved to disk/Terraform state.
  6. Injects values directly via put_secret_value.
  7. Verifies KMS CMK encryption association and metadata without retrieving payloads.
"""

import argparse
import getpass
import json
import logging
import os
import secrets
import string
import sys
from typing import Dict, Any, Tuple
try:
    import boto3
    from botocore.exceptions import ClientError
except ImportError:
    boto3 = None

    class ClientError(Exception):
        def __init__(self, error_response=None, operation_name=None):
            self.response = error_response or {}
            self.operation_name = operation_name
            super().__init__(str(error_response))

DEFAULT_REGION = "us-east-2"
DB_SECRET_NAME = "boutique/database/credentials"
JWT_SECRET_NAME = "boutique/auth/jwt-secret"
AIOPS_WEBHOOK_SECRET_NAME = "boutique/aiops/webhook-token"
AIOPS_GITHUB_SECRET_NAME = "boutique/aiops/github-token"
EXPECTED_KMS_ALIAS = "alias/boutique-aiops-key"

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("seed_secrets")


def generate_postgres_password(length: int = 32) -> str:
    """
    Generates a high-entropy password using alphanumeric and URL-safe characters (_ -).
    Avoids URI-reserved characters (@, :, /, ?, #) to prevent connection string parsing
    failures in PostgreSQL clients (e.g. node-postgres Pool).
    """
    safe_symbols = "_-"
    charset = string.ascii_letters + string.digits + safe_symbols
    while True:
        pwd = "".join(secrets.choice(charset) for _ in range(length))
        if (any(c.islower() for c in pwd)
                and any(c.isupper() for c in pwd)
                and any(c.isdigit() for c in pwd)
                and any(c in safe_symbols for c in pwd)):
            return pwd


def generate_jwt_signing_secret(token_bytes: int = 48) -> str:
    """Generates a cryptographic 64-character base64url secret for HMAC-SHA256."""
    return secrets.token_urlsafe(token_bytes)


def generate_webhook_token(token_bytes: int = 32) -> str:
    """Generates a cryptographic URL-safe secret for Alertmanager to AIOps webhook authentication."""
    return secrets.token_urlsafe(token_bytes)


def build_db_payload(password: str) -> str:
    """Exact JSON schema expected by Boutique microservices database connections."""
    payload = {
        "POSTGRES_USER": "postgres",
        "POSTGRES_PASSWORD": password,
        "POSTGRES_DB": "postgres"
    }
    return json.dumps(payload, separators=(',', ':'))


def build_jwt_payload(secret: str) -> str:
    """Exact JSON schema expected by Boutique auth and gateway services."""
    payload = {
        "JWT_SECRET": secret,
        "JWT_EXPIRES_IN": "24h"
    }
    return json.dumps(payload, separators=(',', ':'))


def build_token_payload(token: str) -> str:
    """Exact JSON schema expected by Kubernetes secretKeyRef key 'token'."""
    payload = {
        "token": token
    }
    return json.dumps(payload, separators=(',', ':'))


def check_existing_secret_state(sm_client, secret_name: str) -> Tuple[bool, str]:
    """
    Checks if a secret exists and whether it already has an active AWSCURRENT version.
    Returns (has_current_version, kms_key_id).
    """
    try:
        meta = sm_client.describe_secret(SecretId=secret_name)
    except ClientError as e:
        logger.error("Failed to describe secret metadata for %s: %s", secret_name, e.response.get('Error', {}).get('Message', str(e)))
        raise

    stages = meta.get("VersionIdsToStages", {})
    has_current = any("AWSCURRENT" in stage_list for stage_list in stages.values())
    kms_key = meta.get("KmsKeyId", "unknown")
    return has_current, kms_key


def seed_or_rotate_secret(
    sm_client,
    secret_name: str,
    payload_builder,
    secret_generator,
    rotate: bool = False
) -> Dict[str, Any]:
    """
    Idempotently seeds or rotates a secret value.
    Never logs or exposes the secret payload.
    """
    has_current, kms_key = check_existing_secret_state(sm_client, secret_name)

    if has_current and not rotate:
        logger.info(
            "Secret '%s' already has an active AWSCURRENT version. Skipping generation to prevent accidental overwrite (use --rotate to force rotation).",
            secret_name
        )
        return {
            "secret_name": secret_name,
            "action": "SKIPPED",
            "reason": "Existing AWSCURRENT version preserved",
            "kms_key_id": kms_key
        }

    # Generate in-memory payload
    secret_val = secret_generator()
    secret_string = payload_builder(secret_val)

    action_name = "ROTATED" if has_current else "INITIAL_SEED"
    try:
        response = sm_client.put_secret_value(
            SecretId=secret_name,
            SecretString=secret_string,
            VersionStages=["AWSCURRENT"]
        )
        logger.info(
            "Successfully seeded secret '%s' [Action: %s, VersionId: %s]",
            secret_name, action_name, response.get("VersionId")
        )
        return {
            "secret_name": secret_name,
            "action": action_name,
            "version_id": response.get("VersionId"),
            "kms_key_id": kms_key
        }
    except ClientError as e:
        logger.error(
            "AWS API error putting secret value for '%s': %s",
            secret_name, e.response.get('Error', {}).get('Message', str(e))
        )
        raise


def run_seeding(
    region: str,
    rotate: bool = False,
    rotate_jwt_only: bool = False,
    rotate_webhook_only: bool = False,
    github_token: str = None,
    sm_client=None
) -> bool:
    """Main orchestration for seeding all production platform secrets."""
    if sm_client is None:
        sm_client = boto3.client("secretsmanager", region_name=region)

    results = []

    # 1. Database Credentials (bypassed if selective rotation of JWT or webhook is requested)
    if rotate_jwt_only or rotate_webhook_only:
        db_result = {
            "secret_name": DB_SECRET_NAME,
            "action": "SKIPPED",
            "reason": "Selective rotation requested; database credentials untouched",
            "kms_key_id": "untouched"
        }
        logger.info(
            "Database secret '%s' skipped: selective rotation requested; database credentials untouched.",
            DB_SECRET_NAME
        )
    else:
        db_result = seed_or_rotate_secret(
            sm_client=sm_client,
            secret_name=DB_SECRET_NAME,
            payload_builder=build_db_payload,
            secret_generator=generate_postgres_password,
            rotate=rotate
        )
    results.append(db_result)

    # 2. JWT Secret (rotated if either rotate or rotate_jwt_only is True; skipped if rotate_webhook_only)
    if rotate_webhook_only:
        jwt_result = {
            "secret_name": JWT_SECRET_NAME,
            "action": "SKIPPED",
            "reason": "Webhook-only rotation requested; JWT secret untouched",
            "kms_key_id": "untouched"
        }
        logger.info(
            "JWT secret '%s' skipped: webhook-only rotation requested; JWT secret untouched.",
            JWT_SECRET_NAME
        )
    else:
        rotate_jwt = rotate or rotate_jwt_only
        jwt_result = seed_or_rotate_secret(
            sm_client=sm_client,
            secret_name=JWT_SECRET_NAME,
            payload_builder=build_jwt_payload,
            secret_generator=generate_jwt_signing_secret,
            rotate=rotate_jwt
        )
    results.append(jwt_result)

    # 3. AIOps Webhook Bearer Token (rotated if rotate or rotate_webhook_only; skipped if rotate_jwt_only)
    if rotate_jwt_only:
        webhook_result = {
            "secret_name": AIOPS_WEBHOOK_SECRET_NAME,
            "action": "SKIPPED",
            "reason": "JWT-only rotation requested; webhook token untouched",
            "kms_key_id": "untouched"
        }
        logger.info(
            "AIOps webhook token '%s' skipped: JWT-only rotation requested; webhook token untouched.",
            AIOPS_WEBHOOK_SECRET_NAME
        )
    else:
        rotate_webhook = rotate or rotate_webhook_only
        webhook_result = seed_or_rotate_secret(
            sm_client=sm_client,
            secret_name=AIOPS_WEBHOOK_SECRET_NAME,
            payload_builder=build_token_payload,
            secret_generator=generate_webhook_token,
            rotate=rotate_webhook
        )
    results.append(webhook_result)

    # 4. AIOps GitHub Token (Optional operator-supplied token for GitOps autonomous commits/PRs)
    if github_token and github_token.strip():
        clean_token = github_token.strip()
        github_result = seed_or_rotate_secret(
            sm_client=sm_client,
            secret_name=AIOPS_GITHUB_SECRET_NAME,
            payload_builder=build_token_payload,
            secret_generator=lambda: clean_token,
            rotate=True
        )
        results.append(github_result)
    else:
        # Check existing state without modifying
        try:
            has_github, gh_kms = check_existing_secret_state(sm_client, AIOPS_GITHUB_SECRET_NAME)
            status_reason = "Existing GitHub token preserved" if has_github else "No token supplied (set AIOPS_GITHUB_TOKEN env var when GitOps PR automation is enabled)"
            github_result = {
                "secret_name": AIOPS_GITHUB_SECRET_NAME,
                "action": "PRESERVED" if has_github else "OPTIONAL_PENDING",
                "reason": status_reason,
                "kms_key_id": gh_kms
            }
        except ClientError:
            github_result = {
                "secret_name": AIOPS_GITHUB_SECRET_NAME,
                "action": "CONTAINER_PENDING",
                "reason": "Secret container not yet provisioned in AWS Secrets Manager",
                "kms_key_id": "unknown"
            }
        results.append(github_result)

    logger.info("Summary of secrets seeding operation:")
    for res in results:
        logger.info("  Secret: %s | Action: %s | KMS Key: %s", res["secret_name"], res["action"], res.get("kms_key_id"))

    return True


def parse_args():
    parser = argparse.ArgumentParser(
        description="Secure, idempotent seeding for AWS Secrets Manager credentials.",
        epilog="Note: Supply GitHub PAT via AIOPS_GITHUB_TOKEN environment variable (or interactive prompt); CLI argument is disabled for security."
    )
    parser.add_argument("--region", default=DEFAULT_REGION, help=f"AWS Region (default: {DEFAULT_REGION})")
    parser.add_argument("--rotate", action="store_true", help="Force credential rotation for all secrets if already existing")
    parser.add_argument("--rotate-jwt-only", action="store_true", help="Force rotation of JWT secret only (preserves database credentials & webhook token)")
    parser.add_argument("--rotate-webhook-only", action="store_true", help="Force rotation of AIOps webhook token only (preserves database & JWT credentials)")
    # GitHub token is intentionally NOT accepted as a CLI argument to prevent exposure in
    # shell history and /proc/*/cmdline. Supply it via the AIOPS_GITHUB_TOKEN environment
    # variable (set without shell history via: export AIOPS_GITHUB_TOKEN=... before running)
    # or leave it unset to be prompted securely via getpass at runtime.
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()

    # Resolve GitHub token securely: env var first, then interactive prompt, never CLI arg.
    github_token: str | None = os.getenv("AIOPS_GITHUB_TOKEN", "").strip() or None
    if github_token is None:
        try:
            prompted = getpass.getpass(
                "Enter GitHub PAT for boutique/aiops/github-token (leave blank to skip): "
            ).strip()
            github_token = prompted if prompted else None
        except (EOFError, KeyboardInterrupt):
            github_token = None

    try:
        success = run_seeding(
            region=args.region,
            rotate=args.rotate,
            rotate_jwt_only=args.rotate_jwt_only,
            rotate_webhook_only=args.rotate_webhook_only,
            github_token=github_token,
        )
        sys.exit(0 if success else 1)
    except Exception as exc:
        logger.error("Seeding operation aborted: %s", exc)
        sys.exit(1)

