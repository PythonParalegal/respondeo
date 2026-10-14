# ─── LIBPFF RECORD SET INTROSPECTION ────────────────────────────────────────
# Run this on your Windows machine where libpff-python is installed.
# Usage: python introspect_libpff_records.py "path\to\any.pst"
#
# This digs into the record_sets on message and attachment objects to find
# the actual MAPI properties (filenames, email addresses, content types, etc.)
# that are NOT exposed as direct attributes.
#
# Output goes to docs/LIBPFF_RECORD_ENTRIES_DUMP.md
# ─────────────────────────────────────────────────────────────────────────────
import sys
import os

try:
    import pypff
except ImportError:
    print("ERROR: libpff-python (pypff) is not installed.")
    sys.exit(1)

# Known MAPI property tags we care about (for labeling)
KNOWN_TAGS = {
    # Attachment properties
    0x3701: "PR_ATTACH_DATA_BIN",
    0x3703: "PR_ATTACH_EXTENSION",
    0x3704: "PR_ATTACH_FILENAME (8.3 short name)",
    0x3707: "PR_ATTACH_LONG_FILENAME (full name)",
    0x370E: "PR_ATTACH_MIME_TAG (content type)",
    0x3712: "PR_ATTACH_CONTENT_ID (CID)",
    0x3714: "PR_ATTACH_FLAGS",
    0x0E20: "PR_ATTACH_SIZE",
    0x0E21: "PR_ATTACH_NUM",
    0x3001: "PR_DISPLAY_NAME",
    0x3705: "PR_ATTACH_METHOD",
    
    # Message properties
    0x001A: "PR_MESSAGE_CLASS",
    0x0037: "PR_SUBJECT",
    0x0039: "PR_CLIENT_SUBMIT_TIME",
    0x0042: "PR_SENT_REPRESENTING_NAME",
    0x0065: "PR_SENT_REPRESENTING_EMAIL_ADDRESS",
    0x0070: "PR_CONVERSATION_TOPIC",
    0x0071: "PR_CONVERSATION_INDEX",
    0x0075: "PR_RECEIVED_BY_EMAIL_ADDRESS",
    0x0076: "PR_RECEIVED_BY_NAME",
    0x0C1A: "PR_SENDER_NAME",
    0x0C1F: "PR_SENDER_EMAIL_ADDRESS",
    0x0E06: "PR_MESSAGE_DELIVERY_TIME",
    0x1000: "PR_BODY",
    0x1009: "PR_RTF_COMPRESSED",
    0x1013: "PR_BODY_HTML",
    0x0E07: "PR_MESSAGE_FLAGS",
    0x0017: "PR_IMPORTANCE",
    0x0036: "PR_SENSITIVITY",
    0x0E08: "PR_MESSAGE_SIZE",
    
    # Recipient properties  
    0x0C15: "PR_RECIPIENT_TYPE",
    0x3002: "PR_ADDRTYPE",
    0x3003: "PR_EMAIL_ADDRESS",
    0x39FE: "PR_SMTP_ADDRESS",
}


def safe_read_entry(entry):
    """Safely read a record entry's value."""
    try:
        data = entry.data
        if data is None:
            return "<None>"
        if isinstance(data, bytes):
            # Try to decode as UTF-16-LE first (common for MAPI strings)
            if len(data) >= 2 and data[-2:] == b'\x00\x00':
                try:
                    decoded = data.decode('utf-16-le').rstrip('\x00')
                    if decoded and all(c.isprintable() or c in '\r\n\t' for c in decoded):
                        return f'"{decoded}"' if len(decoded) < 200 else f'"{decoded[:100]}..." (len={len(decoded)})'
                except UnicodeDecodeError:
                    pass
            # Try UTF-8
            try:
                decoded = data.decode('utf-8', errors='strict').rstrip('\x00')
                if decoded and all(c.isprintable() or c in '\r\n\t' for c in decoded):
                    return f'"{decoded}"' if len(decoded) < 200 else f'"{decoded[:100]}..." (len={len(decoded)})'
            except UnicodeDecodeError:
                pass
            # Binary — show hex preview
            hex_preview = data[:16].hex(' ')
            return f"<bytes len={len(data)}, hex={hex_preview}>"
        return repr(data)
    except Exception as e:
        return f"<ERROR: {e}>"


def dump_record_sets(obj, label, out_lines):
    """Dump all record set entries for an object."""
    out_lines.append(f"\n## {label}\n")
    
    num_rs = obj.number_of_record_sets
    out_lines.append(f"**Record sets:** {num_rs}\n")
    
    for rs_idx in range(num_rs):
        rs = obj.get_record_set(rs_idx)
        num_entries = rs.number_of_entries
        out_lines.append(f"### Record Set {rs_idx} ({num_entries} entries)\n")
        out_lines.append("| # | Entry Type | Value Type | Tag (hex) | Known Name | Value |")
        out_lines.append("|---|-----------|------------|-----------|------------|-------|")
        
        for e_idx in range(num_entries):
            try:
                entry = rs.get_entry(e_idx)
                entry_type = getattr(entry, 'entry_type', '?')
                value_type = getattr(entry, 'value_type', '?')
                
                # Format tag as hex
                tag_hex = f"0x{entry_type:04X}" if isinstance(entry_type, int) else str(entry_type)
                
                # Look up known name
                tag_int = entry_type if isinstance(entry_type, int) else 0
                known = KNOWN_TAGS.get(tag_int, "")
                
                # Read value
                value = safe_read_entry(entry)
                # Escape pipes for markdown
                value = str(value).replace("|", "\\|")
                
                out_lines.append(f"| {e_idx} | {tag_hex} | {value_type} | {tag_hex} | {known} | {value} |")
            except Exception as e:
                out_lines.append(f"| {e_idx} | ? | ? | ? | ? | ERROR: {e} |")


def find_message_with_attachments(root):
    """Walk PST to find a message with attachments."""
    def _search(folder):
        num_msg = folder.number_of_sub_messages
        getter = getattr(folder, 'get_sub_message', None)
        if num_msg > 0 and getter:
            for i in range(min(num_msg, 20)):
                try:
                    msg = getter(i)
                    if msg and msg.number_of_attachments > 0:
                        return msg
                except Exception:
                    continue
        
        for i in range(folder.number_of_sub_folders):
            try:
                sub = folder.get_sub_folder(i)
                result = _search(sub)
                if result:
                    return result
            except Exception:
                continue
        return None
    
    return _search(root)


def find_message_without_attachments(root):
    """Walk PST to find a message WITHOUT attachments."""
    def _search(folder):
        num_msg = folder.number_of_sub_messages
        getter = getattr(folder, 'get_sub_message', None)
        if num_msg > 0 and getter:
            for i in range(min(num_msg, 20)):
                try:
                    msg = getter(i)
                    if msg and msg.number_of_attachments == 0:
                        return msg
                except Exception:
                    continue
        
        for i in range(folder.number_of_sub_folders):
            try:
                sub = folder.get_sub_folder(i)
                result = _search(sub)
                if result:
                    return result
            except Exception:
                continue
        return None
    
    return _search(root)


def main():
    if len(sys.argv) < 2:
        print("Usage: python introspect_libpff_records.py <path_to_pst>")
        sys.exit(1)
    
    pst_path = sys.argv[1]
    if not os.path.exists(pst_path):
        print(f"ERROR: File not found: {pst_path}")
        sys.exit(1)
    
    out_lines = [
        "# libpff-python — MAPI Record Set Entries Dump\n",
        f"**Source PST:** `{os.path.basename(pst_path)}`\n",
        f"**Python:** `{sys.version}`\n",
        "---\n",
        "This dump shows the MAPI properties stored in record_sets on message and",
        "attachment objects. These are the ONLY way to access filenames, email",
        "addresses, content types, and other metadata that are NOT exposed as",
        "direct Python attributes on pypff objects.\n",
    ]
    
    # Also dump record_entry object attributes so we know the API
    out_lines.append("\n## record_entry Object Attributes\n")
    out_lines.append("(Dumped from first available entry to document the API)\n")
    
    pst = pypff.file()
    pst.open(pst_path)
    root = pst.get_root_folder()
    
    # Find a message with attachments
    msg = find_message_with_attachments(root)
    
    if msg:
        # Dump record_entry attributes from first message entry
        try:
            rs0 = msg.get_record_set(0)
            if rs0.number_of_entries > 0:
                sample_entry = rs0.get_entry(0)
                entry_attrs = sorted([a for a in dir(sample_entry) if not a.startswith('_')])
                out_lines.append("| Attribute | Type | Value |")
                out_lines.append("|-----------|------|-------|")
                for attr in entry_attrs:
                    try:
                        val = getattr(sample_entry, attr)
                        vtype = type(val).__name__
                        if callable(val):
                            vtype = "method"
                            val = f"{val.__doc__[:80] if val.__doc__ else 'no doc'}"
                        else:
                            val = repr(val)[:100]
                    except Exception as e:
                        vtype = "?"
                        val = f"ERROR: {e}"
                    val = str(val).replace("|", "\\|")
                    out_lines.append(f"| `{attr}` | {vtype} | {val} |")
        except Exception as e:
            out_lines.append(f"\nERROR dumping record_entry attributes: {e}\n")
        
        out_lines.append(f"\n---\n")
        out_lines.append(f"\n**Sample message subject:** `{msg.subject}`\n")
        out_lines.append(f"**Attachment count:** {msg.number_of_attachments}\n")
        
        # Dump message record sets
        dump_record_sets(msg, f"Message Record Sets — \"{msg.subject[:60]}\"", out_lines)
        
        # Dump attachment record sets (all attachments)
        for att_idx in range(msg.number_of_attachments):
            att = msg.get_attachment(att_idx)
            dump_record_sets(att, f"Attachment {att_idx} Record Sets (size={att.size} bytes)", out_lines)
    else:
        out_lines.append("\n**No messages with attachments found.**\n")
    
    # Also dump a second message if available (for comparison)
    msg2 = find_message_without_attachments(root)
    if msg2:
        dump_record_sets(msg2, f"Message (no attachments) — \"{msg2.subject[:60]}\" (for comparison)", out_lines)
    
    pst.close()
    
    # Write output
    os.makedirs("docs", exist_ok=True)
    output_path = os.path.join("docs", "LIBPFF_RECORD_ENTRIES_DUMP.md")
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(out_lines))
    
    print(f"\nDone! Output written to: {output_path}")
    if msg:
        print(f"  - Message: \"{msg.subject[:60]}\" ({msg.number_of_attachments} attachments)")
        print(f"  - Message record entries: {msg.number_of_entries}")
        for i in range(msg.number_of_attachments):
            att = msg.get_attachment(i)
            print(f"  - Attachment {i}: {att.number_of_entries} record entries, {att.size} bytes")
    print(f"\nThis will show us the MAPI properties (filenames, MIME types, etc.)")
    print(f"that we need to access via record_sets.")


if __name__ == '__main__':
    main()
