# Synthetic Sample Data in Docs

**One-sentence summary:** Specs, preflights, lessons, and prompts use synthetic sample data for every case-like detail, so worked examples can be shared and tracked like any other doc.

## The pattern

Legal-tech development produces documents whose value lies in concrete worked examples: the Bates number where a bug manifests, the PST that breaks the extractor, the case folder that makes a query slow. Those examples are most useful when they are written from the start with obviously synthetic values. A doc built on synthetic data can be committed, reviewed, and shared without a second thought; a doc that needs special handling tends to end up untracked and eventually lost.

## How to apply

- **Matters and clients** → `Sample Matter`, `Acme Corp`, `Smith v. Jones`
- **Bates numbers** → `ABC-000001` style, with round numbers
- **Control numbers** → `DOC-000100`
- **People and files** → `Reviewer A`, `custodian_a.pst`, `jane@example.com`
- **Paths** → `D:\eDiscovery\SampleCase`
- **Counts and ranges** → round numbers (100, 250, 1,000)

Prefer natural-looking sample values over bracketed tokens; a bracketed token reads as a gap rather than an example.

The pre-commit secrets/PII guard (`.claude/hooks/precommit_pii_guard.py`) catches the most common slips (real-looking email addresses, phone numbers, keys) and any terms a developer adds to their local deny-list.

## See also

- **Related lessons:** `docs/lessons/defensibility-statement-practice.md`.
