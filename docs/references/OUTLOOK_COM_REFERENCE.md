# Outlook COM (win32com) API Reference — eDiscovery Platform Usage

**Last updated:** 2026-03-18  
**Applies to:** `container_exploder.py` (`process_msg_batch`, `_explode_pst_com`, `_walk_pst_folder_com`)  
**MSDN root:** https://learn.microsoft.com/en-us/office/vba/api/overview/outlook

---

## Initialization

```python
import win32com.client
import pythoncom

# MUST call CoInitialize in every thread that uses COM
pythoncom.CoInitialize()
try:
    outlook = win32com.client.Dispatch("Outlook.Application").GetNamespace("MAPI")
    # ... use outlook ...
finally:
    pythoncom.CoUninitialize()
```

**Critical threading rule:** COM is apartment-threaded. `CoInitialize()` / `CoUninitialize()` must be called in every thread that uses COM objects. Passing COM objects across threads will crash. Our `process_msg_batch` initializes COM once per batch call.

---

## Opening Files

### MSG Files (standalone)
```python
msg = outlook.OpenSharedItem(r"C:\path\to\file.msg")
```

**Constraints:**
- Path must be absolute.
- Path must NOT have the `\\?\` extended-length prefix — COM APIs reject it.
- Path length must be ≤ 260 chars (Windows MAX_PATH). For longer paths, our code copies to a temp location first.

### PST Files (archive stores)
```python
outlook.AddStore(r"C:\path\to\archive.pst")
# Find the newly added store in outlook.Folders
# ... process ...
outlook.RemoveStore(folder_object)  # Clean up when done
```

**Constraints:** Same path restrictions as MSG. AddStore makes the PST visible in the user's Outlook profile — always RemoveStore after processing.

---

## MailItem Object (Message)

Obtained via `outlook.OpenSharedItem(path)` for MSG files, or by iterating folder items for PST.

### Properties We Use

| Property | Type | Notes |
|----------|------|-------|
| `Subject` | `str` | Email subject line. Can be `None` or empty. |
| `SenderName` | `str` | Display name of sender. |
| `SenderEmailAddress` | `str` | Email address (may be Exchange DN format like `/o=ExchangeLabs/...`). |
| `To` | `str` | Semicolon-separated display names of To recipients. |
| `CC` | `str` | Semicolon-separated CC recipients. |
| `BCC` | `str` | Usually empty (BCC stripped on receipt). |
| `SentOn` | `datetime` | When the message was sent. Can be `datetime(4501, 1, 1)` for unsent items — treat as None. |
| `ReceivedTime` | `datetime` | When received. |
| `Body` | `str` | Plain text body. |
| `HTMLBody` | `str` | HTML body. May contain CID image references. |
| `Attachments` | `Attachments` collection | 1-indexed. See below. |
| `Attachments.Count` | `int` | Number of attachments. |
| `Class` | `int` | Object class. `43` = olMail. Use to skip non-mail items (calendar=26, contact=40, task=48). |
| `ConversationIndex` | `str` | Hex-encoded threading index. |
| `ConversationTopic` | `str` | Thread topic (usually = Subject minus Re:/Fwd:). |
| `Importance` | `int` | 0=Low, 1=Normal, 2=High. |
| `Sensitivity` | `int` | 0=Normal, 1=Personal, 2=Private, 3=Confidential. |
| `MessageClass` | `str` | e.g., `'IPM.Note'` for email. |

### Methods

| Method | Notes |
|--------|-------|
| `SaveAs(path, format)` | Save to disk. Format `3` = olMSG. Format `0` = olTXT. |
| `Close(action)` | Close the item. Action `1` = olDiscard (don't save changes). Always use this. |

---

## Attachment Object

Obtained via `msg.Attachments.Item(i)` — **1-indexed** (COM convention).

### Properties

| Property | Type | Notes |
|----------|------|-------|
| `FileName` | `str` | The attachment filename. **Usually reliable** — this is the display name Outlook shows. Can be empty for embedded items. |
| `DisplayName` | `str` | Sometimes different from FileName. Less reliable for file-type attachments. |
| `Type` | `int` | Attachment type constant (see table below). |
| `Size` | `int` | Size in bytes. |
| `Position` | `int` | Character position in RTF body where attachment is embedded. `-1` if not inline. |

### Attachment Type Constants

| Value | Constant | Meaning |
|-------|----------|---------|
| 1 | olByValue | File attachment (most common). |
| 5 | olEmbeddedItem | Embedded message (MSG within MSG). Our code appends `.msg` if missing. |
| 6 | olOLE | OLE object. Rare. |

### Methods

| Method | Notes |
|--------|-------|
| `SaveAsFile(path)` | Save attachment payload to disk. **Always use this** — reading the raw bytes via PropertyAccessor is unreliable. |

### MAPI Property Access (Advanced)

For properties not exposed directly, use `PropertyAccessor`:

```python
pa = attachment.PropertyAccessor
value = pa.GetProperty("http://schemas.microsoft.com/mapi/proptag/0x37140003")
```

**Properties we access:**
| Tag | Name | Type | Use |
|-----|------|------|-----|
| `0x37140003` | PR_ATTACH_FLAGS | int | Bit 4 (mask `& 4`) = ATT_MHTML_REF → inline CID embed. We use this to skip signature images. |

**Caveat:** PropertyAccessor is not available on all attachment types and can throw. Always wrap in try/except.

---

## Folder Navigation (PST Processing)

```python
# After AddStore, find the PST root:
for i in range(1, outlook.Folders.Count + 1):
    folder = outlook.Folders.Item(i)
    # Check if this is our newly added PST store
```

### Folder Properties

| Property | Type | Notes |
|----------|------|-------|
| `Name` | `str` | Folder display name. |
| `Items` | `Items` collection | Messages in this folder. 1-indexed. |
| `Items.Count` | `int` | Number of items. |
| `Folders` | `Folders` collection | Subfolders. 1-indexed. |
| `Folders.Count` | `int` | Number of subfolders. |

### Recursive Traversal Pattern

```python
def walk_folder(folder, depth=0):
    for i in range(1, folder.Items.Count + 1):
        item = folder.Items.Item(i)
        if hasattr(item, 'SaveAs'):  # Skip non-mail items
            process(item)
        del item  # Release COM reference immediately
    
    for i in range(1, folder.Folders.Count + 1):
        subfolder = folder.Folders.Item(i)
        walk_folder(subfolder, depth + 1)
```

**Critical:** Always `del` COM objects when done. COM reference counting is manual — Python's GC is not reliable for COM release. Failing to release can cause file locks on the PST.

---

## Known Gotchas — Things That Have Bitten Us

### 1. `\\?\` prefix causes COM to reject paths
Windows extended-length paths (`\\?\C:\very\long\path`) are valid for Win32 file APIs but NOT for COM methods like `OpenSharedItem` and `AddStore`. Always strip the prefix before passing to COM.

### 2. 1-indexed collections
ALL Outlook COM collections are 1-indexed. `Attachments.Item(0)` will throw. Loop: `for i in range(1, collection.Count + 1)`.

### 3. MAX_PATH (260 chars) for COM paths
Unlike Win32 APIs, COM does not support extended-length paths. For MSG files with paths > 240 chars, copy to a temp directory first, open the temp copy, then clean up.

### 4. SentOn returns year 4501 for unsent items
Items that were never sent (drafts, meeting requests) have `SentOn = datetime(4501, 1, 1, 0, 0)`. Always check for this sentinel and treat as None.

### 5. SenderEmailAddress may be Exchange DN
For internal Exchange messages, `SenderEmailAddress` returns a Distinguished Name like `/o=ExchangeLabs/ou=Exchange Administrative Group/cn=Recipients/cn=...` instead of an SMTP address. To get the SMTP address, use:
```python
sender = msg.Sender
if sender:
    smtp = sender.GetExchangeUser()
    if smtp:
        email_addr = smtp.PrimarySmtpAddress
```
This is fragile and may not work for all scenarios. Our current code uses `SenderEmailAddress` as-is.

### 6. Embedded MSG attachments (Type 5) may lack `.msg` extension
When an email is attached to another email, Outlook stores it as an embedded item (Type 5) whose `FileName` may not end in `.msg`. Our code explicitly appends `.msg` for Type 5 attachments:
```python
if attachment.Type == 5 and not orig_filename.lower().endswith('.msg'):
    orig_filename += ".msg"
```

### 7. CID inline images show up in Attachments collection
Outlook exposes ALL attachments including inline CID images (signature logos, decorative images) through `msg.Attachments`. These are not "real" attachments the user intended to send. We use PR_ATTACH_FLAGS (bit 4) to detect and skip these.

### 8. COM apartment threading
COM objects created in one thread cannot be used in another. Each thread must call `CoInitialize()` before any COM use and `CoUninitialize()` after. Our batch processor handles this.

### 9. File locks and cleanup
`OpenSharedItem` and `AddStore` may hold file locks. Always `msg.Close(1)` and `del msg` when done. For PSTs, always `RemoveStore`. Failing to clean up can prevent the PST from being opened by other processes.

### 10. Items collection can include non-mail items
PST folders can contain calendar entries (Class 26), contacts (Class 40), tasks (Class 48), and other item types. Check `hasattr(item, 'SaveAs')` or `item.Class == 43` before treating as a mail item.
