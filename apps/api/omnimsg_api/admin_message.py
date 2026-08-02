"""SQLAdmin Message view (C2.4) — observability only, strictly read-only."""

from __future__ import annotations

import json
import re
from typing import Any

from omnimsg_common.db.models import Message
from sqladmin import ModelView
from sqladmin.filters import AllUniqueStringValuesFilter, OperationColumnFilter
from starlette.requests import Request

_SENSITIVE_KEY = re.compile(
    r"(token|secret|password|authorization|access[_-]?token|api[_-]?key|bearer)",
    re.IGNORECASE,
)
_PHONE_LIKE = re.compile(r"^\+?\d[\d\s\-()]{6,}\d$")
_EMAIL_LIKE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def mask_recipient(value: str | None) -> str:
    """Mask phone / email for list and detail display."""
    if not value:
        return "—"
    text = str(value).strip()
    if _EMAIL_LIKE.match(text):
        local, _, domain = text.partition("@")
        keep = local[:1] if local else ""
        return f"{keep}•••@{domain}"
    digits = re.sub(r"\D", "", text)
    if len(digits) >= 8:
        return f"•••{digits[-4:]}"
    if len(text) <= 4:
        return "••••"
    return f"{text[:1]}•••{text[-1:]}"


def redact_payload(value: Any) -> Any:
    """Recursively redact tokens; mask phone/email leaf strings."""
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for key, item in value.items():
            if _SENSITIVE_KEY.search(str(key)):
                out[key] = "[redacted]"
            else:
                out[key] = redact_payload(item)
        return out
    if isinstance(value, list):
        return [redact_payload(item) for item in value]
    if isinstance(value, str):
        if _EMAIL_LIKE.match(value) or _PHONE_LIKE.match(value):
            return mask_recipient(value)
        if value.startswith("omni_") and len(value) > 20:
            return "[redacted]"
        if value.startswith("EAA") and len(value) > 20:
            return "[redacted]"
        return value
    return value


def _fmt_recipient(obj: Any, _prop: Any) -> str:
    return mask_recipient(getattr(obj, "to", None))


def _fmt_from(obj: Any, _prop: Any) -> str:
    return mask_recipient(getattr(obj, "from_address", None))


def _fmt_payload(obj: Any, _prop: Any) -> str:
    sections: list[str] = []
    err = _payload_error(obj)
    if err != "—":
        sections.append(f"Error:\n{err}")
    resp = _provider_response(obj)
    if resp != "—":
        sections.append(f"Provider response:\n{resp}")
    raw = getattr(obj, "payload", None) or {}
    try:
        body = json.dumps(
            redact_payload(raw), ensure_ascii=False, indent=2, default=str
        )
    except (TypeError, ValueError):
        body = "[unreadable payload]"
    sections.append(f"Payload:\n{body}")
    return "\n\n".join(sections)


def _payload_error(obj: Any) -> str:
    payload = getattr(obj, "payload", None) or {}
    if not isinstance(payload, dict):
        return "—"
    for key in ("error", "last_error", "provider_error", "error_message"):
        if key in payload and payload[key]:
            return str(payload[key])[:500]
    return "—"


def _provider_response(obj: Any) -> str:
    payload = getattr(obj, "payload", None) or {}
    if not isinstance(payload, dict):
        return "—"
    for key in ("provider_response", "graph_response", "provider_result"):
        if key in payload and payload[key] is not None:
            try:
                return json.dumps(
                    redact_payload(payload[key]),
                    ensure_ascii=False,
                    indent=2,
                    default=str,
                )
            except (TypeError, ValueError):
                return str(payload[key])[:500]
    # Common outbound echo fields.
    bits = {
        k: payload[k]
        for k in ("provider_message_id", "wamid", "meta")
        if k in payload
    }
    if not bits:
        return "—"
    try:
        return json.dumps(redact_payload(bits), ensure_ascii=False, indent=2, default=str)
    except (TypeError, ValueError):
        return "—"


class MessageAdmin(ModelView, model=Message):
    """Ops observability for messages — no mutations (ADR-0022 C2.4)."""

    name = "Message"
    name_plural = "Messages"
    icon = "fa-solid fa-envelope"
    can_create = False
    can_edit = False
    can_delete = False
    can_export = True
    page_size = 50
    column_default_sort = [(Message.created_at, True)]

    column_list = [
        Message.created_at,
        Message.tenant_id,
        Message.channel,
        Message.direction,
        Message.status,
        Message.to,
        Message.correlation_id,
    ]
    column_labels = {
        Message.channel: "Channel / provider",
        Message.to: "Recipient",
        Message.correlation_id: "Correlation ID",
    }
    column_details_list = [
        Message.id,
        Message.created_at,
        Message.updated_at,
        Message.tenant_id,
        Message.channel,
        Message.direction,
        Message.status,
        Message.type,
        Message.to,
        Message.from_address,
        Message.correlation_id,
        Message.idempotency_key,
        Message.conversation_id,
        Message.provider_message_id,
        Message.payload,
    ]
    column_formatters = {
        Message.to: _fmt_recipient,
    }
    column_formatters_detail = {
        Message.to: _fmt_recipient,
        Message.from_address: _fmt_from,
        Message.payload: _fmt_payload,
    }
    column_searchable_list = [
        Message.id,
        Message.tenant_id,
        Message.correlation_id,
        Message.provider_message_id,
        Message.status,
    ]
    column_sortable_list = [
        Message.created_at,
        Message.status,
        Message.tenant_id,
        Message.channel,
        Message.direction,
    ]
    column_filters = [
        AllUniqueStringValuesFilter(Message.tenant_id, title="Tenant"),
        AllUniqueStringValuesFilter(Message.status, title="Status"),
        AllUniqueStringValuesFilter(Message.channel, title="Channel / provider"),
        AllUniqueStringValuesFilter(Message.direction, title="Direction"),
        OperationColumnFilter(Message.created_at, title="Created at"),
    ]

    # Synthetic detail helpers via column_formatters are enough for payload;
    # error / provider response are derived inside redacted payload JSON.

    def is_accessible(self, request: Request) -> bool:
        return bool(request.session.get("admin_user"))

    def is_visible(self, request: Request) -> bool:
        return self.is_accessible(request)
