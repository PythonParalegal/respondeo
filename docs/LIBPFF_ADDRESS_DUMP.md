# libpff-python — Email Address Extraction Reference

**Last updated:** 2026-03-27
**Applies to:** `container_exploder.py` address extraction from PST messages

---

This document summarizes the MAPI property tags used for email address
extraction from pypff message objects. The canonical tag reference is in
`LIBPFF_API_REFERENCE.md`; this file documents which tags reliably contain
SMTP addresses vs display names.

> **Note:** All examples below use synthetic placeholder values.

## Address Property Tags (Confirmed Present)

| Tag | Known Name | Contains |
|-----|-----------|----------|
| 0x0037 | PR_SUBJECT | Email subject line |
| 0x003B | PR_SENT_REPRESENTING_SEARCH_KEY | Sender search key (encoded, often `SMTP:SENDER@EXAMPLE.COM`) |
| 0x0040 | (unnamed) | Received-by email address (SMTP) |
| 0x0042 | PR_SENT_REPRESENTING_NAME | Sender display name |
| 0x0044 | (unnamed) | Received-representing email address (SMTP) |
| 0x0064 | PR_SENT_REPRESENTING_ADDRTYPE | Address type (always `SMTP` for internet mail) |
| 0x0065 | PR_SENT_REPRESENTING_EMAIL_ADDRESS | Sender SMTP address |
| 0x0070 | PR_CONVERSATION_TOPIC | Thread subject (without Re:/Fwd: prefix) |
| 0x0075 | PR_RECEIVED_BY_ADDRTYPE | Recipient address type |
| 0x0076 | PR_RECEIVED_BY_EMAIL_ADDRESS | Recipient SMTP address |
| 0x007D | PR_TRANSPORT_MESSAGE_HEADERS | Raw RFC 2822 headers (richest source) |
| 0x0C1A | PR_SENDER_NAME | Sender display name |
| 0x0C1E | PR_SENDER_ADDRTYPE | Sender address type |
| 0x0C1F | PR_SENDER_EMAIL_ADDRESS | Sender SMTP address |
| 0x0E03 | PR_DISPLAY_CC | CC display names (semicolon-separated) |
| 0x0E04 | PR_DISPLAY_TO | To display names (semicolon-separated) |
| 0x3FFA | PR_LAST_MODIFIER_NAME | Last modifier (often recipient email) |

## Extraction Strategy

1. **Primary:** Parse `transport_headers` (tag 0x007D) — most reliable for full From/To/Cc with both display names and SMTP addresses.
2. **Fallback:** Use `PR_SENDER_EMAIL_ADDRESS` (0x0C1F) for From, `PR_DISPLAY_TO` (0x0E04) for To.
3. **Display names only:** `PR_SENT_REPRESENTING_NAME` (0x0042) and `PR_SENDER_NAME` (0x0C1A) have display names without email addresses.

## Key Findings from Introspection

- Tags 0x003B, 0x0051, 0x0052, 0x0C1D contain encoded search keys (not directly usable as addresses).
- Tags 0x003F, 0x0041, 0x0043, 0x0C19 contain MAPI entry IDs with embedded address data in UTF-16-LE (binary type 258). Decoding these is unreliable; use transport_headers instead.
- Tags 0x680D/0x680E and 0x800D/0x800E are unnamed and appear to duplicate the recipient address.
- When transport_headers are absent (some sent-items), fall back to the MAPI properties above.
