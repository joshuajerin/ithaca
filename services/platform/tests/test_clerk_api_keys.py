from __future__ import annotations

import json

from ithaca_platform import AuthStore, ClerkManagedApiKeyStore, UserStore


class _Response:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return json.dumps(self.payload).encode()


def _linked_identity(db):
    auth = AuthStore(db)
    tenant_id = auth.create_tenant("Clerk tenant")
    subject = "user_2xhFjEI5X2qWRvtV13BzSj8H6Dk"
    UserStore(db).oauth_upsert(
        "clerk", subject, "clerk@example.test", "Clerk user", None, tenant_id
    )
    return subject, tenant_id


def test_clerk_creates_and_verifies_tenant_bound_key(db):
    subject, tenant_id = _linked_identity(db)
    requests = []
    key = {
        "id": "ak_3beecc9c60adb5f9b850e91a8ee1e992",
        "secret": "ak_live_secret",
        "subject": subject,
        "name": "Ithaca agent key",
        "claims": {"ithaca_managed": True, "ithaca_tenant_id": tenant_id},
        "scopes": ["data:read"],
        "revoked": False,
        "expired": False,
        "created_at": 1_754_938_436_732,
        "last_used_at": None,
    }

    def urlopen(request, timeout):
        requests.append((request, timeout))
        if request.full_url.endswith("/api_keys"):
            return _Response(key)
        return _Response({k: v for k, v in key.items() if k != "secret"})

    store = ClerkManagedApiKeyStore(db, "sk_test_secret", urlopen=urlopen)
    secret, key_id = store.create_key(
        subject=subject, tenant_id=tenant_id, scopes=["data:read"]
    )
    assert (secret, key_id) == ("ak_live_secret", key["id"])
    create_body = json.loads(requests[0][0].data)
    assert create_body["subject"] == subject
    assert create_body["claims"]["ithaca_tenant_id"] == tenant_id
    assert create_body["claims"]["ithaca_managed"] is True
    assert requests[0][0].headers["Authorization"] == "Bearer sk_test_secret"
    assert requests[0][0].headers["User-agent"].startswith("Ithaca/1.0")

    assert store.verify(secret) == {
        "tenant_id": tenant_id,
        "scopes": ["data:read"],
        "key_id": key["id"],
    }


def test_clerk_rejects_unmanaged_or_cross_tenant_key(db):
    subject, tenant_id = _linked_identity(db)

    def unmanaged(_request, timeout):
        return _Response(
            {
                "id": "ak_3beecc9c60adb5f9b850e91a8ee1e992",
                "subject": subject,
                "claims": None,
                "scopes": ["data:read"],
                "revoked": False,
                "expired": False,
            }
        )

    store = ClerkManagedApiKeyStore(db, "sk_test_secret", urlopen=unmanaged)
    assert store.verify("ak_secret") is None

    other_tenant = AuthStore(db).create_tenant("Other")

    def cross_tenant(_request, timeout):
        return _Response(
            {
                "id": "ak_3beecc9c60adb5f9b850e91a8ee1e992",
                "subject": subject,
                "claims": {
                    "ithaca_managed": True,
                    "ithaca_tenant_id": other_tenant,
                },
                "scopes": ["data:read"],
                "revoked": False,
                "expired": False,
            }
        )

    store = ClerkManagedApiKeyStore(db, "sk_test_secret", urlopen=cross_tenant)
    assert store.verify("ak_secret") is None


def test_clerk_list_and_revoke_only_include_ithaca_managed_keys(db):
    subject, tenant_id = _linked_identity(db)
    calls = []
    managed = {
        "id": "ak_3beecc9c60adb5f9b850e91a8ee1e992",
        "subject": subject,
        "name": "Ithaca agent key",
        "claims": {"ithaca_managed": True, "ithaca_tenant_id": tenant_id},
        "scopes": ["data:read"],
        "revoked": False,
        "expired": False,
        "created_at": 1_754_938_436_732,
        "last_used_at": None,
    }

    def urlopen(request, timeout):
        calls.append(request)
        if request.method == "GET":
            return _Response(
                {
                    "data": [managed, {**managed, "id": "ak_other", "claims": None}],
                    "total_count": 2,
                }
            )
        return _Response({**managed, "revoked": True})

    store = ClerkManagedApiKeyStore(db, "sk_test_secret", urlopen=urlopen)
    listed = store.list_keys(subject=subject, tenant_id=tenant_id)
    assert [item["key_id"] for item in listed] == [managed["id"]]
    assert listed[0]["managed_by"] == "clerk"
    assert store.revoke_key(key_id=managed["id"], subject=subject, tenant_id=tenant_id)
    assert calls[-1].full_url.endswith(f"/api_keys/{managed['id']}/revoke")
