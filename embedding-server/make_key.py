"""Create a new API key and add it to .env (API_KEYS is a comma-separated list)."""

import secrets
from pathlib import Path

env = Path(__file__).with_name(".env")
key = "egk_" + secrets.token_urlsafe(24)
lines = env.read_text().splitlines() if env.exists() else []
for i, line in enumerate(lines):
    if line.startswith("API_KEYS="):
        existing = line.split("=", 1)[1].strip()
        lines[i] = f"API_KEYS={existing},{key}" if existing else f"API_KEYS={key}"
        break
else:
    lines.append(f"API_KEYS={key}")
env.write_text("\n".join(lines) + "\n")
env.chmod(0o600)
print(f"Added a new key to {env}. Restart the server to pick it up.")
