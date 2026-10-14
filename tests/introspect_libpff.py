# ─── LIBPFF INTROSPECTION SCRIPT ────────────────────────────────────────────
# Run this on your Windows machine where libpff-python is installed.
# Usage: python introspect_libpff.py "path\to\any.pst"
#
# This dumps every attribute, method, and property on the key objects
# (file, folder, message, attachment) so we can build an authoritative
# API reference. Output goes to docs/LIBPFF_INTROSPECTION_DUMP.md
# ─────────────────────────────────────────────────────────────────────────────
import sys
import os
import inspect

try:
    import pypff
except ImportError:
    print("ERROR: libpff-python (pypff) is not installed.")
    print("Install with: pip install libpff-python")
    sys.exit(1)


def safe_getattr(obj, attr):
    """Try to read an attribute value, catching any errors."""
    try:
        val = getattr(obj, attr)
        if callable(val) and not isinstance(val, property):
            return f"<method: {val.__doc__[:120] if val.__doc__ else 'no docstring'}>"
        if isinstance(val, bytes):
            return f"<bytes, len={len(val)}>"
        if isinstance(val, str) and len(val) > 200:
            return f"<str, len={len(val)}, preview={val[:80]!r}...>"
        return repr(val)
    except Exception as e:
        return f"<ERROR: {type(e).__name__}: {e}>"


def dump_object(obj, label, out_lines, sample_values=True):
    """Dump all non-dunder attributes of an object."""
    out_lines.append(f"\n## {label}\n")
    out_lines.append(f"**Type:** `{type(obj).__name__}`\n")
    
    attrs = sorted([a for a in dir(obj) if not a.startswith('_')])
    
    out_lines.append(f"**Attribute count:** {len(attrs)}\n")
    out_lines.append("| Attribute | Type | Value/Signature |")
    out_lines.append("|-----------|------|-----------------|")
    
    for attr in attrs:
        try:
            raw = getattr(obj, attr)
            if callable(raw) and not isinstance(raw, property):
                attr_type = "method"
                if sample_values:
                    sig = ""
                    try:
                        sig = str(inspect.signature(raw))
                    except (ValueError, TypeError):
                        sig = "(…)"
                    doc = (raw.__doc__ or "no docstring").split('\n')[0][:100]
                    val_str = f"`{sig}` — {doc}"
                else:
                    val_str = "<method>"
            else:
                attr_type = type(raw).__name__
                if sample_values:
                    val_str = safe_getattr(obj, attr)
                    # Truncate long values for readability
                    if len(str(val_str)) > 150:
                        val_str = str(val_str)[:150] + "…"
                else:
                    val_str = f"<{attr_type}>"
        except Exception as e:
            attr_type = "?"
            val_str = f"<ERROR: {e}>"
        
        # Escape pipes for markdown table
        val_str = str(val_str).replace("|", "\\|")
        out_lines.append(f"| `{attr}` | {attr_type} | {val_str} |")


def main():
    if len(sys.argv) < 2:
        print("Usage: python introspect_libpff.py <path_to_pst>")
        sys.exit(1)
    
    pst_path = sys.argv[1]
    if not os.path.exists(pst_path):
        print(f"ERROR: File not found: {pst_path}")
        sys.exit(1)
    
    out_lines = [
        "# libpff-python (pypff) API Introspection Dump\n",
        f"**Source PST:** `{os.path.basename(pst_path)}`\n",
        f"**pypff version:** `{getattr(pypff, '__version__', 'unknown')}`\n",
        f"**Python:** `{sys.version}`\n",
        "---\n",
        "This is a machine-generated dump of all public attributes on key pypff objects.",
        "Use this to build `docs/references/LIBPFF_API_REFERENCE.md`.\n",
    ]
    
    # 1. Module-level attributes
    out_lines.append("\n## pypff Module\n")
    module_attrs = sorted([a for a in dir(pypff) if not a.startswith('_')])
    out_lines.append(f"**Public symbols:** {', '.join(f'`{a}`' for a in module_attrs)}\n")
    
    # 2. Open file
    pst = pypff.file()
    pst.open(pst_path)
    dump_object(pst, "pypff.file() — PST File Object", out_lines)
    
    # 3. Root folder
    root = pst.get_root_folder()
    dump_object(root, "Root Folder", out_lines)
    
    # 4. Walk to find a folder with messages
    msg = None
    att = None
    
    def find_message(folder, depth=0):
        nonlocal msg, att
        if msg is not None:
            return
        
        num_sub = folder.number_of_sub_messages if hasattr(folder, 'number_of_sub_messages') else 0
        # Try get_sub_message first (some builds), then get_message
        getter = getattr(folder, 'get_sub_message', None) or getattr(folder, 'get_message', None)
        
        if num_sub > 0 and getter:
            for i in range(min(num_sub, 5)):  # Check up to 5 messages
                try:
                    candidate = getter(i)
                    if candidate:
                        msg = candidate
                        # Look for one with attachments
                        num_att = getattr(msg, 'number_of_attachments', 0)
                        if num_att > 0:
                            att = msg.get_attachment(0)
                            return  # Found message WITH attachment — ideal
                except Exception:
                    continue
        
        # Recurse into subfolders
        num_folders = folder.number_of_sub_folders if hasattr(folder, 'number_of_sub_folders') else 0
        for i in range(num_folders):
            try:
                sub = folder.get_sub_folder(i)
                find_message(sub, depth + 1)
                if msg is not None:
                    return
            except Exception:
                continue
    
    find_message(root)
    
    # 5. Dump a sample subfolder (first non-root)
    try:
        first_sub = root.get_sub_folder(0)
        dump_object(first_sub, "Sample Subfolder", out_lines)
    except Exception as e:
        out_lines.append(f"\n## Sample Subfolder\n\n**ERROR:** {e}\n")
    
    # 6. Dump message
    if msg:
        dump_object(msg, "Sample Message (email)", out_lines)
    else:
        out_lines.append("\n## Sample Message\n\n**No messages found in PST.**\n")
    
    # 7. Dump attachment
    if att:
        dump_object(att, "Sample Attachment", out_lines)
    else:
        out_lines.append("\n## Sample Attachment\n\n**No attachments found in PST.**\n")
    
    # 8. Also dump a message WITHOUT attachments if we can find one
    def find_no_attach_msg(folder):
        num_sub = folder.number_of_sub_messages if hasattr(folder, 'number_of_sub_messages') else 0
        getter = getattr(folder, 'get_sub_message', None) or getattr(folder, 'get_message', None)
        if num_sub > 0 and getter:
            for i in range(min(num_sub, 20)):
                try:
                    candidate = getter(i)
                    if candidate and getattr(candidate, 'number_of_attachments', 0) == 0:
                        return candidate
                except Exception:
                    continue
        num_folders = folder.number_of_sub_folders if hasattr(folder, 'number_of_sub_folders') else 0
        for i in range(num_folders):
            try:
                sub = folder.get_sub_folder(i)
                result = find_no_attach_msg(sub)
                if result:
                    return result
            except Exception:
                continue
        return None
    
    no_att_msg = find_no_attach_msg(root)
    if no_att_msg:
        dump_object(no_att_msg, "Sample Message (no attachments — for comparison)", out_lines, sample_values=True)
    
    pst.close()
    
    # Write output
    os.makedirs("docs", exist_ok=True)
    output_path = os.path.join("docs", "LIBPFF_INTROSPECTION_DUMP.md")
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(out_lines))
    
    print(f"\nDone! Output written to: {output_path}")
    print(f"  - PST file object: {len([a for a in dir(pst) if not a.startswith('_')])} attributes")
    if msg:
        print(f"  - Message object: {len([a for a in dir(msg) if not a.startswith('_')])} attributes")
    if att:
        print(f"  - Attachment object: {len([a for a in dir(att) if not a.startswith('_')])} attributes")
    print(f"\nNext step: review the dump, then copy it into the project repo.")
    print(f"Both Claude (in chat) and Claude Code (in VSCode) will have it in context.")


if __name__ == '__main__':
    main()
