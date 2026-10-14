# libpff-python (pypff) API Introspection Dump

**Source PST:** `sample.pst`

**pypff version:** `unknown`

**Python:** `3.11.9 (tags/v3.11.9:de54cf5, Apr  2 2024, 10:12:12) [MSC v.1938 64 bit (AMD64)]`

---

This is a machine-generated dump of all public attributes on key pypff objects.
Use this to build `docs/references/LIBPFF_API_REFERENCE.md`.


## pypff Module

**Public symbols:** `attachment`, `check_file_signature`, `check_file_signature_file_object`, `file`, `folder`, `get_version`, `item`, `items`, `message`, `open`, `open_file_object`, `record_entries`, `record_entry`, `record_set`, `record_sets`


## pypff.file() — PST File Object

**Type:** `file`

**Attribute count:** 25

| Attribute | Type | Value/Signature |
|-----------|------|-----------------|
| `ascii_codepage` | bytes | <bytes, len=6> |
| `close` | method | `(…)` — close() -> None |
| `content_type` | int | 112 |
| `encryption_type` | int | 1 |
| `get_ascii_codepage` | method | `(…)` — get_ascii_codepage() -> String |
| `get_content_type` | method | `(…)` — get_content_type() -> Integer or None |
| `get_encryption_type` | method | `(…)` — get_encryption_type() -> Integer or None |
| `get_message_store` | method | `(…)` — get_message_store() -> Object or None |
| `get_name_to_id_map` | method | `(…)` — get_name_to_id_map() -> Object or None |
| `get_number_of_orphan_items` | method | `(…)` — get_number_of_orphan_items() -> Integer or None |
| `get_orphan_item` | method | `(…)` — get_orphan_item(orphan_item_index) -> Object or None |
| `get_root_folder` | method | `(…)` — get_root_folder() -> Object or None |
| `get_root_item` | method | `(…)` — get_root_item() -> Object or None |
| `get_size` | method | `(…)` — get_size() -> Integer or None |
| `message_store` | folder | <pypff.folder object at 0x0000023C8BBEA5B0> |
| `name_to_id_map` | folder | <pypff.folder object at 0x0000023C8BBEA580> |
| `number_of_orphan_items` | int | 0 |
| `open` | method | `(…)` — open(filename, mode='r') -> None |
| `open_file_object` | method | `(…)` — open_file_object(file_object, mode='r') -> None |
| `orphan_items` | items | <pypff.items object at 0x0000023C8BBEA580> |
| `root_folder` | folder | <pypff.folder object at 0x0000023C8BBEA5B0> |
| `root_item` | folder | <pypff.folder object at 0x0000023C8BBEA580> |
| `set_ascii_codepage` | method | `(…)` — set_ascii_codepage(codepage) -> None |
| `signal_abort` | method | `(…)` — signal_abort() -> None |
| `size` | int | 10485760 |

## Root Folder

**Type:** `folder`

**Attribute count:** 22

| Attribute | Type | Value/Signature |
|-----------|------|-----------------|
| `get_identifier` | method | `(…)` — get_identifier() -> Integer or None |
| `get_name` | method | `(…)` — get_name() -> Unicode string or None |
| `get_number_of_entries` | method | `(…)` — get_number_of_entries() -> Integer or None |
| `get_number_of_record_sets` | method | `(…)` — get_number_of_record_sets() -> Integer or None |
| `get_number_of_sub_folders` | method | `(…)` — get_number_of_sub_folders() -> Integer |
| `get_number_of_sub_items` | method | `(…)` — get_number_of_sub_items() -> Integer or None |
| `get_number_of_sub_messages` | method | `(…)` — get_number_of_sub_messages() -> Integer |
| `get_record_set` | method | `(…)` — get_record_set(record_set_index) -> Object or None |
| `get_sub_folder` | method | `(…)` — get_sub_folder(sub_folder_index) -> Object or None |
| `get_sub_item` | method | `(…)` — get_sub_item(sub_item_index) -> Object or None |
| `get_sub_message` | method | `(…)` — get_sub_message(sub_message_index) -> Object or None |
| `identifier` | int | 290 |
| `name` | NoneType | None |
| `number_of_entries` | int | 4 |
| `number_of_record_sets` | int | 1 |
| `number_of_sub_folders` | int | 3 |
| `number_of_sub_items` | int | 3 |
| `number_of_sub_messages` | int | 0 |
| `record_sets` | _record_sets | <pypff._record_sets object at 0x0000023C8BBEA5E0> |
| `sub_folders` | items | <pypff.items object at 0x0000023C8BBEA580> |
| `sub_items` | items | <pypff.items object at 0x0000023C8BBEA5E0> |
| `sub_messages` | items | <pypff.items object at 0x0000023C8BBEA580> |

## Sample Subfolder

**Type:** `folder`

**Attribute count:** 22

| Attribute | Type | Value/Signature |
|-----------|------|-----------------|
| `get_identifier` | method | `(…)` — get_identifier() -> Integer or None |
| `get_name` | method | `(…)` — get_name() -> Unicode string or None |
| `get_number_of_entries` | method | `(…)` — get_number_of_entries() -> Integer or None |
| `get_number_of_record_sets` | method | `(…)` — get_number_of_record_sets() -> Integer or None |
| `get_number_of_sub_folders` | method | `(…)` — get_number_of_sub_folders() -> Integer |
| `get_number_of_sub_items` | method | `(…)` — get_number_of_sub_items() -> Integer or None |
| `get_number_of_sub_messages` | method | `(…)` — get_number_of_sub_messages() -> Integer |
| `get_record_set` | method | `(…)` — get_record_set(record_set_index) -> Object or None |
| `get_sub_folder` | method | `(…)` — get_sub_folder(sub_folder_index) -> Object or None |
| `get_sub_item` | method | `(…)` — get_sub_item(sub_item_index) -> Object or None |
| `get_sub_message` | method | `(…)` — get_sub_message(sub_message_index) -> Object or None |
| `identifier` | int | 8739 |
| `name` | str | 'SPAM Search Folder 2' |
| `number_of_entries` | int | 4 |
| `number_of_record_sets` | int | 1 |
| `number_of_sub_folders` | int | 0 |
| `number_of_sub_items` | int | 0 |
| `number_of_sub_messages` | int | 0 |
| `record_sets` | _record_sets | <pypff._record_sets object at 0x0000023C8BBEA4C0> |
| `sub_folders` | items | <pypff.items object at 0x0000023C8BBEA4F0> |
| `sub_items` | items | <pypff.items object at 0x0000023C8BBEA4C0> |
| `sub_messages` | items | <pypff.items object at 0x0000023C8BBEA4F0> |

## Sample Message (email)

**Type:** `message`

**Attribute count:** 42

| Attribute | Type | Value/Signature |
|-----------|------|-----------------|
| `attachments` | items | <pypff.items object at 0x0000023C8BBEA4F0> |
| `client_submit_time` | datetime | datetime.datetime(2020, 1, 15, 9, 0) |
| `conversation_topic` | str | 'Project update' |
| `creation_time` | datetime | datetime.datetime(2020, 1, 16, 8, 0) |
| `delivery_time` | datetime | datetime.datetime(2020, 1, 15, 9, 1) |
| `get_attachment` | method | `(…)` — get_attachment(attachment_index) -> Object or None |
| `get_client_submit_time` | method | `(…)` — get_client_submit_time() -> Datetime or None |
| `get_client_submit_time_as_integer` | method | `(…)` — get_client_submit_time_as_integer() -> Integer or None |
| `get_conversation_topic` | method | `(…)` — get_conversation_topic() -> Unicode string or None |
| `get_creation_time` | method | `(…)` — get_creation_time() -> Datetime or None |
| `get_creation_time_as_integer` | method | `(…)` — get_creation_time_as_integer() -> Integer or None |
| `get_delivery_time` | method | `(…)` — get_delivery_time() -> Datetime or None |
| `get_delivery_time_as_integer` | method | `(…)` — get_delivery_time_as_integer() -> Integer or None |
| `get_html_body` | method | `(…)` — get_html_body() -> String or None |
| `get_identifier` | method | `(…)` — get_identifier() -> Integer or None |
| `get_modification_time` | method | `(…)` — get_modification_time() -> Datetime or None |
| `get_modification_time_as_integer` | method | `(…)` — get_modification_time_as_integer() -> Integer or None |
| `get_number_of_attachments` | method | `(…)` — get_number_of_attachments() -> Integer |
| `get_number_of_entries` | method | `(…)` — get_number_of_entries() -> Integer or None |
| `get_number_of_record_sets` | method | `(…)` — get_number_of_record_sets() -> Integer or None |
| `get_number_of_sub_items` | method | `(…)` — get_number_of_sub_items() -> Integer or None |
| `get_plain_text_body` | method | `(…)` — get_plain_text_body() -> String or None |
| `get_record_set` | method | `(…)` — get_record_set(record_set_index) -> Object or None |
| `get_rtf_body` | method | `(…)` — get_rtf_body() -> String or None |
| `get_sender_name` | method | `(…)` — get_sender_name() -> Unicode string or None |
| `get_sub_item` | method | `(…)` — get_sub_item(sub_item_index) -> Object or None |
| `get_subject` | method | `(…)` — get_subject() -> Unicode string or -None |
| `get_transport_headers` | method | `(…)` — get_transport_headers() -> String or None |
| `html_body` | bytes | <bytes, len=8192> |
| `identifier` | int | 2097152 |
| `modification_time` | datetime | datetime.datetime(2020, 1, 15, 9, 1) |
| `number_of_attachments` | int | 2 |
| `number_of_entries` | int | 53 |
| `number_of_record_sets` | int | 1 |
| `number_of_sub_items` | int | 0 |
| `plain_text_body` | bytes | <bytes, len=1400> |
| `record_sets` | _record_sets | <pypff._record_sets object at 0x0000023C8BBEA460> |
| `rtf_body` | NoneType | None |
| `sender_name` | str | 'Jane Doe' |
| `sub_items` | items | <pypff.items object at 0x0000023C8BBEA460> |
| `subject` | str | 'Re: Project update' |
| `transport_headers` | str | <str, len=1024, preview='Return-Path: <jane@example.com>\r\nReceived: from mail.example.com'...> |

## Sample Attachment

**Type:** `attachment`

**Attribute count:** 16

| Attribute | Type | Value/Signature |
|-----------|------|-----------------|
| `get_identifier` | method | `(…)` — get_identifier() -> Integer or None |
| `get_number_of_entries` | method | `(…)` — get_number_of_entries() -> Integer or None |
| `get_number_of_record_sets` | method | `(…)` — get_number_of_record_sets() -> Integer or None |
| `get_number_of_sub_items` | method | `(…)` — get_number_of_sub_items() -> Integer or None |
| `get_record_set` | method | `(…)` — get_record_set(record_set_index) -> Object or None |
| `get_size` | method | `(…)` — get_size() -> Integer or None |
| `get_sub_item` | method | `(…)` — get_sub_item(sub_item_index) -> Object or None |
| `identifier` | int | 32805 |
| `number_of_entries` | int | 11 |
| `number_of_record_sets` | int | 1 |
| `number_of_sub_items` | int | 0 |
| `read_buffer` | method | `(…)` — read_buffer(size) -> String |
| `record_sets` | _record_sets | <pypff._record_sets object at 0x0000023C8BBEA580> |
| `seek_offset` | method | `(…)` — seek_offset(offset, whence) -> None |
| `size` | int | 24576 |
| `sub_items` | items | <pypff.items object at 0x0000023C8BBEA580> |