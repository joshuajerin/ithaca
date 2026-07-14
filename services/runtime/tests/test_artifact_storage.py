from __future__ import annotations

from ithaca_runtime import artifact_storage


class FakeS3:
    def __init__(self):
        self.puts = []

    def put_object(self, **kwargs):
        self.puts.append(kwargs)


def test_put_artifact_uses_private_encrypted_object_storage(monkeypatch):
    fake = FakeS3()
    monkeypatch.setenv("ITHACA_ARTIFACT_BUCKET", "private-bucket")
    monkeypatch.setenv("ITHACA_ARTIFACT_ENDPOINT_URL", "https://nyc3.example.test")
    monkeypatch.setattr(artifact_storage, "_client", lambda: fake)

    uri = artifact_storage.put_artifact(
        key="backtests/t/r/summary.json",
        content=b"{}",
        media_type="application/json",
        sha256="abc",
    )

    assert uri == "s3://private-bucket/backtests/t/r/summary.json"
    assert fake.puts == [
        {
            "Bucket": "private-bucket",
            "Key": "backtests/t/r/summary.json",
            "Body": b"{}",
            "ContentType": "application/json",
            "Metadata": {"sha256": "abc"},
            "ServerSideEncryption": "AES256",
        }
    ]
