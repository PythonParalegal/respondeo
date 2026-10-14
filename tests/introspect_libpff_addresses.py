# ─── LIBPFF EMAIL ADDRESS INTROSPECTION ─────────────────────────────────────
# Run on your Windows machine: python introspect_libpff_addresses.py "path\to\any.pst"
#
# Dumps transport_headers + all address-related MAPI properties from several
# messages so we can determine the best strategy for extracting full SMTP
# email addresses for To/Cc/Bcc fields in synthesized EMLs.
#
# Output goes to docs/LIBPFF_ADDRESS_DUMP.md
# ─────────────────────────────────────────────────────────────────────────────
import sys
import os
import re

try:
    import pypff
except ImportError:
    print("ERROR: libpff-python (pypff) is not installed.")
    sys.exit(1)

# Address-related MAPI tags
ADDRESS_TAGS = {
    0x001A: "PR_MESSAGE_CLASS",
    0x0037: "PR_SUBJECT",
    0x003B: "PR_SENT_REPRESENTING_SEARCH_KEY",
    0x0040: "PR_RECEIVED_BY_ENTRYID_OR_ADDR",
    0x0042: "PR_SENT_REPRESENTING_NAME",
    0x0044: "PR_RCVD_REPRESENTING_ENTRYID",
    0x0051: "PR_RECEIVED_BY_SEARCH_KEY",
    0x0052: "PR_RCVD_REPRESENTING_SEARCH_KEY",
    0x0064: "PR_SENT_REPRESENTING_ADDRTYPE",
    0x0065: "PR_SENT_REPRESENTING_EMAIL_ADDRESS",
    0x0070: "PR_CONVERSATION_TOPIC",
    0x0075: "PR_RECEIVED_BY_ADDRTYPE",
    0x0076: "PR_RECEIVED_BY_EMAIL_ADDRESS",
    0x0077: "PR_RCVD_REPRESENTING_ADDRTYPE",
    0x0078: "PR_RCVD_REPRESENTING_EMAIL_ADDRESS",
    0x007D: "PR_TRANSPORT_MESSAGE_HEADERS",
    0x0C19: "PR_SENDER_ENTRYID",
    0x0C1A: "PR_SENDER_NAME",
    0x0C1D: "PR_SENDER_SEARCH_KEY",
    0x0C1E: "PR_SENDER_ADDRTYPE",
    0x0C1F: "PR_SENDER_EMAIL_ADDRESS",
    0x0E04: "PR_DISPLAY_TO",
    0x0E03: "PR_DISPLAY_CC",
    0x0E02: "PR_DISPLAY_BCC",
    0x3FFA: "PR_LAST_MODIFIER_NAME",
    0x5D01: "PR_SENDER_SMTP_ADDRESS",
    0x5D02: "PR_SENT_REPRESENTING_SMTP_ADDRESS",
    0x5D05: "PR_RECEIVED_BY_SMTP_ADDRESS",
    0x5D07: "PR_RCVD_REPRESENTING_SMTP_ADDRESS",
}


def safe_decode(data):
    """Try to decode bytes to string."""
    if data is None:
        return "<None>"
    if isinstance(data, str):
        return data
    if isinstance(data, bytes):
        # Try UTF-16-LE first (MAPI PT_UNICODE)
        if len(data) >= 2:
            try:
                decoded = data.decode('utf-16-le').rstrip('\x00')
                if decoded and all(c.isprintable() or c in '\r\n\t ' for c in decoded):
                    return decoded
            except UnicodeDecodeError:
                pass
        # Try UTF-8
        try:
            decoded = data.decode('utf-8', errors='replace').rstrip('\x00')
            return decoded
        except Exception:
            pass
        return f"<bytes len={len(data)}, hex={data[:20].hex(' ')}>"
    return repr(data)


def dump_message_addresses(msg, out_lines, msg_num):
    """Dump all address-related info from a single message."""
    out_lines.append(f"\n## Message {msg_num}: `{msg.subject}`\n")
    out_lines.append(f"- **sender_name:** `{msg.sender_name}`")
    out_lines.append(f"- **client_submit_time:** `{msg.client_submit_time}`")
    out_lines.append(f"- **delivery_time:** `{msg.delivery_time}`")
    out_lines.append(f"- **number_of_attachments:** `{msg.number_of_attachments}`")
    
    # 1. Direct attribute: transport_headers
    out_lines.append(f"\n### Transport Headers (raw)\n")
    th = msg.transport_headers
    if th:
        out_lines.append("```")
        out_lines.append(th)
        out_lines.append("```")
    else:
        out_lines.append("**None — no transport headers available.**")
    
    # 2. Parse transport headers for address fields specifically
    if th:
        out_lines.append(f"\n### Parsed Address Headers\n")
        import email as _email
        from email import policy as _policy
        try:
            parsed = _email.message_from_string(th, policy=_policy.default)
            for hdr in ['From', 'To', 'Cc', 'Bcc', 'Reply-To', 'Sender',
                       'Return-Path', 'X-Sender', 'Delivered-To',
                       'X-MS-Exchange-Organization-AuthAs',
                       'X-MS-Exchange-Organization-AuthSource']:
                val = parsed.get(hdr)
                if val:
                    out_lines.append(f"- **{hdr}:** `{val}`")
            
            # Also check for any header containing @ (might reveal addresses)
            at_headers = []
            for key in parsed.keys():
                val = str(parsed.get(key, ''))
                if '@' in val and key not in ['From', 'To', 'Cc', 'Bcc', 'Reply-To', 
                                                'Sender', 'Return-Path']:
                    at_headers.append(f"  - **{key}:** `{val[:200]}`")
            if at_headers:
                out_lines.append(f"\n**Other headers containing @:**")
                out_lines.extend(at_headers)
        except Exception as e:
            out_lines.append(f"**Parse error:** {e}")
    
    # 3. Address-related MAPI record set entries
    out_lines.append(f"\n### MAPI Record Set — Address Properties\n")
    out_lines.append("| Tag | Known Name | Value Type | Decoded Value |")
    out_lines.append("|-----|-----------|------------|---------------|")
    
    for rs_idx in range(msg.number_of_record_sets):
        rs = msg.get_record_set(rs_idx)
        for e_idx in range(rs.number_of_entries):
            entry = rs.get_entry(e_idx)
            tag = entry.entry_type
            
            # Only dump address-related tags
            if tag not in ADDRESS_TAGS:
                # Also catch any tag we don't know about that contains @ in its value
                try:
                    test_val = safe_decode(entry.data)
                    if '@' not in test_val and tag not in ADDRESS_TAGS:
                        continue
                except Exception:
                    continue
            
            known = ADDRESS_TAGS.get(tag, f"UNKNOWN (0x{tag:04X})")
            vtype = entry.value_type
            
            # Decode based on value type
            if vtype == 31:  # PT_UNICODE
                try:
                    val = entry.data_as_string
                except Exception:
                    val = safe_decode(entry.data)
            elif vtype == 258:  # PT_BINARY
                val = safe_decode(entry.data)
            elif vtype == 3:  # PT_LONG
                try:
                    val = str(entry.data_as_integer)
                except Exception:
                    val = safe_decode(entry.data)
            elif vtype == 64:  # PT_SYSTIME
                try:
                    val = str(entry.data_as_datetime)
                except Exception:
                    val = safe_decode(entry.data)
            else:
                val = safe_decode(entry.data)
            
            # Truncate very long values
            val_str = str(val).replace("|", "\\|")
            if len(val_str) > 200:
                val_str = val_str[:200] + "..."
            
            out_lines.append(f"| 0x{tag:04X} | {known} | {vtype} | {val_str} |")


def collect_messages(root, target_count=5):
    """Collect a diverse set of messages: with attachments, without, different senders."""
    messages = []
    senders_seen = set()
    
    def _search(folder):
        if len(messages) >= target_count:
            return
        for i in range(folder.number_of_sub_messages):
            if len(messages) >= target_count:
                return
            try:
                msg = folder.get_sub_message(i)
                sender = msg.sender_name or 'unknown'
                # Try to get diverse messages
                has_att = msg.number_of_attachments > 0
                is_new_sender = sender.lower() not in senders_seen
                
                if len(messages) < 2:
                    # First two: just grab them
                    messages.append(msg)
                    senders_seen.add(sender.lower())
                elif is_new_sender or (has_att and len([m for m in messages if m.number_of_attachments > 0]) < 2):
                    messages.append(msg)
                    senders_seen.add(sender.lower())
            except Exception:
                continue
        
        for i in range(folder.number_of_sub_folders):
            if len(messages) >= target_count:
                return
            try:
                _search(folder.get_sub_folder(i))
            except Exception:
                continue
    
    _search(root)
    return messages


def main():
    if len(sys.argv) < 2:
        print("Usage: python introspect_libpff_addresses.py <path_to_pst>")
        sys.exit(1)
    
    pst_path = sys.argv[1]
    if not os.path.exists(pst_path):
        print(f"ERROR: File not found: {pst_path}")
        sys.exit(1)
    
    out_lines = [
        "# libpff-python — Email Address Extraction Dump\n",
        f"**Source PST:** `{os.path.basename(pst_path)}`\n",
        f"**Python:** `{sys.version}`\n",
        "---\n",
        "This dump shows transport_headers and MAPI address properties from several",
        "messages to determine the best strategy for extracting full SMTP email",
        "addresses for To/Cc/Bcc fields.\n",
    ]
    
    pst = pypff.file()
    pst.open(pst_path)
    root = pst.get_root_folder()
    
    messages = collect_messages(root, target_count=5)
    
    out_lines.append(f"**Messages sampled:** {len(messages)}\n")
    
    for i, msg in enumerate(messages):
        dump_message_addresses(msg, out_lines, i + 1)
    
    pst.close()
    
    # Write output
    os.makedirs("docs", exist_ok=True)
    output_path = os.path.join("docs", "LIBPFF_ADDRESS_DUMP.md")
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(out_lines))
    
    print(f"\nDone! Output written to: {output_path}")
    print(f"Sampled {len(messages)} messages:")
    for i, msg in enumerate(messages):
        th = msg.transport_headers
        has_to_addr = '@' in (th or '') if th else False
        print(f"  {i+1}. \"{msg.subject[:50]}\" — sender: {msg.sender_name}, "
              f"att: {msg.number_of_attachments}, "
              f"transport_headers: {'yes' if th else 'NO'}, "
              f"has @: {has_to_addr}")


if __name__ == '__main__':
    main()
