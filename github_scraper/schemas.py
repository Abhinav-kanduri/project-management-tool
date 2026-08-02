import re


SENSITIVE_FILE_NAMES = {
    ".env",
    ".env.local",
    ".env.production",
    ".env.development",
    "credentials.json",
    "service-account.json",
    "secrets.json",
    "secrets.yaml",
    "secrets.yml",
    "terraform.tfstate",
    "terraform.tfstate.backup",
    "id_rsa",
    "id_dsa",
    "id_ecdsa",
    "id_ed25519",
}

SENSITIVE_SUFFIXES = {
    ".pem",
    ".key",
    ".p12",
    ".pfx",
    ".jks",
    ".keystore",
}

_SECRET_PATTERNS = [
    re.compile(r"gh[pousr]_[A-Za-z0-9_]{20,}"),
    re.compile(r"github_pat_[A-Za-z0-9_]{20,}"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"(?i)(api[_-]?key|token|password|secret)\s*[:=]\s*['\"][^'\"]{6,}['\"]"),
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----[\s\S]*?-----END (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
]


def is_sensitive_path(relative_path: str) -> bool:
    normalized = relative_path.replace("\\", "/").lower()
    name = normalized.rsplit("/", 1)[-1]
    safe_env_templates = {".env.example", ".env.sample", ".env.template"}
    if name in safe_env_templates:
        return False
    if name in SENSITIVE_FILE_NAMES:
        return True
    if name.startswith(".env."):
        return True
    return any(name.endswith(suffix) for suffix in SENSITIVE_SUFFIXES)


def redact_secrets(content: str) -> str:
    sanitized = content
    for pattern in _SECRET_PATTERNS:
        sanitized = pattern.sub("[REDACTED_SECRET]", sanitized)
    return sanitized
