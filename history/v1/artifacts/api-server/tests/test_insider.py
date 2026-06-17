"""Unit tests for the SEC EDGAR insider-transactions (Form 4/5) feed.

Runnable two ways:
    python artifacts/api-server/tests/test_insider.py   # standalone
    pytest artifacts/api-server/tests/test_insider.py    # if pytest installed

These tests are regression guards for the Form 4 XML quirk that bit us: most
ownership fields (shares, price, dates, securityTitle) ARE wrapped in a
``<value>`` element, but several are NOT — ``transactionCode``, ``rptOwnerName``,
``issuerName`` and the ``reportingOwnerRelationship`` flags are direct text.
Reading those with the ``<value>`` helper silently yields ``None``, which made
every trade classify as ``other`` (sentiment always "no activity") and every
insider render as "Unknown". The parser must read each field with the right
helper. We assert on a synthetic-but-realistic filing so no network is touched.
"""
from __future__ import annotations

import os
import sys
import xml.etree.ElementTree as ET

# Make the api-server package importable regardless of how the test is invoked.
_API_SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _API_SERVER_DIR not in sys.path:
    sys.path.insert(0, _API_SERVER_DIR)

from app.sources import edgar  # noqa: E402


# A trimmed but structurally faithful Form 4: a direct-text transactionCode and
# owner/issuer/relationship fields, with <value>-wrapped amounts and dates. It
# carries one open-market sale (S), one option exercise (M) and one tax
# withholding (F) so we can prove code -> type classification.
_FORM4_XML = """<?xml version="1.0"?>
<ownershipDocument>
  <issuer>
    <issuerCik>0000796343</issuerCik>
    <issuerName>ADOBE INC.</issuerName>
    <issuerTradingSymbol>ADBE</issuerTradingSymbol>
  </issuer>
  <reportingOwner>
    <reportingOwnerId>
      <rptOwnerCik>0001234567</rptOwnerCik>
      <rptOwnerName>NARAYEN SHANTANU</rptOwnerName>
    </reportingOwnerId>
    <reportingOwnerRelationship>
      <isDirector>1</isDirector>
      <isOfficer>1</isOfficer>
      <officerTitle>Chair and CEO</officerTitle>
    </reportingOwnerRelationship>
  </reportingOwner>
  <nonDerivativeTable>
    <nonDerivativeTransaction>
      <securityTitle><value>Common Stock</value></securityTitle>
      <transactionDate><value>2026-04-30</value></transactionDate>
      <transactionCoding>
        <transactionCode>S</transactionCode>
      </transactionCoding>
      <transactionAmounts>
        <transactionShares><value>755</value></transactionShares>
        <transactionPricePerShare><value>246.245</value></transactionPricePerShare>
        <transactionAcquiredDisposedCode><value>D</value></transactionAcquiredDisposedCode>
      </transactionAmounts>
      <postTransactionAmounts>
        <sharesOwnedFollowingTransaction><value>10000</value></sharesOwnedFollowingTransaction>
      </postTransactionAmounts>
    </nonDerivativeTransaction>
    <nonDerivativeTransaction>
      <securityTitle><value>Common Stock</value></securityTitle>
      <transactionDate><value>2026-04-28</value></transactionDate>
      <transactionCoding>
        <transactionCode>F</transactionCode>
      </transactionCoding>
      <transactionAmounts>
        <transactionShares><value>120</value></transactionShares>
        <transactionPricePerShare><value>250.00</value></transactionPricePerShare>
        <transactionAcquiredDisposedCode><value>D</value></transactionAcquiredDisposedCode>
      </transactionAmounts>
    </nonDerivativeTransaction>
  </nonDerivativeTable>
  <derivativeTable>
    <derivativeTransaction>
      <securityTitle><value>Restricted Stock Unit</value></securityTitle>
      <transactionDate><value>2026-04-28</value></transactionDate>
      <transactionCoding>
        <transactionCode>M</transactionCode>
      </transactionCoding>
      <transactionAmounts>
        <transactionShares><value>500</value></transactionShares>
        <transactionPricePerShare><value>0</value></transactionPricePerShare>
        <transactionAcquiredDisposedCode><value>A</value></transactionAcquiredDisposedCode>
      </transactionAmounts>
    </derivativeTransaction>
  </derivativeTable>
</ownershipDocument>"""


def _parse():
    doc = edgar._parse_ownership_xml(_FORM4_XML)
    assert doc is not None, "failed to parse synthetic Form 4 XML"
    return edgar._transactions_from_doc(
        doc, symbol="ADBE", cik10="0000796343", accession="0000796343-26-000107",
        form="4", filing_date="2026-05-01",
        url="https://www.sec.gov/Archives/edgar/data/796343/x-index.htm",
    )


# ---------------------- transactionCode (direct text) ----------------------
def test_transaction_codes_parse_not_none():
    rows = _parse()
    codes = {r["code"] for r in rows}
    # Regression: before the fix every code was None (read as a <value> child).
    assert None not in codes, "transactionCode parsed as None (the <value> bug)"
    assert codes == {"S", "F", "M"}, codes


def test_codes_classify_to_sentiment_types():
    rows = _parse()
    by_code = {r["code"]: r["type"] for r in rows}
    assert by_code["S"] == "sell"
    assert by_code["F"] == "tax"
    assert by_code["M"] == "option-exercise"
    # Not everything collapses to the catch-all "other".
    assert "other" not in by_code.values()


# ---------------------- owner name + role (direct text) --------------------
def test_insider_name_and_role_populate():
    rows = _parse()
    assert rows, "no rows parsed"
    insider = rows[0]["insider"]
    role = rows[0]["role"]
    assert insider == "NARAYEN SHANTANU", f"owner name not parsed: {insider!r}"
    assert insider != "Unknown"
    # Director + Officer(title) both come from direct-text relationship flags.
    assert "Director" in role and "Officer" in role and "Chair and CEO" in role, role


def test_issuer_name_populates():
    rows = _parse()
    assert rows[0]["issuerName"] == "ADOBE INC.", rows[0]["issuerName"]


# ---------------------- value-wrapped amounts still parse ------------------
def test_amounts_and_value_compute():
    rows = _parse()
    sale = next(r for r in rows if r["code"] == "S")
    assert sale["shares"] == 755.0
    assert sale["price"] == 246.245
    assert sale["value"] == round(755 * 246.245, 2)
    assert sale["sharesOwnedAfter"] == 10000.0
    assert sale["transactionDate"] == "2026-04-30"
    assert sale["filingDate"] == "2026-05-01"
    assert sale["isDerivative"] is False
    deriv = next(r for r in rows if r["code"] == "M")
    assert deriv["isDerivative"] is True


# ---------------------- end-to-end fetch (no network) ----------------------
def test_fetch_insider_transactions_builds_envelope(monkeypatch=None):
    # Patch the three network seams: CIK resolution, submissions index, and the
    # raw filing fetch. No HTTP is performed.
    orig_resolve = edgar.resolve_cik
    orig_subs = edgar.fetch_submissions
    orig_get = edgar._get

    class _Resp:
        text = _FORM4_XML

    edgar.resolve_cik = lambda t: ("0000796343", "ADOBE INC.")
    edgar.fetch_submissions = lambda cik: {
        "name": "ADOBE INC.",
        "filings": {"recent": {
            "form": ["4"],
            "accessionNumber": ["0000796343-26-000107"],
            "filingDate": ["2026-05-01"],
            "primaryDocument": ["x.xml"],
        }},
    }
    edgar._get = lambda url, **kw: _Resp()
    try:
        out = edgar.fetch_insider_transactions("ADBE", since_days=3650)
    finally:
        edgar.resolve_cik = orig_resolve
        edgar.fetch_submissions = orig_subs
        edgar._get = orig_get

    assert out["source"] == "live", out["source"]
    assert out["symbol"] == "ADBE"
    assert out["issuerName"] == "ADOBE INC."
    assert out["asOf"] == "2026-05-01"
    txns = out["transactions"]
    assert len(txns) == 3, len(txns)
    assert {t["code"] for t in txns} == {"S", "F", "M"}
    # Most recent transactionDate first.
    assert txns[0]["transactionDate"] >= txns[-1]["transactionDate"]


def test_unknown_ticker_is_unavailable_not_fabricated():
    orig_resolve = edgar.resolve_cik
    edgar.resolve_cik = lambda t: None
    try:
        out = edgar.fetch_insider_transactions("NOTATICKER")
    finally:
        edgar.resolve_cik = orig_resolve
    assert out["source"] == "unavailable"
    assert out["transactions"] == []  # never invents trades


def _run_all():
    funcs = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    passed = 0
    for fn in funcs:
        fn()
        passed += 1
        print(f"  PASS {fn.__name__}")
    print(f"\n{passed}/{len(funcs)} insider tests passed")


if __name__ == "__main__":
    _run_all()
