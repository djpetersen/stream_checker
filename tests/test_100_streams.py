#!/usr/bin/env python3
"""Test 100 audio streams end-to-end and verify database logging"""

import sys
import os
import json
import time
from pathlib import Path
from datetime import datetime

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Import safe subprocess helper to prevent fork crashes on macOS
from stream_checker.utils.subprocess_utils import run_subprocess_safe

# Stream list - 100 unique streams
STREAMS = [
    # RadioMast reference streams (MP3)
    "http://streams.radiomast.io/ref-128k-mp3-stereo",
    "http://streams.radiomast.io/ref-96k-mp3-stereo",
    "http://streams.radiomast.io/ref-64k-mp3-stereo",
    "http://streams.radiomast.io/ref-32k-mp3-mono",
    "https://streams.radiomast.io/ref-128k-mp3-stereo",
    "https://streams.radiomast.io/ref-96k-mp3-stereo",
    "https://streams.radiomast.io/ref-64k-mp3-stereo",
    "http://streams.radiomast.io/ref-48k-mp3-stereo",
    "http://streams.radiomast.io/ref-40k-mp3-stereo",
    
    # RadioMast AAC streams
    "http://streams.radiomast.io/ref-128k-aaclc-stereo",
    "http://streams.radiomast.io/ref-96k-aaclc-stereo",
    "http://streams.radiomast.io/ref-64k-heaacv1-stereo",
    "http://streams.radiomast.io/ref-64k-heaacv2-stereo",
    "http://streams.radiomast.io/ref-24k-heaacv1-mono",
    "https://streams.radiomast.io/ref-128k-aaclc-stereo",
    "https://streams.radiomast.io/ref-64k-heaacv1-stereo",
    
    # RadioMast Ogg streams
    "http://streams.radiomast.io/ref-64k-ogg-vorbis-stereo",
    "http://streams.radiomast.io/ref-64k-ogg-opus-stereo",
    "http://streams.radiomast.io/ref-96k-ogg-vorbis-stereo",
    "https://streams.radiomast.io/ref-64k-ogg-vorbis-stereo",
    "https://streams.radiomast.io/ref-64k-ogg-opus-stereo",
    
    # Dutch public radio (Icecast) - NPO Radio
    "http://icecast.omroep.nl/radio1-bb-mp3",
    "http://icecast.omroep.nl/radio2-bb-mp3",
    "http://icecast.omroep.nl/3fm-bb-mp3",
    "http://icecast.omroep.nl/radio4-bb-mp3",
    "http://icecast.omroep.nl/radio5-bb-mp3",
    "http://icecast.omroep.nl/radio6-bb-mp3",
    "http://icecast.omroep.nl/funx-bb-mp3",
    "http://icecast.omroep.nl/radio1-bb-aac",
    "http://icecast.omroep.nl/radio2-bb-aac",
    "http://icecast.omroep.nl/3fm-bb-aac",
    
    # SomaFM streams (MP3) - ice1
    "http://ice1.somafm.com/groovesalad-128-mp3",
    "http://ice1.somafm.com/dronezone-128-mp3",
    "http://ice1.somafm.com/deepspaceone-128-mp3",
    "http://ice1.somafm.com/defcon-128-mp3",
    "http://ice1.somafm.com/fluid-128-mp3",
    "http://ice1.somafm.com/beatblender-128-mp3",
    "http://ice1.somafm.com/bootliquor-128-mp3",
    "http://ice1.somafm.com/brfm-128-mp3",
    "http://ice1.somafm.com/cliqhop-128-mp3",
    "http://ice1.somafm.com/covers-128-mp3",
    "http://ice1.somafm.com/digitalis-128-mp3",
    "http://ice1.somafm.com/doomed-128-mp3",
    "http://ice1.somafm.com/dubstep-128-mp3",
    "http://ice1.somafm.com/earwaves-128-mp3",
    "http://ice1.somafm.com/folkfwd-128-mp3",
    "http://ice1.somafm.com/illstreet-128-mp3",
    "http://ice1.somafm.com/indiepop-128-mp3",
    "http://ice1.somafm.com/lush-128-mp3",
    "http://ice1.somafm.com/metal-128-mp3",
    "http://ice1.somafm.com/missioncontrol-128-mp3",
    "http://ice1.somafm.com/n5md-128-mp3",
    "http://ice1.somafm.com/poptron-128-mp3",
    "http://ice1.somafm.com/reggae-128-mp3",
    "http://ice1.somafm.com/seventies-128-mp3",
    "http://ice1.somafm.com/sf1033-128-mp3",
    "http://ice1.somafm.com/sonicuniverse-128-mp3",
    "http://ice1.somafm.com/spacestation-128-mp3",
    "http://ice1.somafm.com/suburbsofgoa-128-mp3",
    "http://ice1.somafm.com/synphaera-128-mp3",
    "http://ice1.somafm.com/thetrip-128-mp3",
    "http://ice1.somafm.com/thistle-128-mp3",
    "http://ice1.somafm.com/u80s-128-mp3",
    "http://ice1.somafm.com/vaporwaves-128-mp3",
    
    # SomaFM streams - ice2
    "http://ice2.somafm.com/groovesalad-128-mp3",
    "http://ice2.somafm.com/dronezone-128-mp3",
    "http://ice2.somafm.com/deepspaceone-128-mp3",
    "http://ice2.somafm.com/beatblender-128-mp3",
    "http://ice2.somafm.com/bootliquor-128-mp3",
    "http://ice2.somafm.com/cliqhop-128-mp3",
    "http://ice2.somafm.com/digitalis-128-mp3",
    "http://ice2.somafm.com/doomed-128-mp3",
    "http://ice2.somafm.com/earwaves-128-mp3",
    "http://ice2.somafm.com/folkfwd-128-mp3",
    "http://ice2.somafm.com/illstreet-128-mp3",
    "http://ice2.somafm.com/indiepop-128-mp3",
    "http://ice2.somafm.com/lush-128-mp3",
    "http://ice2.somafm.com/metal-128-mp3",
    "http://ice2.somafm.com/missioncontrol-128-mp3",
    "http://ice2.somafm.com/poptron-128-mp3",
    "http://ice2.somafm.com/reggae-128-mp3",
    "http://ice2.somafm.com/spacestation-128-mp3",
    "http://ice2.somafm.com/suburbsofgoa-128-mp3",
    "http://ice2.somafm.com/thetrip-128-mp3",
    "http://ice2.somafm.com/u80s-128-mp3",
    
    # SomaFM streams - ice3, ice4, ice5, ice6
    "http://ice3.somafm.com/groovesalad-128-mp3",
    "http://ice3.somafm.com/dronezone-128-mp3",
    "http://ice3.somafm.com/deepspaceone-128-mp3",
    "http://ice4.somafm.com/groovesalad-128-mp3",
    "http://ice4.somafm.com/dronezone-128-mp3",
    "http://ice5.somafm.com/groovesalad-128-mp3",
    "http://ice5.somafm.com/dronezone-128-mp3",
    "http://ice6.somafm.com/groovesalad-128-mp3",
    "http://ice6.somafm.com/dronezone-128-mp3",
    
    # Radio France (HTTPS)
    "https://icecast.radiofrance.fr/fip-hifi.mp3",
    "https://icecast.radiofrance.fr/franceinter-hifi.aac",
    "https://icecast.radiofrance.fr/franceinfo-hifi.aac",
    "https://icecast.radiofrance.fr/franceculture-hifi.aac",
    "https://icecast.radiofrance.fr/francemusique-hifi.aac",
    "https://icecast.radiofrance.fr/mouv-hifi.aac",
    "https://icecast.radiofrance.fr/fip-hifi.aac",
    "https://icecast.radiofrance.fr/fip-midfi.mp3",
    "https://icecast.radiofrance.fr/franceinter-midfi.aac",
    "https://icecast.radiofrance.fr/franceinfo-midfi.aac",
    "https://icecast.radiofrance.fr/franceculture-midfi.aac",
    
    # BBC Radio streams
    "http://bbcmedia.ic.llnwd.net/stream/bbcmedia_radio1_mf_p",
    "http://bbcmedia.ic.llnwd.net/stream/bbcmedia_radio2_mf_p",
    "http://bbcmedia.ic.llnwd.net/stream/bbcmedia_radio3_mf_p",
    "http://bbcmedia.ic.llnwd.net/stream/bbcmedia_radio4fm_mf_p",
    "http://bbcmedia.ic.llnwd.net/stream/bbcmedia_radio5live_mf_p",
    "http://bbcmedia.ic.llnwd.net/stream/bbcmedia_6music_mf_p",
    "http://bbcmedia.ic.llnwd.net/stream/bbcmedia_radio1xtra_mf_p",
    "http://bbcmedia.ic.llnwd.net/stream/bbcmedia_radio4extra_mf_p",
    "http://bbcmedia.ic.llnwd.net/stream/bbcmedia_asiannetwork_mf_p",
    "http://bbcmedia.ic.llnwd.net/stream/bbcmedia_worldservice_mf_p",
    
    # BBC alternative streams
    "http://stream.live.vc.bbcmedia.co.uk/bbc_radio_one",
    "http://stream.live.vc.bbcmedia.co.uk/bbc_radio_two",
    "http://stream.live.vc.bbcmedia.co.uk/bbc_radio_three",
    "http://stream.live.vc.bbcmedia.co.uk/bbc_radio_fourfm",
    "http://stream.live.vc.bbcmedia.co.uk/bbc_radio_five_live_online_nonuk",
    "http://stream.live.vc.bbcmedia.co.uk/bbc_6music",
    "http://stream.live.vc.bbcmedia.co.uk/bbc_radio_onextra",
    "http://stream.live.vc.bbcmedia.co.uk/bbc_radio_four_extra",
    "http://stream.live.vc.bbcmedia.co.uk/bbc_asian_network",
    "http://stream.live.vc.bbcmedia.co.uk/bbc_world_service",
    
    # Radio Paradise streams
    "http://stream-dc1.radioparadise.com/mp3-192",
    "http://stream-dc1.radioparadise.com/mp3-128",
    "http://stream-tx1.radioparadise.com/mp3-128",
    "http://stream-dc1.radioparadise.com/mp3-32",
    "http://stream-dc1.radioparadise.com/aac-320",
    "http://stream-dc1.radioparadise.com/aac-128",
    "http://stream-tx1.radioparadise.com/aac-64",
    "http://stream-tx1.radioparadise.com/aac-32",
    
    # WFMU streams
    "http://stream0.wfmu.org/freeform-128k",
    "http://stream0.wfmu.org/rock-128k",
    "http://stream0.wfmu.org/teaparty-128k",
    
    # HLS test streams (M3U8)
    "https://test-streams.mux.dev/x36xhzz/x36xhzz.m3u8",
    "https://devstreaming-cdn.apple.com/videos/streaming/examples/img_bipbop_adv_example_fmp4/master.m3u8",
    "https://demo.unified-streaming.com/k8s/features/stable/video/tears-of-steel/tears-of-steel.ism/.m3u8",
    "https://cph-p2p-msl.akamaized.net/hls/live/2000345/test/master.m3u8",
    "https://bitdash-a.akamaihd.net/content/sintel/hls/playlist.m3u8",
]

# Limit to 100 unique streams
STREAMS = list(dict.fromkeys(STREAMS))[:100]

def get_db_count(db_path):
    """Get count of test runs in database"""
    try:
        import sqlite3
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute('SELECT COUNT(*) FROM test_runs')
        count = cursor.fetchone()[0]
        conn.close()
        return count
    except Exception:
        return 0

def main():
    db_path = Path.home() / ".stream_checker" / "stream_checker.db"
    results_dir = Path(f"/tmp/stream_test_100_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}")
    results_dir.mkdir(parents=True, exist_ok=True)
    
    print("=" * 60)
    print("Comprehensive Stream Test Suite - 100 Streams")
    print(f"Testing {len(STREAMS)} unique audio streams")
    print("Running ALL phases (including VLC player test)")
    print("Results will be logged to database")
    print("=" * 60)
    print(f"Start time: {datetime.now()}")
    print(f"Database: {db_path}")
    print(f"Results dir: {results_dir}")
    print()
    
    initial_db_count = get_db_count(str(db_path))
    print(f"Initial test runs in database: {initial_db_count}")
    print()
    
    passed = 0
    failed = 0
    crashed = 0
    failed_streams = []
    crashed_streams = []
    start_time = time.time()
    
    # Get project root for stream_checker.py path
    project_root = Path(__file__).parent.parent
    stream_checker_script = project_root / "stream_checker.py"
    
    for i, url in enumerate(STREAMS, 1):
        result_file = results_dir / f"stream_{i}.json"
        error_file = results_dir / f"stream_{i}_error.log"
        
        print(f"[{i}/{len(STREAMS)}] Testing: {url}")
        print("-" * 60)
        
        try:
            # Run stream_checker.py with all phases - use run_subprocess_safe to prevent fork crashes
            # Pass through STREAM_CHECKER_TRACE_SUBPROCESS env var if set
            env = None
            if os.environ.get('STREAM_CHECKER_TRACE_SUBPROCESS') == '1':
                env = dict(os.environ)
            result = run_subprocess_safe(
                [sys.executable, str(stream_checker_script), "--url", url, "--output-format", "json"],
                timeout=300.0,  # 5 minute timeout per stream
                text=True,
                env=env
            )
            
            # Extract results from dictionary format
            returncode = result.get('returncode')
            stdout = result.get('stdout', '')
            stderr = result.get('stderr', '')
            success = result.get('success', False)
            
            # Save output
            with open(result_file, 'w') as f:
                f.write(stdout if isinstance(stdout, str) else stdout.decode('utf-8', errors='ignore') if stdout else '')
            with open(error_file, 'w') as f:
                f.write(stderr if isinstance(stderr, str) else stderr.decode('utf-8', errors='ignore') if stderr else '')
            
            # Check for signal kills (crash detection)
            if result.get('is_signal_kill'):
                signal_num = result.get('signal_num')
                signal_name = result.get('signal_name', f'SIG{signal_num}')
                print(f"💥 CRASHED - Process killed by {signal_name} (signal {signal_num})")
                crashed += 1
                crashed_streams.append(url)
                if stderr:
                    stderr_str = stderr if isinstance(stderr, str) else stderr.decode('utf-8', errors='ignore')
                    print(f"  Error: {stderr_str[:200]}")
            elif success and returncode == 0:
                # Check if output is valid JSON with test_run_id
                try:
                    stdout_str = stdout if isinstance(stdout, str) else stdout.decode('utf-8', errors='ignore') if stdout else '{}'
                    data = json.loads(stdout_str)
                    if "test_run_id" in data:
                        print(f"✅ PASSED - All phases completed, logged to database")
                        passed += 1
                        health = data.get("health_score", "N/A")
                        status = data.get("connectivity", {}).get("status", "N/A")
                        phase = data.get("phase", "N/A")
                        print(f"  Health Score: {health} | Status: {status} | Phase: {phase}")
                    else:
                        print("⚠️  WARNING - Completed but no test_run_id in output")
                        failed += 1
                        failed_streams.append(url)
                except json.JSONDecodeError:
                    print("⚠️  WARNING - Output is not valid JSON")
                    failed += 1
                    failed_streams.append(url)
            else:
                # Process failed or timed out
                exit_code = returncode
                error_msg = result.get('error', 'Unknown error')
                if 'timeout' in error_msg.lower():
                    print("⏱️  TIMEOUT - Stream test exceeded 5 minute timeout")
                elif exit_code in [139, 134, 130]:  # SIGSEGV, SIGABRT, SIGINT
                    print(f"💥 CRASHED (exit code: {exit_code})")
                    crashed += 1
                    crashed_streams.append(url)
                else:
                    print(f"❌ FAILED (exit code: {exit_code})")
                    failed += 1
                    failed_streams.append(url)
                
                if stderr:
                    stderr_str = stderr if isinstance(stderr, str) else stderr.decode('utf-8', errors='ignore')
                    print(f"  Error: {stderr_str[:200]}")
        
        except Exception as e:
            print(f"❌ EXCEPTION: {e}")
            failed += 1
            failed_streams.append(url)
        
        print()
    
    end_time = time.time()
    duration = int(end_time - start_time)
    
    # Verify database
    final_db_count = get_db_count(str(db_path))
    new_runs = final_db_count - initial_db_count
    
    print("=" * 60)
    print("Test Summary")
    print("=" * 60)
    print(f"Total streams tested: {len(STREAMS)}")
    print(f"✅ Passed: {passed}")
    print(f"❌ Failed: {failed}")
    print(f"💥 Crashed: {crashed}")
    print(f"Duration: {duration}s ({duration // 60}m {duration % 60}s)")
    print(f"End time: {datetime.now()}")
    print()
    print(f"Database verification:")
    print(f"  Initial test runs: {initial_db_count}")
    print(f"  Final test runs: {final_db_count}")
    print(f"  New test runs added: {new_runs}")
    print()
    
    if crashed > 0:
        print(f"⚠️  CRITICAL: {crashed} stream(s) caused Python to crash!")
        print("Crashed streams:")
        for stream in crashed_streams:
            print(f"  💥 {stream}")
        print()
    
    if failed > 0:
        print("Failed streams:")
        for stream in failed_streams[:20]:  # Show first 20
            print(f"  ❌ {stream}")
        if len(failed_streams) > 20:
            print(f"  ... and {len(failed_streams) - 20} more")
        print()
    
    print(f"Detailed results saved to: {results_dir}")
    print(f"Database location: {db_path}")
    print()
    
    # Final status
    if crashed > 0:
        print("❌ TEST SUITE FAILED - Crashes detected!")
        return 2
    elif failed > 0:
        print("⚠️  TEST SUITE COMPLETED WITH FAILURES")
        return 1
    else:
        print("✅ ALL TESTS PASSED!")
        return 0

if __name__ == "__main__":
    sys.exit(main())
