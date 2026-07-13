from __future__ import annotations

import json

import pytest

from doomberg_platform import ClerkApiError, ClerkWaitlistService


class _Response:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return json.dumps(self.payload).encode()


def test_approve_creates_then_invites_waitlist_entry():
    requests = []

    def urlopen(request, timeout):
        requests.append((request, timeout))
        if request.full_url.endswith("/waitlist_entries"):
            return _Response(
                {
                    "id": "wait_123",
                    "email_address": "approved@example.com",
                    "status": "pending",
                }
            )
        return _Response(
            {
                "id": "wait_123",
                "email_address": "approved@example.com",
                "status": "invited",
            }
        )

    service = ClerkWaitlistService("sk_test_secret", urlopen=urlopen)
    assert service.approve(" Approved@Example.com ") == {
        "action": "invited",
        "email_address": "approved@example.com",
        "status": "invited",
        "waitlist_entry_id": "wait_123",
    }
    assert json.loads(requests[0][0].data) == {
        "email_address": "approved@example.com",
        "notify": False,
    }
    assert json.loads(requests[1][0].data) == {}
    assert requests[1][0].full_url.endswith("/waitlist_entries/wait_123/invite")
    assert requests[0][0].headers["Authorization"] == "Bearer sk_test_secret"


def test_approve_is_idempotent_for_invited_entry():
    calls = []

    def urlopen(request, timeout):
        calls.append(request)
        return _Response(
            {
                "id": "wait_123",
                "email_address": "approved@example.com",
                "status": "invited",
            }
        )

    service = ClerkWaitlistService("sk_test_secret", urlopen=urlopen)
    result = service.approve("approved@example.com")
    assert result["action"] == "already_approved"
    assert len(calls) == 1


def test_approve_rejected_entry_requires_dashboard_reinvite():
    def urlopen(request, timeout):
        return _Response(
            {
                "id": "wait_123",
                "email_address": "rejected@example.com",
                "status": "rejected",
            }
        )

    service = ClerkWaitlistService("sk_test_secret", urlopen=urlopen)
    with pytest.raises(ClerkApiError, match="re-invite"):
        service.approve("rejected@example.com")
