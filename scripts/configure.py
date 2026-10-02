"""Create first-run configuration, without overwriting an existing installation."""

from pathlib import Path
import secrets

root = Path(__file__).resolve().parents[1]
target = root / ".env"
if target.exists():
    raise SystemExit(
        ".env already exists. Edit it directly; existing configuration was not changed."
    )
password = secrets.token_urlsafe(20)
text = (
    (root / ".env.example")
    .read_text(encoding="utf-8")
    .replace("CHANGE_TO_A_RANDOM_PASSWORD_OF_AT_LEAST_12_CHARACTERS", password)
)
target.write_text(text, encoding="utf-8")
try:
    target.chmod(0o600)
except OSError:
    pass
print("Configuration created. Keep the following first-login password private.")
print("Email: admin@agency.local")
print("Password:", password)
print("Open http://localhost:8000 after starting the application.")
