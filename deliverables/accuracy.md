# Accuracy

## Result

| Check | Result |
|---|---|
| 11 fields, exact string match, 21 documents | 229/231 |
| business_purpose present and found in the message | 21/21 |
| supporting quotes not found in the message | 0 of 76 |
| expected-null fields with no issue | 0 of 23 |
| route matches | 21/21 |

## Source of the results

| Provider | Model | Documents |
|---|---|---|
| mock | mock | 21 |

Mocked results: canned replies in mock_replies/, one per document, authored by hand from the message text. No model produced them.

Injected errors (labelled `_deliberate_error` in the mock reply files):
- IT-012.json: permission is 'write' but the message requests admin (deliberately wrong, to show the accuracy check catching it)
- IT-018.json: end_date is 2026-10-27 but the message gives 2026-11-03 (deliberately wrong, to show the accuracy check catching it)

Live observation: none. No record in this file came from a live provider.

## Procedure and counting rules

1. Expected facts in expected/expected_fields.json were written by hand from the request messages and the office policy, and committed before any mock reply existed.
2. Each document is read from its current record. The 20 supplied messages come from the queue's state; the paraphrase is processed into a separate store and is not in the queue.
3. Exact-match fields: request_id, request_date, kind, requester, team, system, environment, permission, start_date, end_date, manager. Each is compared as an exact string with no trimming or case folding. null equals null. null against a value is a mismatch. Denominator: 21 documents x 11 fields = 231. A document with no valid extraction counts all 11 fields as mismatches.
4. business_purpose is free text and is not exact-matched. Where the expected file says a purpose is present, the extraction must have a non-null purpose that is a whitespace-normalised substring of the message. Where it says absent, the extraction must be null.
5. Supporting quotes: each must be an exact substring of the decoded message. Counted across all documents with an extraction.
6. Expected-null fields: every field expected to be null (the 11 fields, plus business_purpose where absent) must be explained by an issue that names the field. Counted per field.
7. Route match: the record's owner, status and next_action must all equal the expected route derived from the policy.
8. Factual-error reporting: a mismatch is classed as wrong value (a different value), invented value (a value where the message gives none or leaves it unresolved), missing value (null where the message states one), or no extraction. Wrong and invented values are factual errors; missing values are omissions.

## Mismatches

Counts by class: wrong value 2.

| Document | Field | Expected | Got | Class |
|---|---|---|---|---|
| IT-012.json | permission | admin | write | wrong value |
| IT-018.json | end_date | 2026-11-03 | 2026-10-27 | wrong value |

## Other checks

business_purpose: 21/21.

Supporting quotes not found in the message: 0 of 76.

Expected-null fields with no issue naming them: 0 of 23.

Route matches: 21/21.

| Document | Expected | Got | Match |
|---|---|---|---|
| IT-001.json | System Owner / review / review-request | System Owner / review / review-request | yes |
| IT-002.json | Security Review / review / review-risk-then-owner | Security Review / review / review-risk-then-owner | yes |
| IT-003.json | IT Service Desk / needs-information / clarify | IT Service Desk / needs-information / clarify | yes |
| IT-004.json | IT Service Desk / needs-information / clarify | IT Service Desk / needs-information / clarify | yes |
| IT-005.json | IT Service Desk / review / confirm-withdrawal | IT Service Desk / review / confirm-withdrawal | yes |
| IT-006.json | IT Service Desk / review / inspect-message | IT Service Desk / review / inspect-message | yes |
| IT-007.json | Security Review / review / review-risk-then-owner | Security Review / review / review-risk-then-owner | yes |
| IT-008.json | System Owner / review / review-request | System Owner / review / review-request | yes |
| IT-009.json | IT Service Desk / needs-information / clarify | IT Service Desk / needs-information / clarify | yes |
| IT-010.json | IT Service Desk / needs-information / clarify | IT Service Desk / needs-information / clarify | yes |
| IT-011.json | IT Service Desk / needs-information / clarify | IT Service Desk / needs-information / clarify | yes |
| IT-012.json | Security Review / review / review-risk-then-owner | Security Review / review / review-risk-then-owner | yes |
| IT-013.json | Security Review / review / review-risk-then-owner | Security Review / review / review-risk-then-owner | yes |
| IT-014.json | IT Service Desk / needs-information / clarify | IT Service Desk / needs-information / clarify | yes |
| IT-015.json | System Owner / review / review-request | System Owner / review / review-request | yes |
| IT-016.json | IT Service Desk / needs-information / clarify | IT Service Desk / needs-information / clarify | yes |
| IT-017.json | IT Service Desk / needs-information / clarify | IT Service Desk / needs-information / clarify | yes |
| IT-018.json | System Owner / review / review-request | System Owner / review / review-request | yes |
| IT-019.json | Security Review / review / review-risk-then-owner | Security Review / review / review-risk-then-owner | yes |
| IT-020.json | IT Service Desk / needs-information / clarify | IT Service Desk / needs-information / clarify | yes |
| IT-021.json | System Owner / review / review-request | System Owner / review / review-request | yes |

## Expected fields

Written from the messages. null = absent, unresolved, conflicting or relative in the message.

| Document | request_id | request_date | kind | requester | team | system | environment | permission | start_date | end_date | manager | business_purpose |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| IT-001.json | IT-001 | 2026-10-22 | new | Maya Chen | Analytics | Atlas | staging | read | 2026-10-23 | 2026-11-06 | Priya Shah | present |
| IT-002.json | IT-002 | 2026-10-22 | new | Owen Reed | Payments | Ledger | production | write | 2026-10-24 | 2026-10-25 | Elena Park | present |
| IT-003.json | IT-003 | 2026-10-22 | new | Lina Gomez | Customer Success | Beacon | null | null | null | null | Priya Shah | present |
| IT-004.json | IT-004 | 2026-10-22 | new | Theo Malik | Quality Engineering | Atlas | null | read | 2026-10-23 | 2026-10-30 | Nia Patel | present |
| IT-005.json | IT-005 | 2026-10-22 | withdrawal | Ava Brooks | Design | null | null | null | null | null | Elena Park | absent |
| IT-006.json | IT-006 | 2026-10-22 | new | Finn Lee | Platform | Atlas | staging | read | 2026-10-23 | 2026-10-24 | Nia Patel | present |
| IT-007.json | IT-007 | 2026-10-22 | change | Grace Tan | Developer Experience | Forge | staging | write | 2026-10-24 | 2026-10-28 | Nia Patel | present |
| IT-008.json | IT-008 | 2026-10-22 | new | Noah Kim | Finance | Atlas | staging | read | 2026-10-25 | 2026-10-31 | Priya Shah | present |
| IT-009.json | IT-009 | 2026-10-22 | new | Isla Morgan | Support | Beacon | staging | read | 2026-10-26 | 2026-10-29 | null | present |
| IT-010.json | IT-010 | 2026-10-22 | new | Ben Carter | Operations | Ledger | production | read | 2026-10-27 | null | Elena Park | present |
| IT-011.json | IT-011 | 2026-10-22 | new | Zoe Adams | Research | Atlas | staging | read | null | null | Priya Shah | present |
| IT-012.json | IT-012 | 2026-10-22 | new | Ravi Shah | Infrastructure | Forge | staging | admin | 2026-10-26 | 2026-10-27 | Nia Patel | present |
| IT-013.json | IT-013 | 2026-10-22 | new | Emma Wilson | Compliance | Beacon | production | read | 2026-10-28 | 2026-10-30 | Elena Park | present |
| IT-014.json | IT-014 | 2026-10-22 | new | Lucas Brown | Sales Operations | Atlas | staging | read | 2026-11-05 | 2026-11-02 | Priya Shah | present |
| IT-015.json | IT-015 | 2026-10-22 | new | Mia Davis | Learning | Beacon | staging | read | 2026-10-29 | 2026-10-31 | Elena Park | present |
| IT-016.json | IT-061 | 2026-10-22 | new | Alex Turner | Platform | Forge | staging | read | 2026-10-26 | 2026-10-28 | Nia Patel | present |
| IT-017.json | IT-017 | 2026-10-22 | other | Chloe Martin | Communications | null | null | null | null | null | null | absent |
| IT-018.json | IT-018 | 2026-10-22 | new | Daniel Wright | Data Engineering | Atlas | staging | read | 2026-10-27 | 2026-11-03 | Priya Shah | present |
| IT-019.json | IT-019 | 2026-10-22 | change | Sara Ahmed | Customer Operations | Beacon | production | read | 2026-10-28 | 2026-11-04 | Elena Park | present |
| IT-020.json | IT-020 | 2026-10-22 | new | Ethan Clark | Product | Atlas | staging | read | 2026-10-29 | 2026-11-02 | null | present |
| IT-021.json (paraphrase) | IT-021 | 2026-10-22 | new | Tomas Rivera | Procurement | Beacon | staging | read | 2026-11-09 | 2026-11-13 | Dana Whitfield | present |

Paraphrase message (IT-021.json, authored for this check, not in the queue):

> Hello team, Tomas Rivera from Procurement here. Ticket IT-021, filed 2026-10-22. Could you set me up with view-only access to Beacon on the staging side, running 2026-11-09 until 2026-11-13? My line manager is Dana Whitfield. I'm going through the sample vendor invoices to see whether the supplier names line up with the contract list ahead of the quarterly vendor review.

## Model and configuration

- Configured provider: mock; model: claude-sonnet-5-5; max_tokens: 1500; tool_choice: forced single tool call (record_access_request); temperature: not sent (not a parameter of messages.create in anthropic 2.3.0).
- Policy version: rules-1+policy-b949596765ae.
- Records: 21 produced by provider mock, settings fingerprint f0a3b1eb9adc, policy version rules-1+policy-b949596765ae.

