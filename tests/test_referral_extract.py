"""Unit tests for Meta WhatsApp referral extraction."""

from __future__ import annotations

from whatsapp.referral import extract_referrals


def _payload_with_messages(messages: list[dict], phone_number_id: str = "PNID_1") -> dict:
    return {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "WABA",
                "changes": [
                    {
                        "field": "messages",
                        "value": {
                            "metadata": {"phone_number_id": phone_number_id},
                            "messages": messages,
                        },
                    }
                ],
            }
        ],
    }


def test_extract_referral_with_extra_fields() -> None:
    stats = extract_referrals(
        _payload_with_messages(
            [
                {
                    "id": "wamid.1",
                    "from": "385911111111",
                    "referral": {
                        "source": "AD",
                        "source_id": "ad_1",
                        "headline": "Hello",
                        "body": "Body",
                        "media_type": "image",
                        "ctwa_clid": "clid_abc",
                        "future_meta_field": {"nested": True},
                    },
                }
            ]
        ),
        tenant_id="ten_test",
    )
    assert stats.detected == 1
    assert stats.skipped == 0
    assert stats.referrals is not None
    assert len(stats.referrals) == 1
    ref = stats.referrals[0]
    assert ref.provider_message_id == "wamid.1"
    assert ref.contact_external_id == "385911111111"
    assert ref.ctwa_clid == "clid_abc"
    assert ref.raw_payload["future_meta_field"] == {"nested": True}


def test_extract_no_referral() -> None:
    stats = extract_referrals(
        _payload_with_messages(
            [{"id": "wamid.1", "from": "385911111111", "type": "text"}]
        )
    )
    assert stats.detected == 0
    assert stats.skipped == 0
    assert stats.referrals == []


def test_extract_missing_id_or_from_skipped() -> None:
    stats = extract_referrals(
        _payload_with_messages(
            [
                {
                    "from": "385911111111",
                    "referral": {"source": "AD", "ctwa_clid": "x"},
                },
                {
                    "id": "wamid.2",
                    "referral": {"source": "AD", "ctwa_clid": "y"},
                },
            ]
        ),
        tenant_id="ten_test",
    )
    assert stats.detected == 2
    assert stats.skipped == 2
    assert stats.referrals == []


def test_extract_malformed_referral_never_raises() -> None:
    stats = extract_referrals(
        _payload_with_messages(
            [
                {
                    "id": "wamid.bad",
                    "from": "385911111111",
                    "referral": "not-an-object",
                }
            ]
        ),
        tenant_id="ten_test",
    )
    assert stats.detected == 1
    assert stats.skipped == 1
    assert stats.referrals == []

    # Totally broken payload shapes
    assert extract_referrals(None).detected == 0
    assert extract_referrals("x").detected == 0
    assert extract_referrals({"entry": "nope"}).detected == 0
