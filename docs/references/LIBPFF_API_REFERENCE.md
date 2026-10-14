# libpff-python (pypff) API Reference — eDiscovery Platform Usage

**Last updated:** 2026-03-18  
**Applies to:** `container_exploder.py` (`explode_pst_libpff`, `_libpff_msg_to_eml_bytes`, `_walk_pst_folder_libpff`)  
**Source:** https://github.com/libyal/libpff  
**PyPI:** `libpff-python` (pre-compiled wheel in `vendor/wheels/`)  
**Introspection source:** `sample.pst`, Python 3.11.9  
**Verified against:** Object introspection dump + MAPI record set entries dump

---

## CRITICAL FINDING

**The pypff `attachment` object does NOT expose `name`, `long_filename`, `short_filename`, or `content_type` as direct Python attributes.** The attachment object has only 16 attributes, none of which are filename-related.

**All attachment metadata (filenames, MIME types, CID references) must be accessed through the `record_sets` MAPI property interface.** This is confirmed by introspection — the only data-bearing attributes on `pypff.attachment` are `identifier`, `size`, and `read_buffer()`.

Our previous code used `getattr(att, 'name', None)` — which silently returned `None` every time because the attribute does not exist.

---

## PST File Object (`pypff.file`)

```python
pst = pypff.file()
pst.open(pst_path)
root = pst.get_root_folder()
# ... process ...
pst.close()
```

### Key Attributes

| Attribute | Type | Description |
|-----------|------|-------------|
| `root_folder` | folder | Root folder of the PST. |
| `size` | int | PST file size in bytes. |
| `content_type` | int | PST content type identifier. |
| `encryption_type` | int | Encryption type. |

### Key Methods

| Method | Returns | Description |
|--------|---------|-------------|
| `open(path)` | None | Open a PST file. |
| `close()` | None | Close the file handle. |
| `get_root_folder()` | folder | Get the root folder object. |

---

## Folder Object (`pypff.folder`)

### Key Attributes

| Attribute | Type | Sample | Description |
|-----------|------|--------|-------------|
| `name` | str or None | `'SPAM Search Folder 2'` | Folder display name. Root folder has `None`. |
| `identifier` | int | `8739` | Internal folder ID. |
| `number_of_sub_folders` | int | — | Count of child folders. |
| `number_of_sub_messages` | int | — | Count of messages in this folder. |

### Key Methods

| Method | Returns | Description |
|--------|---------|-------------|
| `get_sub_folder(index)` | folder | Get child folder by 0-based index. |
| `get_sub_message(index)` | message | Get message by 0-based index. **This is the correct method name** — `get_message` does not exist. |

### Traversal Pattern

```python
def walk(folder):
    for i in range(folder.number_of_sub_messages):
        msg = folder.get_sub_message(i)
        process(msg)
    for i in range(folder.number_of_sub_folders):
        sub = folder.get_sub_folder(i)
        walk(sub)
```

---

## Message Object (`pypff.message`)

### Direct Attributes (42 total)

| Attribute | Type | Sample | Description |
|-----------|------|--------|-------------|
| `subject` | str | `'Re: Updated Project...'` | Email subject. |
| `sender_name` | str | `'Jane Doe'` | Sender display name only — **no email address as direct attribute**. |
| `conversation_topic` | str | `'Updated Project...'` | Thread topic (subject without Re:/Fwd:). |
| `client_submit_time` | datetime | `datetime(2020, 1, 15, 9, 0)` | **Send time.** |
| `delivery_time` | datetime | `datetime(2020, 1, 15, 9, 1)` | **Receive time.** |
| `creation_time` | datetime | `datetime(2020, 1, 16, 8, 0)` | PST item creation (often import date, NOT email creation). |
| `modification_time` | datetime | `datetime(2020, 1, 15, 9, 1)` | Last modification. |
| `html_body` | bytes or None | — | HTML body. Decode as UTF-8. |
| `plain_text_body` | bytes or None | — | Plain text body. Decode as UTF-8. |
| `rtf_body` | bytes or None | — | RTF body (rarely populated). |
| `transport_headers` | str | `'Return-Path: <jane@...'` | **Raw RFC 2822 headers** — richest source for email metadata. |
| `number_of_attachments` | int | `2` | Attachment count. |
| `number_of_entries` | int | `53` | MAPI property entries count. |
| `number_of_record_sets` | int | `1` | Record set count. |

### What Is NOT a Direct Attribute

These properties do NOT exist on `pypff.message` and `getattr()` will silently return the default:

| Property Needed | Where It Actually Lives |
|----------------|------------------------|
| Sender email address | `transport_headers` (parse `From:`) or record_set tag `0x0C1F` |
| Recipients (To/Cc/Bcc) | `transport_headers` (parse `To:`, `Cc:`, `Bcc:`) |
| `number_of_recipients` | **Does not exist.** Always returns 0 via getattr. |
| `get_recipient(i)` | **Does not exist.** |
| Message-ID | `transport_headers` (parse `Message-ID:`) |
| In-Reply-To | `transport_headers` (parse `In-Reply-To:`) |
| References | `transport_headers` (parse `References:`) |
| Conversation index (binary) | Record set tag `0x0071` |

### Parsing Transport Headers

The `transport_headers` attribute is the most reliable way to get email addresses and threading headers:

```python
from email import message_from_string, policy

if msg.transport_headers:
    headers = message_from_string(msg.transport_headers, policy=policy.default)
    from_addr = headers.get('From')           # "Jane Doe <jane@example.com>"
    to_addr = headers.get('To')               # May be comma-separated
    cc_addr = headers.get('Cc')
    message_id = headers.get('Message-ID')
    in_reply_to = headers.get('In-Reply-To')
    references = headers.get('References')
    date_str = headers.get('Date')
```

### Key Methods

| Method | Returns | Description |
|--------|---------|-------------|
| `get_attachment(index)` | attachment | Get attachment by 0-based index. |
| `get_transport_headers()` | str or None | Get raw RFC 2822 headers. |
| `get_subject()` | str or None | Get subject. |
| `get_sender_name()` | str or None | Get sender display name. |
| `get_client_submit_time()` | datetime or None | Get send time. |
| `get_delivery_time()` | datetime or None | Get receive time. |
| `get_html_body()` | bytes or None | Get HTML body. |
| `get_plain_text_body()` | bytes or None | Get plain text body. |
| `get_record_set(index)` | record_set | Get MAPI record set. |

---

## Attachment Object (`pypff.attachment`)

### Direct Attributes (16 total — NO filename attributes)

| Attribute | Type | Sample | Description |
|-----------|------|--------|-------------|
| `identifier` | int | `32805` | Internal attachment ID. |
| `size` | int | `24576` | Attachment payload size in bytes. |
| `number_of_entries` | int | `11` | MAPI property entries count. |
| `number_of_record_sets` | int | `1` | Record set count (always 1 in practice). |

### Key Methods

| Method | Returns | Description |
|--------|---------|-------------|
| `read_buffer(size)` | bytes | Read raw attachment payload. |
| `seek_offset(offset, whence)` | None | Seek within attachment data. |
| `get_record_set(index)` | record_set | **Where filenames and MIME types live.** |

---

## Record Set API (Confirmed by Introspection)

### record_set

| Attribute/Method | Type | Description |
|-----------------|------|-------------|
| `number_of_entries` | int | Count of MAPI property entries. |
| `get_entry(index)` | record_entry | Get entry by 0-based index. |

### record_entry (CONFIRMED)

| Attribute | Type | Description |
|-----------|------|-------------|
| `entry_type` | int | MAPI property tag (e.g., `0x3707`). |
| `value_type` | int | MAPI value type (see table below). |
| `data` | bytes | Raw property data. |
| `data_as_string` | str | **Decodes UTF-16-LE strings.** Only works for value_type 31. Throws `ValueError` on other types. |
| `data_as_integer` | int | Works for value_type 3. Throws on other types. |
| `data_as_datetime` | datetime | Works for value_type 64. Throws on other types. |
| `data_as_boolean` | bool | Works for value_type 11. Throws on other types. |
| `data_as_floating_point` | float | Works for float types. Throws on others. |
| `data_as_size` | int | Alias for integer in some contexts. |

### Value Types

| Value | MAPI Type | Python Accessor |
|-------|-----------|-----------------|
| 3 | PT_LONG (integer) | `entry.data_as_integer` |
| 11 | PT_BOOLEAN | `entry.data_as_boolean` |
| 31 | PT_UNICODE (UTF-16-LE string) | `entry.data_as_string` |
| 64 | PT_SYSTIME (datetime) | `entry.data_as_datetime` |
| 258 | PT_BINARY | `entry.data` (raw bytes) |

---

## Reading Attachment Properties

### Helper Function

```python
def _get_record_entry(obj, property_tag):
    """
    Read a MAPI property from a pypff object's record sets.
    Returns the record_entry object, or None if not found.
    """
    for rs_idx in range(obj.number_of_record_sets):
        rs = obj.get_record_set(rs_idx)
        for e_idx in range(rs.number_of_entries):
            entry = rs.get_entry(e_idx)
            if entry.entry_type == property_tag:
                return entry
    return None

def _get_record_string(obj, property_tag):
    """Read a string MAPI property (value_type 31 = PT_UNICODE)."""
    entry = _get_record_entry(obj, property_tag)
    if entry is None:
        return None
    try:
        return entry.data_as_string
    except Exception:
        # Fallback: manual UTF-16-LE decode
        if entry.data:
            try:
                return entry.data.decode('utf-16-le').rstrip('\x00')
            except UnicodeDecodeError:
                return None
    return None

def _get_record_integer(obj, property_tag):
    """Read an integer MAPI property (value_type 3 = PT_LONG)."""
    entry = _get_record_entry(obj, property_tag)
    if entry is None:
        return None
    try:
        return entry.data_as_integer
    except Exception:
        return None
```

### MAPI Property Tags for Attachments (Confirmed Present)

| Tag | Constant | Value Type | Confirmed Value |
|-----|----------|-----------|-----------------|
| `0x3707` | PR_ATTACH_LONG_FILENAME | 31 (string) | `"logo.png"` (full filename) |
| `0x3704` | PR_ATTACH_FILENAME | 31 (string) | 8.3 short name |
| `0x370E` | PR_ATTACH_MIME_TAG | 31 (string) | `"image/png"`, `"image/jpeg"` |
| `0x3712` | PR_ATTACH_CONTENT_ID | 31 (string) | CID reference (e.g., `"9A9FC2CB..."`) |
| `0x3714` | PR_ATTACH_FLAGS | 3 (integer) | Bit flags. Value `5` = bits 0+2 set (CID inline). |
| `0x3705` | PR_ATTACH_METHOD | 3 (integer) | 1=by value, 5=embedded msg, 6=OLE. |
| `0x3701` | PR_ATTACH_DATA_BIN | 258 (binary) | Raw attachment payload (same as `read_buffer`). |
| `0x0E20` | PR_ATTACH_SIZE | 3 (integer) | Attachment size. |

### Recommended Filename Resolution

```python
att_name = (
    _get_record_string(att, 0x3707)    # PR_ATTACH_LONG_FILENAME
    or _get_record_string(att, 0x3001) # PR_DISPLAY_NAME
    or _get_record_string(att, 0x3704) # PR_ATTACH_FILENAME
    or f'attachment_{i}.bin'
)

att_mime = _get_record_string(att, 0x370E)  # PR_ATTACH_MIME_TAG
att_cid = _get_record_string(att, 0x3712)   # PR_ATTACH_CONTENT_ID
att_flags = _get_record_integer(att, 0x3714) # PR_ATTACH_FLAGS
```

---

## MAPI Property Tags for Messages (Confirmed Present)

| Tag | Constant | Value Type | Notes |
|-----|----------|-----------|-------|
| `0x0017` | PR_IMPORTANCE | 3 (int) | 0=Low, 1=Normal, 2=High |
| `0x001A` | PR_MESSAGE_CLASS | 31 (string) | e.g., `"IPM.Note"` |
| `0x0037` | PR_SUBJECT | 31 (string) | Also available as `msg.subject` |
| `0x0039` | PR_CLIENT_SUBMIT_TIME | 64 (datetime) | Also available as `msg.client_submit_time` |
| `0x0042` | PR_SENT_REPRESENTING_NAME | 31 (string) | Sender display name |
| `0x0065` | PR_SENT_REPRESENTING_EMAIL_ADDRESS | 31 (string) | Sender email address |
| `0x0070` | PR_CONVERSATION_TOPIC | 31 (string) | Also available as `msg.conversation_topic` |
| `0x0071` | PR_CONVERSATION_INDEX | 258 (binary) | Threading index (binary blob) |
| `0x0075` | PR_RECEIVED_BY_EMAIL_ADDRESS | 31 (string) | Recipient email |
| `0x0076` | PR_RECEIVED_BY_NAME | 31 (string) | Recipient display name |
| `0x0C1A` | PR_SENDER_NAME | 31 (string) | Sender name |
| `0x0C1F` | PR_SENDER_EMAIL_ADDRESS | 31 (string) | Sender email address |
| `0x0E06` | PR_MESSAGE_DELIVERY_TIME | 64 (datetime) | Also available as `msg.delivery_time` |
| `0x0E07` | PR_MESSAGE_FLAGS | 3 (int) | Message flags |
| `0x1000` | PR_BODY | 31 (string) | Plain text body |
| `0x1013` | PR_BODY_HTML | 258 (binary) | HTML body (binary, decode as UTF-8) |

---

## Date Field Mapping

| Our Field | pypff Attribute | Notes |
|-----------|----------------|-------|
| `date_sent` | `msg.client_submit_time` | When sender clicked Send. |
| `date_received` | `msg.delivery_time` | When message was delivered. |
| `date_created` | `msg.creation_time` | **Caution:** Often the PST import date. |
| `date_modified` | `msg.modification_time` | Last modification. |

---

## Known Bugs in Our Code (Discovered Through Introspection)

### 1. `getattr(att, 'name', None)` — always returns None
**Severity: High.** The `name` attribute does not exist on `pypff.attachment`. Must use `_get_record_string(att, 0x3707)`.

### 2. `getattr(msg, 'number_of_recipients', 0)` — always returns 0
**Severity: High.** Recipients must be parsed from `msg.transport_headers`.

### 3. Missing `Date:` header on synthesized EMLs
**Severity: Medium.** Should use `msg.client_submit_time` formatted as RFC 2822.

### 4. Missing sender email address on synthesized EMLs
**Severity: Medium.** Should parse `From:` from `msg.transport_headers`.

### 5. Missing recipient addresses on synthesized EMLs
**Severity: Medium.** Should parse `To:`/`Cc:`/`Bcc:` from `msg.transport_headers`.
