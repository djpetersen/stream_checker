#!/usr/bin/env python3
"""
Run 20-stream Phase 3 verification using the real CLI (stream_checker.py --phase 3).
Report: pass count, fail count, and for failures the error string plus download vs load_raw.
Also confirm no new ~/Library/Logs/DiagnosticReports/*Python*.ips were created during the run.
"""

import json
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CLI = PROJECT_ROOT / "stream_checker.py"
DIAG_REPORTS_DIR = Path.home() / "Library" / "Logs" / "DiagnosticReports"


def list_python_ips():
    """Return set of Python*.ips filenames in DiagnosticReports (macOS)."""
    if not DIAG_REPORTS_DIR.is_dir():
        return set()
    return {p.name for p in DIAG_REPORTS_DIR.glob("Python*.ips")}

# 20 diverse URLs: the 2 we used (fip-hifi.aac, groovesalad) + 18 from recent tests
STREAMS = [
    "https://icecast.radiofrance.fr/fip-hifi.aac",
    "http://ice2.somafm.com/groovesalad-128-mp3",
    "http://streams.radiomast.io/ref-128k-mp3-stereo",
    "http://streams.radiomast.io/ref-32k-mp3-mono",
    "http://streams.radiomast.io/ref-128k-aaclc-stereo",
    "http://streams.radiomast.io/ref-64k-heaacv1-stereo",
    "http://streams.radiomast.io/ref-64k-ogg-vorbis-stereo",
    "http://streams.radiomast.io/ref-64k-ogg-opus-stereo",
    "http://icecast.omroep.nl/radio1-bb-mp3",
    "http://icecast.omroep.nl/radio2-bb-mp3",
    "http://icecast.omroep.nl/3fm-bb-mp3",
    "http://ice1.somafm.com/groovesalad-128-mp3",
    "http://ice1.somafm.com/dronezone-128-mp3",
    "http://ice1.somafm.com/deepspaceone-128-mp3",
    "http://ice2.somafm.com/beatblender-128-mp3",
    "https://icecast.radiofrance.fr/fip-hifi.mp3",
    "https://icecast.radiofrance.fr/franceinter-hifi.aac",
    "http://streams.radiomast.io/ref-96k-mp3-stereo",
    "http://ice1.somafm.com/defcon-128-mp3",
    "http://ice1.somafm.com/fluid-128-mp3",
]


def main():
    if not CLI.exists():
        print(f"CLI not found: {CLI}", file=sys.stderr)
        sys.exit(1)

    ips_before = list_python_ips()
    passed = 0
    failed = 0
    failures = []

    for i, url in enumerate(STREAMS, 1):
        sys.stdout.write(f"[{i}/{len(STREAMS)}] {url[:60]}... ")
        sys.stdout.flush()
        try:
            result = subprocess.run(
                [sys.executable, str(CLI), "--url", url, "--phase", "3", "--output-format", "json"],
                cwd=str(PROJECT_ROOT),
                capture_output=True,
                timeout=120,
                env={**__import__("os").environ, "PYTHONPATH": str(PROJECT_ROOT)},
            )
            out = result.stdout.decode("utf-8", errors="replace")
            err = result.stderr.decode("utf-8", errors="replace")
            # JSON may be multi-line; try parsing entire stdout as JSON first
            data = None
            try:
                data = json.loads(out.strip())
            except json.JSONDecodeError:
                # Try finding JSON block (between first { and last })
                lines = out.splitlines()
                json_start = None
                for i, line in enumerate(lines):
                    if line.strip().startswith("{"):
                        json_start = i
                        break
                if json_start is not None:
                    json_text = "\n".join(lines[json_start:])
                    try:
                        data = json.loads(json_text)
                    except json.JSONDecodeError:
                        pass
            if not data:
                failed += 1
                failures.append((url, "no JSON in output", "unknown"))
                print("FAIL (no JSON)")
                continue
            aa = data.get("audio_analysis") or {}
            err_str = aa.get("error")
            if err_str:
                failed += 1
                phase = "download" if "download" in err_str.lower() or "Failed to download" in err_str else "load_raw"
                failures.append((url, err_str, phase))
                print(f"FAIL ({phase})")
            else:
                passed += 1
                print("PASS")
        except subprocess.TimeoutExpired:
            failed += 1
            failures.append((url, "timeout", "unknown"))
            print("FAIL (timeout)")
        except Exception as e:
            failed += 1
            failures.append((url, str(e), "unknown"))
            print(f"FAIL ({e})")

    ips_after = list_python_ips()
    new_ips = sorted(ips_after - ips_before)

    print()
    print("=" * 60)
    print("Phase 3 verification summary")
    print("=" * 60)
    print(f"Pass count: {passed}")
    print(f"Fail count: {failed}")
    if failures:
        print()
        print("Failures (error string, phase):")
        for url, err, phase in failures:
            short_url = url[:55] + "..." if len(url) > 58 else url
            print(f"  {short_url}")
            print(f"    error: {err[:80]}{'...' if len(err) > 80 else ''}")
            print(f"    phase: {phase}")
    print()
    if new_ips:
        print("Python crash reports: NEW .ips during run:")
        for name in new_ips:
            print(f"  {DIAG_REPORTS_DIR / name}")
    else:
        print("Python crash reports: no new ~/Library/Logs/DiagnosticReports/*Python*.ips during run.")
    print()
    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()
