"""Send one signed synthetic Meta WhatsApp inbound webhook.

The dashboard sample in ``docs/meta/webhooks/`` wraps the Cloud API ``value``
object. The gateway reads ``entry[].changes[].value``, so this script lifts
that sample into a WhatsApp webhook envelope, stamps a fresh message id and
text, and signs the exact bytes it posts.

Targets:
  direct  http://127.0.0.1:8000/webhooks/meta/whatsapp
          Production does not publish that port. Pass ``--url`` with the
          gateway container address when running on dedicated-hel1.
  public  https://api.omnimsg.io/webhooks/meta/whatsapp
          The webhook is on the API host, not https://omnimsg.io.

Usage:
  META_APP_SECRET=... python tests/send_synthetic_webhook.py --target public
  python tests/send_synthetic_webhook.py --target direct --url http://10.0.0.5:8000/webhooks/meta/whatsapp
"""

from __future__ import annotations

import argparse
import getpass
import hashlib
import hmac
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

import httpx

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SAMPLE = (
    REPO_ROOT / "docs" / "meta" / "webhooks" / "messages.incoming_text.sample.json"
)
WEBHOOK_PATH = "/webhooks/meta/whatsapp"
DEFAULT_PHONE_NUMBER_ID = "1283232261535702"
TARGETS = {
    "direct": f"http://127.0.0.1:8000{WEBHOOK_PATH}",
    "public": f"https://api.omnimsg.io{WEBHOOK_PATH}",
}


def _load_value(path: Path) -> dict[str, Any]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"{path} must be a JSON object")
    sample = raw.get("sample")
    if isinstance(sample, dict) and isinstance(sample.get("value"), dict):
        return sample["value"]
    if isinstance(raw.get("value"), dict):
        return raw["value"]
    raise ValueError(f"{path} has no sample.value")


def build_payload(
    *,
    sample_path: Path,
    phone_number_id: str,
    text: str,
    timestamp: str,
    message_id: str,
) -> dict[str, Any]:
    value = _load_value(sample_path)
    metadata = value.get("metadata")
    if not isinstance(metadata, dict):
        raise ValueError("sample value has no metadata object")
    metadata["phone_number_id"] = phone_number_id

    messages = value.get("messages")
    if not isinstance(messages, list) or not messages or not isinstance(messages[0], dict):
        raise ValueError("sample value has no messages[0]")
    message = messages[0]
    message["id"] = message_id
    message["timestamp"] = timestamp
    message["type"] = "text"
    message["text"] = {"body": text}

    return {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "synthetic",
                "changes": [
                    {
                        "field": "messages",
                        "value": value,
                    }
                ],
            }
        ],
    }


def sign_body(secret: str, body: bytes) -> str:
    """Match gateway ``verify_meta_signature``: HMAC-SHA256 over the raw body."""
    digest = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


def _secret_from_env_or_prompt() -> str:
    secret = os.environ.get("META_APP_SECRET", "").strip()
    if secret:
        return secret
    secret = getpass.getpass("META_APP_SECRET: ").strip()
    if not secret:
        raise SystemExit("META_APP_SECRET is required")
    return secret


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--target",
        choices=sorted(TARGETS),
        default="public",
        help="direct = localhost:8000 gateway; public = https://api.omnimsg.io",
    )
    parser.add_argument(
        "--url",
        default="",
        help="Override the full webhook URL (wins over --target)",
    )
    parser.add_argument(
        "--sample",
        type=Path,
        default=DEFAULT_SAMPLE,
        help="Dashboard sample JSON (default: messages.incoming_text.sample.json)",
    )
    parser.add_argument("--phone-number-id", default=DEFAULT_PHONE_NUMBER_ID)
    parser.add_argument(
        "--text",
        default="",
        help="Message body. Default includes the current UTC time.",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=20.0,
        help="HTTP timeout in seconds",
    )
    args = parser.parse_args(argv)

    url = args.url.strip() or TARGETS[args.target]
    now = int(time.time())
    text = args.text.strip() or f"synthetic inbound {now}"
    message_id = f"wamid.synthetic.{now}"
    payload = build_payload(
        sample_path=args.sample,
        phone_number_id=args.phone_number_id.strip(),
        text=text,
        timestamp=str(now),
        message_id=message_id,
    )
    body = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    signature = sign_body(_secret_from_env_or_prompt(), body)

    print(f"POST {url}")
    print(f"phone_number_id={args.phone_number_id.strip()} message_id={message_id}")
    print(f"text={text}")

    response = httpx.post(
        url,
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-Hub-Signature-256": signature,
        },
        timeout=args.timeout,
    )
    print(f"HTTP {response.status_code}")
    print(response.text)
    return 0 if response.is_success else 1


if __name__ == "__main__":
    sys.exit(main())
