"""Tolerant Meta WhatsApp referral extraction (CTWA / ad click).

Never raises for unknown or partial referral shapes; callers get skips + warnings.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

_QUERYABLE_KEYS = ("source", "source_id", "headline", "body", "media_type", "ctwa_clid")


@dataclass(frozen=True)
class ExtractedReferral:
    """One valid messages[].referral ready for persistence."""

    contact_external_id: str
    provider_message_id: str
    phone_number_id: str | None
    source: str | None
    source_id: str | None
    headline: str | None
    body: str | None
    media_type: str | None
    ctwa_clid: str | None
    raw_payload: dict[str, Any]


@dataclass
class ReferralExtractStats:
    """Counters from a single extract pass."""

    detected: int = 0
    skipped: int = 0
    referrals: list[ExtractedReferral] | None = None

    def __post_init__(self) -> None:
        if self.referrals is None:
            self.referrals = []


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        stripped = value.strip()
        return stripped or None
    try:
        text = str(value).strip()
    except Exception:  # noqa: BLE001 — never fail extract on coercion
        return None
    return text or None


def _warn_skip(
    *,
    tenant_id: str | None,
    provider_message_id: str | None,
    reason: str,
) -> None:
    logger.warning(
        "referral_skipped tenant_id=%s provider_message_id=%s reason=%s",
        tenant_id or "-",
        provider_message_id or "-",
        reason,
    )


def extract_referrals(
    payload: Any,
    *,
    tenant_id: str | None = None,
) -> ReferralExtractStats:
    """Walk Meta webhook JSON and collect referrals. Never raises."""
    stats = ReferralExtractStats()
    try:
        if not isinstance(payload, dict):
            return stats
        entries = payload.get("entry")
        if not isinstance(entries, list):
            return stats
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            changes = entry.get("changes")
            if not isinstance(changes, list):
                continue
            for change in changes:
                if not isinstance(change, dict):
                    continue
                value = change.get("value")
                if not isinstance(value, dict):
                    continue
                phone_number_id = _optional_str(
                    (value.get("metadata") or {}).get("phone_number_id")
                    if isinstance(value.get("metadata"), dict)
                    else None
                )
                messages = value.get("messages")
                if not isinstance(messages, list):
                    continue
                for message in messages:
                    _process_message(
                        message,
                        phone_number_id=phone_number_id,
                        tenant_id=tenant_id,
                        stats=stats,
                    )
    except Exception:  # noqa: BLE001 — parser never throws to caller
        logger.warning(
            "referral_skipped tenant_id=%s provider_message_id=%s reason=%s",
            tenant_id or "-",
            "-",
            "unexpected_extract_error",
            exc_info=True,
        )
        stats.skipped += 1
    return stats


def _process_message(
    message: Any,
    *,
    phone_number_id: str | None,
    tenant_id: str | None,
    stats: ReferralExtractStats,
) -> None:
    if not isinstance(message, dict):
        return
    if "referral" not in message:
        return

    stats.detected += 1
    provider_message_id = _optional_str(message.get("id"))
    contact = _optional_str(message.get("from"))
    referral = message.get("referral")

    if not isinstance(referral, dict):
        stats.skipped += 1
        _warn_skip(
            tenant_id=tenant_id,
            provider_message_id=provider_message_id,
            reason="referral_not_object",
        )
        return
    if not provider_message_id:
        stats.skipped += 1
        _warn_skip(
            tenant_id=tenant_id,
            provider_message_id=None,
            reason="missing_provider_message_id",
        )
        return
    if not contact:
        stats.skipped += 1
        _warn_skip(
            tenant_id=tenant_id,
            provider_message_id=provider_message_id,
            reason="missing_contact_external_id",
        )
        return

    fields = {key: _optional_str(referral.get(key)) for key in _QUERYABLE_KEYS}
    assert stats.referrals is not None
    stats.referrals.append(
        ExtractedReferral(
            contact_external_id=contact,
            provider_message_id=provider_message_id,
            phone_number_id=phone_number_id,
            source=fields["source"],
            source_id=fields["source_id"],
            headline=fields["headline"],
            body=fields["body"],
            media_type=fields["media_type"],
            ctwa_clid=fields["ctwa_clid"],
            raw_payload=dict(referral),
        )
    )
