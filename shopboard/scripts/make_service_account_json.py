"""Convert the legacy streamlit secrets.toml [gcp_service_account] section
into a standard Google service-account JSON key file (gitignored)."""
import json
import sys
import tomllib
from pathlib import Path

root = Path(__file__).resolve().parents[2]
src = root / "shop_dashboard_Streamlit_Sample" / ".streamlit" / "secrets.toml"
dst = root / "shopboard" / "service_account.json"

with open(src, "rb") as f:
    sa = tomllib.load(f)["gcp_service_account"]

required = {"type", "project_id", "private_key", "client_email", "token_uri"}
missing = required - sa.keys()
if missing:
    sys.exit(f"missing keys in [gcp_service_account]: {missing}")

dst.write_text(json.dumps(sa, indent=2), encoding="utf-8")
print(f"wrote {dst} ({dst.stat().st_size} bytes) for {sa['client_email']}")
