"""
Standalone PST extraction worker — invoked via subprocess.Popen.

Runs libpff extraction in a clean Python process (no Streamlit, no COM).
This avoids the multiprocessing.spawn issue where Windows re-imports the
Streamlit entry point, polluting the subprocess with ScriptRunContext
warnings and causing libpff's C library to hang.

Usage:
    python _pst_worker.py <pst_path> <output_dir> <result_json_path> [log_path]
"""
import sys
import os
import json
import logging

# Ensure project root is on the path so container_exploder can be imported
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from container_exploder import explode_pst_libpff


def main():
    if len(sys.argv) < 4:
        print("Usage: python _pst_worker.py <pst_path> <output_dir> <result_json>  [log_path]",
              file=sys.stderr)
        sys.exit(2)

    pst_path = sys.argv[1]
    output_dir = sys.argv[2]
    result_json_path = sys.argv[3]
    log_path = sys.argv[4] if len(sys.argv) > 4 else None

    # Set up logging
    logger = logging.getLogger("ProcessorLogger")
    logger.setLevel(logging.INFO)
    if log_path:
        handler = logging.FileHandler(log_path)
    else:
        handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter(
        '%(asctime)s - %(levelname)s - %(message)s'
    ))
    logger.addHandler(handler)

    try:
        result = explode_pst_libpff(pst_path, output_dir)
        output = {'status': 'OK', 'payload': result}
    except Exception as e:
        logger.error("PST extraction failed: %s", e)
        output = {'status': 'ERROR', 'payload': str(e)}

    with open(result_json_path, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=True)


if __name__ == '__main__':
    main()
