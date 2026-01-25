#!/usr/bin/env python3
"""
Stream Checker - Audio stream monitoring and validation tool
Main CLI entry point
"""

import sys
import argparse
import json
import logging
from pathlib import Path
from typing import Any

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from stream_checker.security.key_management import generate_test_run_id, generate_stream_id
from stream_checker.security.validation import URLValidator, ValidationError, validate_phase, validate_silence_threshold, validate_sample_duration
from stream_checker.core.connectivity import ConnectivityChecker
from stream_checker.core.player_test import test_player_connectivity
from stream_checker.core.audio_analysis import AudioAnalyzer
from stream_checker.core.ad_detection import AdDetector, HealthScoreCalculator
from stream_checker.database.models import Database
from stream_checker.utils.config import Config
from stream_checker.utils.logging import setup_logging
from colorama import init, Fore, Style

# Initialize colorama for cross-platform colored output
init(autoreset=True)


def print_header(text: str):
    """Print formatted header"""
    print(f"\n{Fore.CYAN}{Style.BRIGHT}{'=' * 60}")
    print(f"{text:^60}")
    print(f"{'=' * 60}{Style.RESET_ALL}\n")


def print_section(title: str):
    """Print section title"""
    print(f"\n{Fore.YELLOW}{Style.BRIGHT}{title}{Style.RESET_ALL}")
    print("-" * 60)


def print_result(key: str, value: Any, status: str = None):
    """Print key-value result with optional status color"""
    if status == "success":
        status_marker = f"{Fore.GREEN}✓{Style.RESET_ALL}"
    elif status == "error":
        status_marker = f"{Fore.RED}✗{Style.RESET_ALL}"
    elif status == "warning":
        status_marker = f"{Fore.YELLOW}⚠{Style.RESET_ALL}"
    else:
        status_marker = ""
    
    if status_marker:
        print(f"  {status_marker} {key:.<40} {value}")
    else:
        print(f"    {key:.<40} {value}")


def format_json_output(result: dict) -> str:
    """Format result as JSON"""
    try:
        return json.dumps(result, indent=2, default=str)  # default=str handles non-serializable types
    except (TypeError, ValueError) as e:
        logger = logging.getLogger("stream_checker")
        logger.error(f"JSON serialization error: {e}")
        # Return a simplified error message
        return json.dumps({"error": "Failed to serialize results", "details": str(e)}, indent=2)


def format_text_output(result: dict) -> str:
    """Format result as human-readable text"""
    output = []
    
    output.append(f"\n{'=' * 60}")
    output.append(f"Stream Health Check Report")
    output.append(f"{'=' * 60}\n")
    
    output.append(f"Test Run ID: {result.get('test_run_id', 'N/A')}")
    output.append(f"Stream ID:   {result.get('stream_id', 'N/A')}")
    output.append(f"Stream URL:  {result.get('stream_url', 'N/A')}")
    output.append(f"Test Time:   {result.get('timestamp', 'N/A')}")
    output.append(f"Phase:       {result.get('phase', 'N/A')}")
    
    # Health Score
    if "health_score" in result:
        score = result["health_score"]
        score_color = Fore.GREEN if score >= 80 else Fore.YELLOW if score >= 60 else Fore.RED
        output.append(f"{score_color}Overall Health Score: {score}/100{Style.RESET_ALL}")
    
    output.append("")
    
    # Connectivity
    if "connectivity" in result:
        output.append(f"\n{Fore.YELLOW}{Style.BRIGHT}Connectivity{Style.RESET_ALL}")
        output.append("-" * 60)
        conn = result["connectivity"]
        status = "success" if conn.get("status") == "success" else "error"
        status_marker = f"{Fore.GREEN}✓{Style.RESET_ALL}" if status == "success" else f"{Fore.RED}✗{Style.RESET_ALL}"
        output.append(f"  {status_marker} {'Status':.<40} {conn.get('status', 'unknown')}")
        if "response_time_ms" in conn:
            output.append(f"    {'Response Time':.<40} {conn['response_time_ms']} ms")
        if "http_status" in conn:
            output.append(f"    {'HTTP Status':.<40} {conn['http_status']}")
        if "content_type" in conn:
            output.append(f"    {'Content Type':.<40} {conn['content_type']}")
        if "error" in conn:
            output.append(f"  {Fore.RED}✗{Style.RESET_ALL} {'Error':.<40} {conn['error']}")
    
    # SSL Certificate
    if "ssl_certificate" in result and result["ssl_certificate"]:
        output.append(f"\n{Fore.YELLOW}{Style.BRIGHT}SSL Certificate{Style.RESET_ALL}")
        output.append("-" * 60)
        ssl = result["ssl_certificate"]
        if "valid" in ssl:
            status = "success" if ssl["valid"] else "error"
            status_marker = f"{Fore.GREEN}✓{Style.RESET_ALL}" if status == "success" else f"{Fore.RED}✗{Style.RESET_ALL}"
            output.append(f"  {status_marker} {'Valid':.<40} {'YES' if ssl['valid'] else 'NO'}")
        if "expires" in ssl:
            output.append(f"    {'Expires':.<40} {ssl['expires']}")
        if "days_until_expiration" in ssl and ssl["days_until_expiration"] is not None:
            days = ssl["days_until_expiration"]
            status_marker = f"{Fore.YELLOW}⚠{Style.RESET_ALL}" if days < 30 else f"{Fore.GREEN}✓{Style.RESET_ALL}"
            output.append(f"  {status_marker} {'Days Until Expiration':.<40} {days} days")
        if "issuer" in ssl:
            output.append(f"    {'Issuer':.<40} {ssl['issuer']}")
        if "self_signed" in ssl:
            status_marker = f"{Fore.YELLOW}⚠{Style.RESET_ALL}" if ssl["self_signed"] else ""
            output.append(f"  {status_marker} {'Self-Signed':.<40} {'YES' if ssl['self_signed'] else 'NO'}")
        if "error" in ssl:
            output.append(f"  {Fore.RED}✗{Style.RESET_ALL} {'Error':.<40} {ssl['error']}")
    
    # Stream Parameters
    if "stream_parameters" in result:
        output.append(f"\n{Fore.YELLOW}{Style.BRIGHT}Stream Parameters{Style.RESET_ALL}")
        output.append("-" * 60)
        params = result["stream_parameters"]
        if params.get("bitrate_kbps"):
            output.append(f"    {'Bitrate':.<40} {params['bitrate_kbps']} kbps")
        if params.get("codec"):
            output.append(f"    {'Codec':.<40} {params['codec']}")
        if params.get("sample_rate_hz"):
            output.append(f"    {'Sample Rate':.<40} {params['sample_rate_hz']} Hz")
        if params.get("channels"):
            output.append(f"    {'Channels':.<40} {params['channels']}")
        if params.get("container"):
            output.append(f"    {'Container':.<40} {params['container']}")
        if params.get("error"):
            output.append(f"  {Fore.RED}✗{Style.RESET_ALL} {'Error':.<40} {params['error']}")
    
    # Metadata
    if "metadata" in result:
        output.append(f"\n{Fore.YELLOW}{Style.BRIGHT}Metadata{Style.RESET_ALL}")
        output.append("-" * 60)
        meta = result["metadata"]
        if meta.get("title"):
            output.append(f"    {'Title':.<40} {meta['title']}")
        if meta.get("artist"):
            output.append(f"    {'Artist':.<40} {meta['artist']}")
        if meta.get("genre"):
            output.append(f"    {'Genre':.<40} {meta['genre']}")
        if meta.get("description"):
            output.append(f"    {'Description':.<40} {meta['description']}")
    
    # Server Headers
    if "server_headers" in result:
        output.append(f"\n{Fore.YELLOW}{Style.BRIGHT}Server Headers{Style.RESET_ALL}")
        output.append("-" * 60)
        headers = result["server_headers"]
        if headers.get("server"):
            output.append(f"    {'Server':.<40} {headers['server']}")
        if "cors_enabled" in headers:
            output.append(f"    {'CORS Enabled':.<40} {'YES' if headers['cors_enabled'] else 'NO'}")
        if headers.get("cache_control"):
            output.append(f"    {'Cache Control':.<40} {headers['cache_control']}")
    
    # HLS Info
    if "hls_info" in result and result["hls_info"]:
        output.append(f"\n{Fore.YELLOW}{Style.BRIGHT}HLS Information{Style.RESET_ALL}")
        output.append("-" * 60)
        hls = result["hls_info"]
        if "playlist_accessible" in hls:
            status_marker = f"{Fore.GREEN}✓{Style.RESET_ALL}" if hls["playlist_accessible"] else f"{Fore.RED}✗{Style.RESET_ALL}"
            output.append(f"  {status_marker} {'Playlist Accessible':.<40} {'YES' if hls['playlist_accessible'] else 'NO'}")
        if "is_master_playlist" in hls:
            output.append(f"    {'Master Playlist':.<40} {'YES' if hls['is_master_playlist'] else 'NO'}")
        if "variant_streams" in hls and hls["variant_streams"]:
            output.append(f"    {'Variant Streams':.<40} {len(hls['variant_streams'])}")
    
    # Player Tests (Phase 2)
    if "player_tests" in result:
        output.append(f"\n{Fore.YELLOW}{Style.BRIGHT}Player Tests{Style.RESET_ALL}")
        output.append("-" * 60)
        player_tests = result["player_tests"]
        if "vlc" in player_tests:
            vlc_result = player_tests["vlc"]
            status = vlc_result.get("status", "unknown")
            status_marker = f"{Fore.GREEN}✓{Style.RESET_ALL}" if status == "success" else f"{Fore.RED}✗{Style.RESET_ALL}"
            output.append(f"  {status_marker} {'VLC Status':.<40} {status.upper()}")
            
            if vlc_result.get("connection_time_ms"):
                output.append(f"    {'Connection Time':.<40} {vlc_result['connection_time_ms']} ms")
            if vlc_result.get("playback_duration_seconds"):
                output.append(f"    {'Playback Duration':.<40} {vlc_result['playback_duration_seconds']} seconds")
            if vlc_result.get("buffering_events", 0) > 0:
                output.append(f"    {'Buffering Events':.<40} {vlc_result['buffering_events']}")
            if vlc_result.get("format_supported") is not None:
                format_status = "YES" if vlc_result["format_supported"] else "NO"
                format_marker = f"{Fore.GREEN}✓{Style.RESET_ALL}" if vlc_result["format_supported"] else f"{Fore.RED}✗{Style.RESET_ALL}"
                output.append(f"  {format_marker} {'Format Supported':.<40} {format_status}")
            if vlc_result.get("errors"):
                for error in vlc_result["errors"]:
                    output.append(f"  {Fore.RED}✗{Style.RESET_ALL} {'Error':.<40} {error}")
            if vlc_result.get("method"):
                output.append(f"    {'Test Method':.<40} {vlc_result['method']}")
    
    # Connection Quality (Phase 2)
    if "connection_quality" in result:
        output.append(f"\n{Fore.YELLOW}{Style.BRIGHT}Connection Quality{Style.RESET_ALL}")
        output.append("-" * 60)
        quality = result["connection_quality"]
        if "stable" in quality:
            stable_status = "YES" if quality["stable"] else "NO"
            stable_marker = f"{Fore.GREEN}✓{Style.RESET_ALL}" if quality["stable"] else f"{Fore.RED}✗{Style.RESET_ALL}"
            output.append(f"  {stable_marker} {'Stable':.<40} {stable_status}")
        if "packet_loss_detected" in quality:
            packet_loss = "YES" if quality["packet_loss_detected"] else "NO"
            output.append(f"    {'Packet Loss Detected':.<40} {packet_loss}")
    
    # Audio Analysis (Phase 3)
    if "audio_analysis" in result:
        output.append(f"\n{Fore.YELLOW}{Style.BRIGHT}Audio Analysis{Style.RESET_ALL}")
        output.append("-" * 60)
        audio = result["audio_analysis"]
        
        if "error" in audio:
            output.append(f"  {Fore.RED}✗{Style.RESET_ALL} {'Error':.<40} {audio['error']}")
        else:
            # Silence Detection
            silence = audio.get("silence_detection", {})
            if silence.get("silence_detected"):
                status_marker = f"{Fore.YELLOW}⚠{Style.RESET_ALL}"
                output.append(f"  {status_marker} {'Silence Detected':.<40} YES")
                output.append(f"    {'Silence Percentage':.<40} {silence.get('silence_percentage', 0)}%")
                if silence.get("silence_periods"):
                    output.append(f"    {'Silence Periods':.<40} {len(silence['silence_periods'])}")
            else:
                output.append(f"  {Fore.GREEN}✓{Style.RESET_ALL} {'Silence Detected':.<40} NO")
            
            # Error Detection
            error_det = audio.get("error_detection", {})
            if error_det.get("error_detected"):
                output.append(f"  {Fore.RED}✗{Style.RESET_ALL} {'Error Detected':.<40} YES")
                if error_det.get("error_messages"):
                    for msg in error_det["error_messages"]:
                        output.append(f"    {'Error':.<40} {msg}")
            else:
                output.append(f"  {Fore.GREEN}✓{Style.RESET_ALL} {'Error Detected':.<40} NO")
            
            # Audio Quality
            quality = audio.get("audio_quality", {})
            if quality.get("average_volume_db") is not None:
                output.append(f"    {'Average Volume':.<40} {quality['average_volume_db']} dB")
            if quality.get("peak_volume_db") is not None:
                output.append(f"    {'Peak Volume':.<40} {quality['peak_volume_db']} dB")
            if quality.get("dynamic_range_db") is not None:
                output.append(f"    {'Dynamic Range':.<40} {quality['dynamic_range_db']} dB")
            if quality.get("clipping_detected"):
                output.append(f"  {Fore.YELLOW}⚠{Style.RESET_ALL} {'Clipping Detected':.<40} YES ({quality.get('clipping_percentage', 0)}%)")
            else:
                output.append(f"  {Fore.GREEN}✓{Style.RESET_ALL} {'Clipping Detected':.<40} NO")
    
    # Ad Detection (Phase 4)
    if "ad_detection" in result:
        output.append(f"\n{Fore.YELLOW}{Style.BRIGHT}Ad Detection{Style.RESET_ALL}")
        output.append("-" * 60)
        ad_det = result["ad_detection"]
        
        if ad_det.get("ads_detected"):
            output.append(f"  {Fore.GREEN}✓{Style.RESET_ALL} {'Ads Detected':.<40} YES")
            if ad_det.get("ad_frequency_per_hour"):
                output.append(f"    {'Ad Frequency':.<40} {ad_det['ad_frequency_per_hour']} per hour")
            if ad_det.get("total_ad_time_seconds"):
                output.append(f"    {'Total Ad Time':.<40} {ad_det['total_ad_time_seconds']} seconds")
            if ad_det.get("ad_breaks"):
                output.append(f"    {'Ad Breaks':.<40} {len(ad_det['ad_breaks'])}")
                for i, ad_break in enumerate(ad_det["ad_breaks"][:3], 1):  # Show first 3
                    output.append(f"      Break {i}: {ad_break.get('duration_seconds', 0)}s")
        else:
            output.append(f"  {'Ads Detected':.<40} NO")
    
    # Issues and Recommendations
    if "issues" in result and result["issues"]:
        output.append(f"\n{Fore.YELLOW}{Style.BRIGHT}Issues{Style.RESET_ALL}")
        output.append("-" * 60)
        for issue in result["issues"]:
            output.append(f"  {Fore.RED}✗{Style.RESET_ALL} {issue}")
    
    if "recommendations" in result and result["recommendations"]:
        output.append(f"\n{Fore.YELLOW}{Style.BRIGHT}Recommendations{Style.RESET_ALL}")
        output.append("-" * 60)
        for rec in result["recommendations"]:
            output.append(f"  {Fore.CYAN}→{Style.RESET_ALL} {rec}")
    
    output.append(f"\n{'=' * 60}\n")
    
    return "\n".join(output)


def main():
    """Main CLI entry point"""
    parser = argparse.ArgumentParser(
        description="Stream Checker - Audio stream monitoring and validation tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  stream_checker.py --url https://example.com/stream.mp3
  stream_checker.py --url https://example.com/stream.mp3 --phase 1
  stream_checker.py --url https://example.com/stream.mp3 --output-format json
        """
    )
    
    parser.add_argument(
        "--url",
        required=True,
        help="Stream URL to test"
    )
    
    parser.add_argument(
        "--phase",
        type=int,
        choices=[1, 2, 3, 4],
        help="Specific phase to run (default: all phases)"
    )
    
    parser.add_argument(
        "--silence-threshold",
        type=float,
        help="Silence threshold in dB (default: -40)"
    )
    
    parser.add_argument(
        "--sample-duration",
        type=int,
        help="Audio sample duration in seconds (default: 10)"
    )
    
    parser.add_argument(
        "--output-format",
        choices=["json", "text"],
        default="text",
        help="Output format (default: text)"
    )
    
    parser.add_argument(
        "--test-run-id",
        help="Use existing test run ID (default: generate new)"
    )
    
    parser.add_argument(
        "--config",
        help="Path to config file"
    )
    
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose logging"
    )
    
    args = parser.parse_args()
    
    # Load configuration
    config = Config(args.config)
    
    # Setup logging
    log_level = "DEBUG" if args.verbose else config.get("logging.level", "INFO")
    logger = setup_logging(
        level=log_level,
        log_file=config.get_path("logging.file"),
        max_file_size_mb=config.get("logging.max_file_size_mb", 10),
        backup_count=config.get("logging.backup_count", 5)
    )
    
    logger.info(f"Starting stream check for: {args.url}")
    
    # Validate URL
    url_validator = URLValidator(
        allowed_schemes=config.get("security.allowed_schemes", ["http", "https"]),
        block_private_ips=config.get("security.block_private_ips", False),
        max_url_length=config.get("security.max_url_length", 2048)
    )
    
    try:
        url_validator.validate_and_raise(args.url)
    except ValidationError as e:
        print(f"{Fore.RED}Error: {e}{Style.RESET_ALL}", file=sys.stderr)
        logger.error(f"URL validation failed: {e}")
        sys.exit(1)
    
    # Validate phase
    if args.phase and not validate_phase(args.phase):
        print(f"{Fore.RED}Error: Invalid phase. Must be 1-4.{Style.RESET_ALL}", file=sys.stderr)
        sys.exit(1)
    
    # Validate silence threshold
    if args.silence_threshold is not None and not validate_silence_threshold(args.silence_threshold):
        print(f"{Fore.RED}Error: Invalid silence threshold. Must be between -100 and 0 dB.{Style.RESET_ALL}", file=sys.stderr)
        sys.exit(1)
    
    # Validate sample duration
    if args.sample_duration is not None and not validate_sample_duration(args.sample_duration):
        print(f"{Fore.RED}Error: Invalid sample duration. Must be between 1 and 300 seconds.{Style.RESET_ALL}", file=sys.stderr)
        sys.exit(1)
    
    # Validate test_run_id format if provided
    if args.test_run_id:
        try:
            import uuid
            uuid.UUID(args.test_run_id)  # Validate UUID format
        except ValueError:
            print(f"{Fore.RED}Error: Invalid test_run_id format. Must be a valid UUID.{Style.RESET_ALL}", file=sys.stderr)
            sys.exit(1)
    
    # Generate IDs
    test_run_id = args.test_run_id or generate_test_run_id()
    stream_id = generate_stream_id(args.url)
    
    logger.info(f"Test Run ID: {test_run_id}")
    logger.info(f"Stream ID: {stream_id}")
    
    # Initialize database
    try:
        db_path = config.get_path("database.path")
        db = Database(db_path)
        
        # Add stream to database
        db.add_stream(stream_id, args.url)
    except Exception as e:
        logger.error(f"Database error: {e}")
        print(f"{Fore.YELLOW}Warning: Database operations may fail. Continuing without database.{Style.RESET_ALL}", file=sys.stderr)
        db = None
    
    # Determine which phases to run
    # If no phase specified, run all phases (1-4)
    # If phase specified, run that phase and all previous phases
    phases_to_run = []
    if args.phase:
        phases_to_run = list(range(1, args.phase + 1))
    else:
        phases_to_run = [1, 2, 3, 4]  # All phases implemented
    
    result = {
        "test_run_id": test_run_id,
        "stream_id": stream_id,
        "stream_url": args.url,
        "timestamp": None,  # Will be set by phase checker
        "phase": max(phases_to_run) if phases_to_run else 1
    }
    
    # Run Phase 1: Connectivity and Metadata
    if 1 in phases_to_run:
        logger.info("Running Phase 1: Connectivity and Metadata Extraction")
        
        checker = ConnectivityChecker(
            connection_timeout=config.get("security.connection_timeout", 30),
            read_timeout=config.get("security.read_timeout", 60),
            verify_ssl=config.get("security.verify_ssl", True)
        )
        
        phase_result = checker.check(args.url)
        
        # Merge results
        result.update(phase_result)
        
        # Save to database
        if db:
            try:
                db.add_test_run(test_run_id, stream_id, 1, result)
                db.update_stream_test_count(stream_id)
            except Exception as e:
                logger.error(f"Failed to save Phase 1 results to database: {e}")
        
        logger.info("Phase 1 completed")
    
    # Run Phase 2: Player Connectivity Testing
    if 2 in phases_to_run:
        logger.info("Running Phase 2: Player Connectivity Testing")
        
        playback_duration = args.sample_duration or config.get("stream_checker.default_sample_duration", 5)
        connection_timeout = config.get("security.connection_timeout", 30)
        
        player_result = test_player_connectivity(
            args.url,
            playback_duration=playback_duration,
            connection_timeout=connection_timeout
        )
        
        # Add player test results
        result["player_tests"] = {
            "vlc": player_result
        }
        
        result["connection_quality"] = {
            "stable": player_result.get("status") == "success",
            "packet_loss_detected": False  # Not easily detectable without deeper analysis
        }
        
        # Update phase number
        result["phase"] = 2
        
        # Save to database
        if db:
            try:
                db.add_test_run(test_run_id, stream_id, 2, result)
            except Exception as e:
                logger.error(f"Failed to save Phase 2 results to database: {e}")
        
        logger.info("Phase 2 completed")
    
    # Run Phase 3: Audio Analysis
    if 3 in phases_to_run:
        logger.info("Running Phase 3: Audio Analysis")
        
        sample_duration = args.sample_duration or config.get("stream_checker.default_sample_duration", 10)
        silence_threshold = args.silence_threshold or config.get("stream_checker.default_silence_threshold", -40)
        
        analyzer = AudioAnalyzer(
            sample_duration=sample_duration,
            silence_threshold_db=silence_threshold,
            silence_min_duration=2.0
        )
        
        audio_result = analyzer.analyze(args.url)
        
        # Add audio analysis results
        result["audio_analysis"] = audio_result
        
        # Update phase number
        result["phase"] = 3
        
        # Save to database
        if db:
            try:
                db.add_test_run(test_run_id, stream_id, 3, result)
            except Exception as e:
                logger.error(f"Failed to save Phase 3 results to database: {e}")
        
        logger.info("Phase 3 completed")
    
    # Run Phase 4: Ad Detection & Enhanced Reporting
    if 4 in phases_to_run:
        logger.info("Running Phase 4: Ad Detection")
        
        # Monitor for ad markers (shorter duration for testing)
        monitoring_duration = 30  # 30 seconds for desktop version
        
        detector = AdDetector(
            monitoring_duration=monitoring_duration,
            check_interval=2.0
        )
        
        ad_result = detector.detect(args.url)
        
        # Add ad detection results
        result["ad_detection"] = ad_result
        
        # Calculate health score
        health_info = HealthScoreCalculator.calculate(result)
        result["health_score"] = health_info["health_score"]
        result["issues"] = health_info["issues"]
        result["recommendations"] = health_info["recommendations"]
        
        # Update phase number
        result["phase"] = 4
        
        # Save to database
        if db:
            try:
                db.add_test_run(test_run_id, stream_id, 4, result)
            except Exception as e:
                logger.error(f"Failed to save Phase 4 results to database: {e}")
        
        logger.info("Phase 4 completed")
    
    # Output results
    if args.output_format == "json":
        print(format_json_output(result))
    else:
        # Print formatted text output
        text_output = format_text_output(result)
        print(text_output)
        # Also print JSON to stdout if verbose
        if args.verbose:
            print("\n" + "=" * 60)
            print("JSON Output:")
            print("=" * 60)
            print(format_json_output(result))
    
    logger.info("Stream check completed")


if __name__ == "__main__":
    main()
