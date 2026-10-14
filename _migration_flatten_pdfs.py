"""
One-time migration: Re-flatten all processed PDFs in a case to strip
interactive elements (form fields, JS, embedded files) that were
preserved by the raw-copy processing pipeline before the flatten fix.

Usage:
    python _migration_flatten_pdfs.py "C:\\eDiscovery\\YourCase"

What it does:
    1. Scans {case_folder}/Processed/ for *.pdf files
    2. For each PDF, checks if it has interactive elements
    3. If yes: backs up to Processed/_pre_flatten_backup/, then flattens in-place
    4. Prints summary of how many files were flattened vs already clean
"""
import os
import sys
import shutil

# Add project root to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import universal_imager

def main():
    if len(sys.argv) < 2:
        print("Usage: python _migration_flatten_pdfs.py <case_folder_path>")
        sys.exit(1)

    case_folder = sys.argv[1]
    processed_dir = os.path.join(case_folder, "Processed")

    if not os.path.isdir(processed_dir):
        print(f"ERROR: Processed directory not found: {processed_dir}")
        sys.exit(1)

    backup_dir = os.path.join(processed_dir, "_pre_flatten_backup")

    pdf_files = [f for f in os.listdir(processed_dir)
                 if f.lower().endswith('.pdf') and os.path.isfile(os.path.join(processed_dir, f))]

    print(f"Found {len(pdf_files)} PDF files in {processed_dir}")

    flattened = 0
    clean = 0
    errors = 0

    for filename in sorted(pdf_files):
        filepath = os.path.join(processed_dir, filename)

        try:
            import fitz
            doc = fitz.open(filepath)
            needs_flatten = False

            catalog = doc.pdf_catalog()
            cat_dict = doc.xref_get_key(catalog, "AcroForm")
            if cat_dict[0] != 'null':
                needs_flatten = True

            if not needs_flatten:
                for page in doc:
                    if list(page.widgets()):
                        needs_flatten = True
                        break

            if not needs_flatten:
                for js_key in ("JavaScript", "JS", "OpenAction", "AA"):
                    val = doc.xref_get_key(catalog, js_key)
                    if val[0] != 'null':
                        needs_flatten = True
                        break

            if not needs_flatten:
                if doc.embfile_count() > 0:
                    needs_flatten = True

            doc.close()

            if not needs_flatten:
                clean += 1
                continue

            # Needs flattening — backup first
            if not os.path.exists(backup_dir):
                os.makedirs(backup_dir)

            backup_path = os.path.join(backup_dir, filename)
            shutil.copy2(filepath, backup_path)

            # Flatten in-place
            ok, err = universal_imager.flatten_pdf(filepath, filepath)
            if ok:
                flattened += 1
                print(f"  FLATTENED: {filename}")
            else:
                errors += 1
                print(f"  ERROR: {filename} — {err}")
                # Restore from backup
                shutil.copy2(backup_path, filepath)
                print(f"           Restored from backup")

        except Exception as e:
            errors += 1
            print(f"  ERROR: {filename} — {e}")

    print(f"\nSummary:")
    print(f"  Already clean: {clean}")
    print(f"  Flattened:     {flattened}")
    print(f"  Errors:        {errors}")
    print(f"  Total:         {len(pdf_files)}")
    if flattened > 0:
        print(f"\n  Backups saved to: {backup_dir}")
        print(f"  Delete the backup directory once you've verified the flattened files look correct.")

if __name__ == "__main__":
    main()
