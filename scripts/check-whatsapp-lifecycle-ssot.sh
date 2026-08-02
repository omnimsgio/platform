#!/usr/bin/env bash
# Fail if TenantWhatsappAccount.status is assigned outside the lifecycle module.
# ADR-0020: only transition()/bootstrap_ready() may mutate WhatsApp connection status.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT_DIR}"

python3 - <<'PY'
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(".")
ALLOW = {
    Path("packages/common/omnimsg_common/whatsapp_lifecycle.py"),
}
# Assignment only: ".status =" but not ".status ==" / "!="
ASSIGN = re.compile(r"""\b(row|account)\.status\s*=(?!=)""")
LITERAL_ASSIGN = re.compile(
    r"""\.status\s*=(?!=)\s*["'](READY|PHONE_PENDING|EMBEDDED_SIGNUP_STARTED|
    BUSINESS_CONNECTED|WEBHOOK_PENDING|HEALTH_CHECK_PENDING|ERROR|DISCONNECTED|
    active|pending|error)["']""",
    re.VERBOSE,
)

# Only scan modules that import TenantWhatsappAccount (avoids Message.status noise).
bad: list[str] = []
for path in list(ROOT.glob("apps/**/*.py")) + list(ROOT.glob("packages/**/*.py")) + list(
    ROOT.glob("scripts/**/*.py")
):
    rel = path.relative_to(ROOT)
    if rel in ALLOW:
        continue
    if "migrations" in rel.parts:
        continue
    text = path.read_text(encoding="utf-8")
    if "TenantWhatsappAccount" not in text and "whatsapp_lifecycle" not in text:
        continue
    for i, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        if ASSIGN.search(line) or LITERAL_ASSIGN.search(line):
            # Message row.status writes in worker are OK when file also has WA imports —
            # require lifecycle literals or account. prefix for WA, or row in ES module.
            if "Message" in text and "TenantWhatsappAccount" in text:
                if "account.status" in line or LITERAL_ASSIGN.search(line):
                    bad.append(f"{rel}:{i}:{stripped}")
                elif rel.as_posix().endswith("embedded_signup.py") and ASSIGN.search(line):
                    bad.append(f"{rel}:{i}:{stripped}")
                # worker Message.status assignments ignored
                continue
            bad.append(f"{rel}:{i}:{stripped}")

if bad:
    print(
        "Forbidden direct WhatsApp status writes outside whatsapp_lifecycle.py:",
        file=sys.stderr,
    )
    print("\n".join(bad), file=sys.stderr)
    sys.exit(1)
print("WhatsApp lifecycle SSOT check passed.")
PY
