import base64
import json
import logging
import os
from pathlib import Path
from typing import Any

logger = logging.getLogger("security_vault")

VAULT_PATH = Path(__file__).resolve().parent.parent / "memory" / "secrets.vault.json"
_VAULT_KEY = os.environ.get("JARVIS_VAULT_KEY", "")

# ── Encryption helpers (Fernet) ──────────────────────────────────────────

try:
    from cryptography.fernet import Fernet
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

    def _derive_key(passphrase: str, salt: bytes) -> bytes:
        kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt,
                         iterations=600_000)
        return base64.urlsafe_b64encode(kdf.derive(passphrase.encode("utf-8")))

    _HAVE_FERNET = True
except ImportError:
    _HAVE_FERNET = False


def _encrypt(plaintext: str) -> str:
    """Encrypt plaintext JSON string. Returns base64 ciphertext."""
    if not _HAVE_FERNET or not _VAULT_KEY:
        return plaintext  # fallback to plaintext
    salt = os.urandom(16)
    key = _derive_key(_VAULT_KEY, salt)
    cipher = Fernet(key)
    token = cipher.encrypt(plaintext.encode("utf-8"))
    # Prepend salt (hex) so we can derive the same key on decrypt
    return salt.hex() + ":" + token.decode("utf-8")


def _decrypt(ciphertext: str) -> str:
    """Decrypt string that was produced by _encrypt."""
    if not _HAVE_FERNET or not _VAULT_KEY:
        return ciphertext
    if ":" not in ciphertext:
        logger.warning("Vault data missing salt header — treating as plaintext")
        return ciphertext
    try:
        salt_hex, token = ciphertext.split(":", 1)
        salt = bytes.fromhex(salt_hex)
        key = _derive_key(_VAULT_KEY, salt)
        cipher = Fernet(key)
        return cipher.decrypt(token.encode("utf-8")).decode("utf-8")
    except Exception as e:
        logger.error("Vault decryption failed: %s", e)
        return ""


# ── Vault I/O ────────────────────────────────────────────────────────────

def _get_vault() -> dict:
    if not VAULT_PATH.exists():
        return {}
    try:
        raw = VAULT_PATH.read_text(encoding="utf-8").strip()
        if not raw:
            return {}
        decrypted = _decrypt(raw)
        return json.loads(decrypted) if decrypted else {}
    except Exception:
        return {}


def _save_vault(data: dict):
    VAULT_PATH.parent.mkdir(parents=True, exist_ok=True)
    plaintext = json.dumps(data, indent=2, ensure_ascii=False)
    encrypted = _encrypt(plaintext)
    VAULT_PATH.write_text(encrypted, encoding="utf-8")


def store_secret(key: str, value: str) -> str:
    vault = _get_vault()
    vault[key] = value
    _save_vault(vault)
    logger.info("Secret stored: %s", key)
    return f"Secret '{key}' stored."


def get_secret(key: str) -> str:
    vault = _get_vault()
    return vault.get(key, "")


def list_secrets() -> list[str]:
    vault = _get_vault()
    return list(vault.keys())


def delete_secret(key: str) -> str:
    vault = _get_vault()
    if key in vault:
        del vault[key]
        _save_vault(vault)
        return f"Secret '{key}' deleted."
    return f"Secret '{key}' not found."


# ── HashiCorp Vault integration ────────────────────────────────────────

class HashiVaultClient:
    def __init__(self, url: str = "", token: str = ""):
        self.url = url.rstrip("/") or os.environ.get("VAULT_ADDR", "")
        self.token = token or os.environ.get("VAULT_TOKEN", "")
        self._client = None

    def _connect(self):
        if self._client:
            return self._client
        try:
            import hvac
        except ImportError:
            raise ImportError("hvac not installed — pip install hvac")

        if not self.url or not self.token:
            raise ValueError("VAULT_ADDR and VAULT_TOKEN must be set")

        self._client = hvac.Client(url=self.url, token=self.token)
        if not self._client.is_authenticated():
            raise ValueError("Vault authentication failed")
        return self._client

    def read_secret(self, path: str, mount_point: str = "secret") -> dict[str, Any]:
        client = self._connect()
        try:
            resp = client.secrets.kv.v2.read_secret_version(
                path=path, mount_point=mount_point,
            )
            return resp.get("data", {}).get("data", {})
        except Exception as e:
            logger.warning("Vault read error: %s", e)
            return {}

    def write_secret(self, path: str, data: dict, mount_point: str = "secret") -> bool:
        client = self._connect()
        try:
            client.secrets.kv.v2.create_or_update_secret(
                path=path, secret=data, mount_point=mount_point,
            )
            return True
        except Exception as e:
            logger.warning("Vault write error: %s", e)
            return False

    def list_secrets(self, path: str = "", mount_point: str = "secret") -> list[str]:
        client = self._connect()
        try:
            resp = client.secrets.kv.v2.list_secrets(
                path=path, mount_point=mount_point,
            )
            return resp.get("data", {}).get("keys", [])
        except Exception:
            return []

    def delete_secret(self, path: str, mount_point: str = "secret") -> bool:
        client = self._connect()
        try:
            client.secrets.kv.v2.delete_metadata_and_all_versions(
                path=path, mount_point=mount_point,
            )
            return True
        except Exception:
            return False
