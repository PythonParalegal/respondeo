# libpff-python — MAPI Record Set Entries Dump

**Source PST:** `sample.pst`

**Python:** `3.11.9 (tags/v3.11.9:de54cf5, Apr  2 2024, 10:12:12) [MSC v.1938 64 bit (AMD64)]`

---

This dump shows the MAPI properties stored in record_sets on message and
attachment objects. These are the ONLY way to access filenames, email
addresses, content types, and other metadata that are NOT exposed as
direct Python attributes on pypff objects.


## record_entry Object Attributes

(Dumped from first available entry to document the API)

| Attribute | Type | Value |
|-----------|------|-------|
| `data` | bytes | b'\x01\x00\x00\x00' |
| `data_as_boolean` | ? | ERROR: pypff_record_entry_get_data_as_boolean: unable to retrieve boolean value. libpff_record_entry_get_data_as_boolean: unsupported value type. |
| `data_as_datetime` | ? | ERROR: pypff_record_entry_get_data_as_datetime: value is not an datetime type. |
| `data_as_floating_point` | ? | ERROR: pypff_record_entry_get_data_as_floating_point: unable to retrieve data as floating-point value. libpff_record_entry_get_data_as_floating_point: unsupported value type. |
| `data_as_integer` | int | 1 |
| `data_as_size` | int | 1 |
| `data_as_string` | ? | ERROR: pypff_value_get_data_as_string: unable to determine size of data as UTF-8 string. libpff_record_entry_get_data_as_utf8_string_size: unsupported value type. |
| `entry_type` | int | 23 |
| `get_data` | method | get_data() -> Binary string or None

Retrieves the data. |
| `get_data_as_boolean` | method | get_data_as_boolean() -> Integer or None

Retrieves the data as a boolean. |
| `get_data_as_datetime` | method | get_data_as_datetime() -> Datetime or None

Retrieves the data as a datetime obj |
| `get_data_as_floating_point` | method | get_data_as_floating_point() -> Float or None

Retrieves the data as a floating  |
| `get_data_as_integer` | method | get_data_as_integer() -> Integer or None

Retrieves the data as an integer. |
| `get_data_as_size` | method | get_data_as_size() -> Integer or None

Retrieves the data as size. |
| `get_data_as_string` | method | get_data_as_string() -> Unicode string or None

Retrieves the data as a string. |
| `get_entry_type` | method | get_entry_type() -> Integer or None

Retrieves the entry type. |
| `get_value_type` | method | get_value_type() -> Integer or None

Retrieves the value type. |
| `value_type` | int | 3 |

---


**Sample message subject:** `Re: Project update`

**Attachment count:** 2


## Message Record Sets — "Re: Project update"

**Record sets:** 1

### Record Set 0 (53 entries)

| # | Entry Type | Value Type | Tag (hex) | Known Name | Value |
|---|-----------|------------|-----------|------------|-------|
| 0 | 0x0017 | 3 | 0x0017 | PR_IMPORTANCE | <bytes len=4, hex=01 00 00 00> |
| 1 | 0x001A | 31 | 0x001A | PR_MESSAGE_CLASS | <bytes len=16, hex=49 00 50 00 4d 00 2e 00 4e 00 6f 00 74 00 65 00> |
| 2 | 0x0037 | 31 | 0x0037 | PR_SUBJECT | <bytes len=40, hex=01 00 05 00 52 00 65 00 3a 00 20 00 50 00 72 00> |
| 3 | 0x0039 | 64 | 0x0039 | PR_CLIENT_SUBMIT_TIME | <bytes len=8, hex=00 28 b5 2a 82 cb d5 01> |
| 4 | 0x003B | 258 | 0x003B |  | "SMTP:JANE@EXAMPLE.COM" |
| 5 | 0x003F | 258 | 0x003F |  | <bytes len=86, hex=00 00 00 00 81 2b 1f a4 be a3 10 19 9d 6e 00 dd> |
| 6 | 0x0040 | 31 | 0x0040 |  | <bytes len=32, hex=6a 00 6f 00 68 00 6e 00 40 00 65 00 78 00 61 00> |
| 7 | 0x0041 | 258 | 0x0041 |  | <bytes len=86, hex=00 00 00 00 81 2b 1f a4 be a3 10 19 9d 6e 00 dd> |
| 8 | 0x0042 | 31 | 0x0042 | PR_SENT_REPRESENTING_NAME | <bytes len=16, hex=4a 00 61 00 6e 00 65 00 20 00 44 00 6f 00 65 00> |
| 9 | 0x0043 | 258 | 0x0043 |  | <bytes len=86, hex=00 00 00 00 81 2b 1f a4 be a3 10 19 9d 6e 00 dd> |
| 10 | 0x0044 | 31 | 0x0044 |  | <bytes len=32, hex=6a 00 6f 00 68 00 6e 00 40 00 65 00 78 00 61 00> |
| 11 | 0x0051 | 258 | 0x0051 |  | "SMTP:JOHN@EXAMPLE.COM" |
| 12 | 0x0052 | 258 | 0x0052 |  | "SMTP:JOHN@EXAMPLE.COM" |
| 13 | 0x0064 | 31 | 0x0064 |  | <bytes len=8, hex=53 00 4d 00 54 00 50 00> |
| 14 | 0x0065 | 31 | 0x0065 | PR_SENT_REPRESENTING_EMAIL_ADDRESS | <bytes len=32, hex=6a 00 61 00 6e 00 65 00 40 00 65 00 78 00 61 00> |
| 15 | 0x0070 | 31 | 0x0070 | PR_CONVERSATION_TOPIC | <bytes len=28, hex=50 00 72 00 6f 00 6a 00 65 00 63 00 74 00 20 00> |
| 16 | 0x0071 | 258 | 0x0071 | PR_CONVERSATION_INDEX | <bytes len=28, hex=01 01 d5 cb 82 2a b5 00 01 02 03 04 05 06 07 08> |
| 17 | 0x0075 | 31 | 0x0075 | PR_RECEIVED_BY_EMAIL_ADDRESS | <bytes len=8, hex=53 00 4d 00 54 00 50 00> |
| 18 | 0x0076 | 31 | 0x0076 | PR_RECEIVED_BY_NAME | <bytes len=32, hex=6a 00 6f 00 68 00 6e 00 40 00 65 00 78 00 61 00> |
| 19 | 0x0077 | 31 | 0x0077 |  | <bytes len=8, hex=53 00 4d 00 54 00 50 00> |
| 20 | 0x0078 | 31 | 0x0078 |  | <bytes len=32, hex=6a 00 6f 00 68 00 6e 00 40 00 65 00 78 00 61 00> |
| 21 | 0x007D | 31 | 0x007D |  | <bytes len=2048, hex=52 00 65 00 74 00 75 00 72 00 6e 00 2d 00 50 00> |
| 22 | 0x0C19 | 258 | 0x0C19 |  | <bytes len=86, hex=00 00 00 00 81 2b 1f a4 be a3 10 19 9d 6e 00 dd> |
| 23 | 0x0C1A | 31 | 0x0C1A | PR_SENDER_NAME | <bytes len=16, hex=4a 00 61 00 6e 00 65 00 20 00 44 00 6f 00 65 00> |
| 24 | 0x0C1D | 258 | 0x0C1D |  | "SMTP:JANE@EXAMPLE.COM" |
| 25 | 0x0C1E | 31 | 0x0C1E |  | <bytes len=8, hex=53 00 4d 00 54 00 50 00> |
| 26 | 0x0C1F | 31 | 0x0C1F | PR_SENDER_EMAIL_ADDRESS | <bytes len=32, hex=6a 00 61 00 6e 00 65 00 40 00 65 00 78 00 61 00> |
| 27 | 0x0E04 | 31 | 0x0E04 |  | <bytes len=20, hex=4a 00 6f 00 68 00 6e 00 20 00 53 00 6d 00 69 00> |
| 28 | 0x0E06 | 64 | 0x0E06 | PR_MESSAGE_DELIVERY_TIME | <bytes len=8, hex=00 6e 78 4e 82 cb d5 01> |
| 29 | 0x0E07 | 3 | 0x0E07 | PR_MESSAGE_FLAGS | <bytes len=4, hex=10 00 00 00> |
| 30 | 0x0E08 | 3 | 0x0E08 | PR_MESSAGE_SIZE | "탆" |
| 31 | 0x1000 | 31 | 0x1000 | PR_BODY | <bytes len=2048, hex=54 00 68 00 61 00 6e 00 6b 00 73 00 21 00 0d 00> |
| 32 | 0x1013 | 258 | 0x1013 | PR_BODY_HTML | "<html><head><meta http-equiv="Content-Type" content="text/html; charset=us-ascii"></head><body style..." (len=8192) |
| 33 | 0x1016 | 3 | 0x1016 |  | <bytes len=4, hex=00 00 00 00> |
| 34 | 0x1035 | 31 | 0x1035 |  | <bytes len=46, hex=3c 00 53 00 59 00 4e 00 54 00 48 00 30 00 30 00> |
| 35 | 0x1039 | 31 | 0x1039 |  | <bytes len=46, hex=3c 00 53 00 59 00 4e 00 54 00 48 00 30 00 30 00> |
| 36 | 0x1042 | 31 | 0x1042 |  | <bytes len=46, hex=3c 00 53 00 59 00 4e 00 54 00 48 00 30 00 30 00> |
| 37 | 0x3007 | 64 | 0x3007 |  | <bytes len=8, hex=00 80 5a f3 42 cc d5 01> |
| 38 | 0x3008 | 64 | 0x3008 |  | <bytes len=8, hex=00 6e 78 4e 82 cb d5 01> |
| 39 | 0x300B | 258 | 0x300B |  | "ɏ" |
| 40 | 0x3016 | 11 | 0x3016 |  | <bytes len=1, hex=01> |
| 41 | 0x3FDE | 3 | 0x3FDE |  | "亟" |
| 42 | 0x3FFA | 31 | 0x3FFA |  | <bytes len=32, hex=6a 00 6f 00 68 00 6e 00 40 00 65 00 78 00 61 00> |
| 43 | 0x65E2 | 258 | 0x65E2 |  | <bytes len=17, hex=10 11 12 13 14 15 16 17 18 19 1a 1b 1c 1d 1e 1f> |
| 44 | 0x65E3 | 258 | 0x65E3 |  | <bytes len=18, hex=10 10 11 12 13 14 15 16 17 18 19 1a 1b 1c 1d 1e> |
| 45 | 0x6619 | 31 | 0x6619 |  | <bytes len=512, hex=54 00 68 00 61 00 6e 00 6b 00 73 00 21 00 0d 00> |
| 46 | 0x680D | 31 | 0x680D |  | <bytes len=32, hex=6a 00 6f 00 68 00 6e 00 40 00 65 00 78 00 61 00> |
| 47 | 0x680E | 31 | 0x680E |  | <bytes len=36, hex=30 00 30 00 30 00 30 00 30 00 30 00 30 00 32 00> |
| 48 | 0x800D | 31 | 0x800D |  | <bytes len=32, hex=6a 00 6f 00 68 00 6e 00 40 00 65 00 78 00 61 00> |
| 49 | 0x800E | 31 | 0x800E |  | <bytes len=36, hex=30 00 30 00 30 00 30 00 30 00 30 00 30 00 32 00> |
| 50 | 0x8010 | 11 | 0x8010 |  | <bytes len=1, hex=01> |
| 51 | 0x8011 | 3 | 0x8011 |  | <bytes len=4, hex=01 00 00 00> |
| 52 | 0x8012 | 31 | 0x8012 |  | <bytes len=204, hex=6d 00 75 00 6c 00 74 00 69 00 70 00 61 00 72 00> |

## Attachment 0 Record Sets (size=24576 bytes)

**Record sets:** 1

### Record Set 0 (11 entries)

| # | Entry Type | Value Type | Tag (hex) | Known Name | Value |
|---|-----------|------------|-----------|------------|-------|
| 0 | 0x0E20 | 3 | 0x0E20 | PR_ATTACH_SIZE | "怀" |
| 1 | 0x3701 | 258 | 0x3701 | PR_ATTACH_DATA_BIN | <bytes len=24576, hex=89 50 4e 47 0d 0a 1a 0a 00 00 00 0d 49 48 44 52> |
| 2 | 0x3704 | 31 | 0x3704 | PR_ATTACH_FILENAME (8.3 short name) | <bytes len=24, hex=49 00 4d 00 41 00 47 00 45 00 30 00 30 00 31 00> |
| 3 | 0x3705 | 3 | 0x3705 | PR_ATTACH_METHOD | <bytes len=4, hex=01 00 00 00> |
| 4 | 0x3707 | 31 | 0x3707 | PR_ATTACH_LONG_FILENAME (full name) | <bytes len=24, hex=69 00 6d 00 61 00 67 00 65 00 30 00 30 00 31 00> |
| 5 | 0x370A | 258 | 0x370A |  | <bytes len=9, hex=2a 86 48 86 f7 14 03 0a 04> |
| 6 | 0x370B | 3 | 0x370B |  | <bytes len=4, hex=ff ff ff ff> |
| 7 | 0x370E | 31 | 0x370E | PR_ATTACH_MIME_TAG (content type) | <bytes len=18, hex=69 00 6d 00 61 00 67 00 65 00 2f 00 70 00 6e 00> |
| 8 | 0x3710 | 3 | 0x3710 |  | <bytes len=4, hex=00 00 00 00> |
| 9 | 0x3712 | 31 | 0x3712 | PR_ATTACH_CONTENT_ID (CID) | <bytes len=60, hex=69 00 6d 00 61 00 67 00 65 00 30 00 30 00 31 00> |
| 10 | 0x3714 | 3 | 0x3714 | PR_ATTACH_FLAGS | <bytes len=4, hex=05 00 00 00> |

## Attachment 1 Record Sets (size=4096 bytes)

**Record sets:** 1

### Record Set 0 (11 entries)

| # | Entry Type | Value Type | Tag (hex) | Known Name | Value |
|---|-----------|------------|-----------|------------|-------|
| 0 | 0x0E20 | 3 | 0x0E20 | PR_ATTACH_SIZE | "က" |
| 1 | 0x3701 | 258 | 0x3701 | PR_ATTACH_DATA_BIN | <bytes len=4096, hex=ff d8 ff e0 00 10 4a 46 49 46 00 01 02 00 00 64> |
| 2 | 0x3704 | 31 | 0x3704 | PR_ATTACH_FILENAME (8.3 short name) | <bytes len=24, hex=49 00 4d 00 41 00 47 00 45 00 30 00 30 00 32 00> |
| 3 | 0x3705 | 3 | 0x3705 | PR_ATTACH_METHOD | <bytes len=4, hex=01 00 00 00> |
| 4 | 0x3707 | 31 | 0x3707 | PR_ATTACH_LONG_FILENAME (full name) | <bytes len=24, hex=69 00 6d 00 61 00 67 00 65 00 30 00 30 00 32 00> |
| 5 | 0x370A | 258 | 0x370A |  | <bytes len=9, hex=2a 86 48 86 f7 14 03 0a 04> |
| 6 | 0x370B | 3 | 0x370B |  | <bytes len=4, hex=ff ff ff ff> |
| 7 | 0x370E | 31 | 0x370E | PR_ATTACH_MIME_TAG (content type) | <bytes len=20, hex=69 00 6d 00 61 00 67 00 65 00 2f 00 6a 00 70 00> |
| 8 | 0x3710 | 3 | 0x3710 |  | <bytes len=4, hex=01 00 00 00> |
| 9 | 0x3712 | 31 | 0x3712 | PR_ATTACH_CONTENT_ID (CID) | <bytes len=60, hex=69 00 6d 00 61 00 67 00 65 00 30 00 30 00 32 00> |
| 10 | 0x3714 | 3 | 0x3714 | PR_ATTACH_FLAGS | <bytes len=4, hex=05 00 00 00> |