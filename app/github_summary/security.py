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
SENSITIVE_SUFFIXES = {".pem", ".key", ".p12", ".pfx", ".jks", ".keystore"}
_SECRET_PATTERNS = [
    re.compile(r"gh[pousr]_[A-Za-z0-9_]{20,}"),
    re.compile(r"github_pat_[A-Za-z0-9_]{20,}"),
    re.compile(r"sk-[A-Za-z0-9_-]{20,}"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"(?i)authorization\s*:\s*(?:bearer|basic)\s+[^\s]+"),
    re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]{12,}"),
    re.compile(
        r"(?i)\b(?:postgres(?:ql)?|mysql|mariadb|mongodb(?:\+srv)?)://"
        r"[^:/\s]+:[^@/\s]+@[^\s]+"
    ),
    re.compile(
        r"(?i)(?:api[_-]?key|access[_-]?token|token|password|secret)"
        r"\s*[:=]\s*['\"][^'\"]{6,}['\"]"
    ),
    re.compile(
        r"(?i)(?:api[_-]?key|access[_-]?token|password|secret)"
        r"\s*[:=]\s*[^\s,;]{6,}"
    ),
    re.compile(
        r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----[\s\S]*?"
        r"-----END (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"
    ),
]


def is_sensitive_path(relative_path: str) -> bool:
    normalized = relative_path.replace("\\", "/").lower()
    name = normalized.rsplit("/", 1)[-1]
    if name in {".env.example", ".env.sample", ".env.template"}:
        return False
    if name in SENSITIVE_FILE_NAMES or name.startswith(".env."):
        return True
    return any(name.endswith(suffix) for suffix in SENSITIVE_SUFFIXES)


def redact_secrets(content: str) -> str:
    sanitized = content
    for pattern in _SECRET_PATTERNS:
        sanitized = pattern.sub("[REDACTED_SECRET]", sanitized)
    return sanitized
