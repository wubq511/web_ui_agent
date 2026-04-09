import base64
import json
import re
import secrets
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from security_utils import mask_string

try:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
except ImportError:
    AESGCM = None


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", value.strip().lower()).strip("-")
    return slug or "provider"


class LocalSecretCipher:
    def __init__(self, key_file: Path):
        self.key_file = key_file
        self.key_file.parent.mkdir(parents=True, exist_ok=True)
        self.key = self._load_or_create_key()

    def _load_or_create_key(self) -> bytes:
        if self.key_file.exists():
            return base64.b64decode(self.key_file.read_text(encoding="utf-8"))

        if AESGCM is not None:
            assert AESGCM is not None
            key = AESGCM.generate_key(bit_length=256)
        else:
            key = secrets.token_bytes(32)
        self.key_file.write_text(
            base64.b64encode(key).decode("utf-8"), encoding="utf-8"
        )
        return key

    def encrypt(self, plaintext: str) -> str:
        if not plaintext:
            return ""

        raw = plaintext.encode("utf-8")
        if AESGCM is not None:
            assert AESGCM is not None
            nonce = secrets.token_bytes(12)
            ciphertext = AESGCM(self.key).encrypt(nonce, raw, None)
            payload = nonce + ciphertext
        else:
            payload = bytes(b ^ self.key[i % len(self.key)] for i, b in enumerate(raw))

        return base64.b64encode(payload).decode("utf-8")

    def decrypt(self, ciphertext_b64: str) -> str:
        if not ciphertext_b64:
            return ""

        payload = base64.b64decode(ciphertext_b64)
        if AESGCM is not None:
            assert AESGCM is not None
            nonce = payload[:12]
            ciphertext = payload[12:]
            plaintext = AESGCM(self.key).decrypt(nonce, ciphertext, None)
        else:
            plaintext = bytes(
                b ^ self.key[i % len(self.key)] for i, b in enumerate(payload)
            )

        return plaintext.decode("utf-8")


class LLMConfigStore:
    def __init__(self, data_dir: Path | str = "credential_data"):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.config_file = self.data_dir / "llm_provider_configs.json"
        self.key_file = self.data_dir / "llm_provider.key"
        self.cipher = LocalSecretCipher(self.key_file)
        self._configs: Dict[str, Dict[str, Any]] = {}
        self._load()

    def _load(self) -> None:
        if not self.config_file.exists():
            self._configs = {}
            return

        raw = json.loads(self.config_file.read_text(encoding="utf-8"))
        configs = raw.get("configs", []) if isinstance(raw, dict) else []
        self._configs = {item["id"]: item for item in configs}

    def _save(self) -> None:
        payload = {
            "updated_at": datetime.now().isoformat(),
            "configs": list(self._configs.values()),
        }
        self.config_file.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def _serialize(
        self, config: Dict[str, Any], include_secret: bool = False
    ) -> Dict[str, Any]:
        result = {
            "id": config["id"],
            "display_name": config["display_name"],
            "provider": config.get("provider", "openai-compatible"),
            "model_name": config["model_name"],
            "base_url": config["base_url"],
            "description": config.get("description", ""),
            "max_tokens": config.get("max_tokens", 8192),
            "supports_vision": config.get("supports_vision", False),
            "enabled": config.get("enabled", True),
            "created_at": config.get("created_at", ""),
            "updated_at": config.get("updated_at", ""),
        }
        if include_secret:
            result["api_key"] = self.cipher.decrypt(config.get("api_key_encrypted", ""))
        else:
            result["api_key_masked"] = mask_string(
                self.cipher.decrypt(config.get("api_key_encrypted", "")), 3, 2
            )
        return result

    def create_config(
        self,
        display_name: str,
        provider: str,
        model_name: str,
        base_url: str,
        api_key: str,
        description: str = "",
        max_tokens: int = 8192,
        supports_vision: bool = False,
        enabled: bool = True,
    ) -> Dict[str, Any]:
        config_id = f"custom-{_slugify(display_name)}-{uuid.uuid4().hex[:8]}"
        timestamp = datetime.now().isoformat()
        config = {
            "id": config_id,
            "display_name": display_name.strip(),
            "provider": provider.strip() or "openai-compatible",
            "model_name": model_name.strip(),
            "base_url": base_url.strip().rstrip("/"),
            "api_key_encrypted": self.cipher.encrypt(api_key.strip()),
            "description": description.strip(),
            "max_tokens": int(max_tokens),
            "supports_vision": bool(supports_vision),
            "enabled": bool(enabled),
            "created_at": timestamp,
            "updated_at": timestamp,
        }
        self._configs[config_id] = config
        self._save()
        return self._serialize(config)

    def update_config(self, config_id: str, **changes: Any) -> Dict[str, Any]:
        if config_id not in self._configs:
            raise KeyError(f"Unknown config id: {config_id}")

        config = self._configs[config_id]
        for field in [
            "display_name",
            "provider",
            "model_name",
            "base_url",
            "description",
        ]:
            if field in changes and changes[field] is not None:
                value = str(changes[field]).strip()
                config[field] = value.rstrip("/") if field == "base_url" else value

        for field in ["max_tokens", "supports_vision", "enabled"]:
            if field in changes and changes[field] is not None:
                config[field] = changes[field]

        if "api_key" in changes and changes["api_key"]:
            config["api_key_encrypted"] = self.cipher.encrypt(
                str(changes["api_key"]).strip()
            )

        config["updated_at"] = datetime.now().isoformat()
        self._save()
        return self._serialize(config)

    def delete_config(self, config_id: str) -> bool:
        if config_id not in self._configs:
            return False
        del self._configs[config_id]
        self._save()
        return True

    def list_configs(self, include_secrets: bool = False) -> List[Dict[str, Any]]:
        return [
            self._serialize(config, include_secret=include_secrets)
            for config in self._configs.values()
        ]

    def get_config(
        self, config_id: str, include_secret: bool = False
    ) -> Optional[Dict[str, Any]]:
        config = self._configs.get(config_id)
        if not config:
            return None
        return self._serialize(config, include_secret=include_secret)

    def get_available_models(
        self, include_secrets: bool = False
    ) -> Dict[str, Dict[str, Any]]:
        merged: Dict[str, Dict[str, Any]] = {}
        for config_id, config in self._configs.items():
            if not config.get("enabled", True):
                continue

            serialized = self._serialize(config, include_secret=include_secrets)
            merged[config_id] = {
                "name": serialized["display_name"],
                "description": serialized["description"]
                or f"{serialized['provider']} 自定义配置",
                "priority": 100,
                "tags": ["custom", serialized["provider"]],
                "max_tokens": serialized["max_tokens"],
                "supports_vision": serialized["supports_vision"],
                "supports_auto_switch": False,
                "runtime_model": serialized["model_name"],
                "api_base": serialized["base_url"],
                "source": "custom",
                "provider": serialized["provider"],
            }
            if include_secrets:
                merged[config_id]["api_key"] = serialized["api_key"]

        return merged

    def get_default_model_id(self) -> Optional[str]:
        for config_id, config in self._configs.items():
            if config.get("enabled", True):
                return config_id
        return None


_store_instance: Optional[LLMConfigStore] = None


def get_llm_config_store() -> LLMConfigStore:
    global _store_instance
    if _store_instance is None:
        _store_instance = LLMConfigStore()
    return _store_instance


def get_available_model_catalog(
    include_secrets: bool = False,
) -> Dict[str, Dict[str, Any]]:
    return get_llm_config_store().get_available_models(include_secrets=include_secrets)


def get_model_config(
    model_id: str, include_secret: bool = False
) -> Optional[Dict[str, Any]]:
    catalog = get_available_model_catalog(include_secrets=include_secret)
    return catalog.get(model_id)


def get_default_model_id() -> Optional[str]:
    return get_llm_config_store().get_default_model_id()
