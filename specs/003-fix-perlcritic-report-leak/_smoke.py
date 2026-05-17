"""Smoke test for spec 003 — verify no JSON report leak.

Run from anywhere; designed to be invoked inside the docker container
where perlcritic is installed:

    docker run --rm \\
        -v $(pwd)/specs/003-fix-perlcritic-report-leak/_smoke.py:/app/_smoke.py \\
        --entrypoint python lenchik8/simple_mcp:latest /app/_smoke.py

Or locally (perlcritic path may need shell=True wiring; see spec):

    python specs/003-fix-perlcritic-report-leak/_smoke.py
"""
import glob
import os
import sys
import tempfile

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, PROJECT_ROOT)

from tools.perlcritic import analyze_perl_critic

TMP = tempfile.gettempdir()
PATTERN = os.path.join(TMP, "perlcritic_report_*.json")


def count_residue():
    return len(glob.glob(PATTERN))


def main():
    before = count_residue()
    print(f"[setup] residue files in {TMP} before run: {before}")

    sample_code = "use strict;\nuse warnings;\nopen(FILE, $path);\n"
    print("[run]   calling analyze_perl_critic 5 times...")
    last = None
    for i in range(5):
        last = analyze_perl_critic(code=sample_code, filename=f"smoke_003_{i}.pl", severity=1)
    print("[run]   done")

    print("\n[check] response shape:")
    for key in ("path", "type", "issues", "count", "error", "report_file", "timestamp"):
        present = key in last
        value = f"<{len(last.get(key, []))} items>" if key == "issues" else last.get(key)
        print(f"  {'+' if present else '-'} {key}: {value}")

    after = count_residue()
    new_files = after - before
    print(f"\n[check] residue files after run: {after}  (delta: +{new_files})")

    ok = True
    if last.get("report_file") is not None:
        print("FAIL: report_file is not None")
        ok = False
    if new_files > 0:
        print(f"FAIL: {new_files} new perlcritic_report_*.json files created in tempdir")
        for f in glob.glob(PATTERN):
            print(f"  leaked: {f}")
        ok = False
    if last.get("error") and "perlcritic not found" in (last.get("error") or ""):
        print("WARN: perlcritic not on PATH for this run; cannot fully validate parse path")
    if "issues" not in last or not isinstance(last["issues"], list):
        print("FAIL: issues field missing or wrong type")
        ok = False

    print("\nRESULT:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
