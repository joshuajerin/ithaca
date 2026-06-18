---
name: EDGAR Form 4/5 XML field-wrapping quirk
description: Which insider-filing fields are <value>-wrapped vs direct text, and the silent-None failure it causes
---

# SEC Form 4/5 ownership XML: <value>-wrapped vs direct-text fields

In a Form 4/5 `<ownershipDocument>`, MOST fields wrap their content in a child
`<value>` element, but several do NOT — they are direct element text. Mixing
these up parses silently to `None` (no exception), so the bug only shows as bad
data downstream.

**Read with the `<value>` helper (wrapped):** securityTitle, transactionDate,
transactionAmounts/transactionShares, transactionPricePerShare,
transactionAcquiredDisposedCode, postTransactionAmounts/sharesOwnedFollowingTransaction.

**Read as direct text (NOT wrapped):** transactionCoding/transactionCode,
issuer/issuerName, reportingOwnerId/rptOwnerName, and every
reportingOwnerRelationship flag (isDirector, isOfficer, officerTitle,
isTenPercentOwner, isOther, otherText).

**Why it matters:** reading transactionCode with the value-helper made every code
`None` → every trade classified `other` → buy/sell counts 0 → sentiment always
"no open-market activity". Same wrapper mistake made every insider render
"Unknown" and every role blank.

**How to apply:** in `app/sources/edgar.py`, `_value()` = `_text(node, path +
"/value")`; `_text()` = direct element text. Pick per field per the lists above.
There is no schema enforcing this, so verify against a REAL filing (e.g. ADBE)
after any parser change — expect a realistic code distribution (S/M/F/A/G), real
insider names, and populated roles, not all-`other`/all-`Unknown`.
