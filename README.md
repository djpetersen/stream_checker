# Stream Checker

A Python-based application for monitoring and validating internet audio streams. Check stream health, metadata, connectivity, audio quality, and detect advertising markers.

## Features

### Phase 1: Connectivity & Metadata ✅
- ✅ HTTP/HTTPS connection testing
- ✅ SSL/TLS certificate validation
- ✅ Stream parameter extraction (bitrate, codec, sample rate, channels)
- ✅ Stream metadata extraction (title, genre, artist)
- ✅ Server headers analysis
- ✅ HLS stream support

### Phase 2: Player Connectivity Testing ✅
- ✅ VLC player testing (command-line fallback)
- ✅ Connection time measurement
- ✅ Format compatibility detection
- ✅ Connection quality metrics
- ✅ Buffering event monitoring

### Phase 3: Audio Analysis ✅
- ✅ 10-second audio sampling via ffmpeg
- ✅ Silence detection (RMS amplitude, configurable threshold)
- ✅ Error message detection (repetitive pattern detection)
- ✅ Audio quality metrics (volume, dynamic range, clipping)

### Phase 4: Ad Detection & Enhanced Reporting ✅
- ✅ Metadata-based ad marker detection
- ✅ Ad break duration tracking
- ✅ Health score calculation (0-100)
- ✅ Issues and recommendations reporting
- ✅ Comprehensive terminal output

## Installation

### Prerequisites

- Python 3.9 or higher
- VLC media player (for Phase 2)
- ffmpeg (for Phase 3)

### Install Dependencies

```bash
# Create virtual environment (recommended)
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install Python dependencies
pip install -r requirements.txt
```

### Install System Dependencies

**macOS:**
```bash
# Install VLC
brew install vlc

# Install ffmpeg
brew install ffmpeg
```

**Linux (Ubuntu/Debian):**
```bash
sudo apt-get update
sudo apt-get install vlc ffmpeg
```

**Windows:**
- Download and install VLC from https://www.videolan.org/vlc/
- Download and install ffmpeg from https://ffmpeg.org/download.html

## Usage

### Basic Usage

```bash
# Check a stream (runs all phases by default)
python stream_checker.py --url https://example.com/stream.mp3

# Run specific phase
python stream_checker.py --url https://example.com/stream.mp3 --phase 4

# Output as JSON
python stream_checker.py --url https://example.com/stream.mp3 --output-format json

# Verbose logging
python stream_checker.py --url https://example.com/stream.mp3 --verbose

# Custom settings
python stream_checker.py --url https://example.com/stream.mp3 --sample-duration 10 --silence-threshold -40
```

### Command-Line Options

```
--url <stream_url>          Required: Stream URL to test
--phase <1|2|3|4>           Optional: Specific phase (default: all phases)
--silence-threshold <db>    Optional: Silence threshold in dB (default: -40)
--sample-duration <seconds> Optional: Audio sample duration (default: 10)
--output-format <json|text> Optional: Output format (default: text)
--test-run-id <uuid>        Optional: Use existing test run ID
--config <path>             Optional: Path to config file
--verbose                   Optional: Enable verbose logging
```

### Configuration

The application uses `config.yaml` for configuration. A default configuration file is included. You can:

1. Edit `config.yaml` in the project root
2. Create `~/.stream_checker/config.yaml` for user-specific settings
3. Use `--config` to specify a custom config file

## Project Structure

```
stream_checker/
├── stream_checker.py          # Main CLI entry point
├── config.yaml                # Configuration file
├── requirements.txt           # Python dependencies
├── stream_checker/
│   ├── core/                  # Core checking modules
│   │   ├── connectivity.py   # Phase 1: Connectivity & metadata
│   │   ├── player_test.py    # Phase 2: Player testing
│   │   ├── audio_analysis.py # Phase 3: Audio analysis
│   │   └── ad_detection.py   # Phase 4: Ad detection
│   ├── security/              # Security modules
│   │   ├── validation.py     # Input validation
│   │   └── key_management.py # Key generation
│   ├── database/              # Database modules
│   │   └── models.py         # SQLite database models
│   └── utils/                 # Utility modules
│       ├── config.py         # Configuration management
│       └── logging.py        # Logging setup
└── README.md
```

## Database

The application uses SQLite to store:
- Stream information (URL, name, test count)
- Test run results (test_run_id, stream_id, phase, results JSON)

Database location: `~/.stream_checker/stream_checker.db` (configurable)

## Development Guidelines

### Multiprocessing

**All multiprocessing must go through `run_process_with_queue()`.**

This project uses multiprocessing on macOS to avoid fork-related crashes. To ensure consistency and prevent regressions:

1. **Never create `multiprocessing.Process` or `multiprocessing.Queue` directly** in `stream_checker/core/` modules
2. **Always use `run_process_with_queue()`** from `stream_checker/utils/multiprocessing_utils`
3. **Never duplicate spawn method setup** - it's centralized in `multiprocessing_utils.py`

The centralized helper ensures:
- Spawn method is set correctly on macOS
- Proper cleanup to prevent semaphore leaks
- Consistent timeout handling
- Single code path for all multiprocessing operations

**Verification:**
- Run `make mp-check` to run both consistency checks and tests
- Or run `scripts/mp_consistency_check.sh` and `python -m pytest tests/test_multiprocessing_consistency.py` separately

## Output Format

### Text Output (Default)

```
============================================================
Stream Health Check Report
============================================================

Test Run ID: 550e8400-e29b-41d4-a716-446655440000
Stream ID:   a1b2c3d4e5f6g7h8
Stream URL:  https://example.com/stream.mp3
Test Time:   2026-01-23T10:00:00Z
Phase:       4
Overall Health Score: 95/100

------------------------------------------------------------
Connectivity
------------------------------------------------------------
  ✓ Status.................................. success
    Response Time............................ 245 ms
    HTTP Status.............................. 200
    Content Type............................. audio/mpeg

------------------------------------------------------------
SSL Certificate
------------------------------------------------------------
  ✓ Valid................................... YES
    Expires.................................. 2026-12-31T23:59:59Z
    Days Until Expiration.................... 342 days
    Issuer................................... CN=Let's Encrypt

------------------------------------------------------------
Player Tests
------------------------------------------------------------
  ✓ VLC Status.............................. SUCCESS
    Connection Time.......................... 804 ms
    Format Supported......................... YES

------------------------------------------------------------
Audio Analysis
------------------------------------------------------------
  ✓ Silence Detected......................... NO
  ✓ Error Detected.......................... NO
    Average Volume.......................... -12.55 dB
    Peak Volume............................. -1.36 dB
    Dynamic Range........................... 11.19 dB

------------------------------------------------------------
Ad Detection
------------------------------------------------------------
  Ads Detected............................ NO

============================================================
```

### JSON Output

```json
{
  "test_run_id": "550e8400-e29b-41d4-a716-446655440000",
  "stream_id": "a1b2c3d4e5f6g7h8",
  "stream_url": "https://example.com/stream.mp3",
  "timestamp": "2026-01-23T10:00:00Z",
  "phase": 4,
  "connectivity": { ... },
  "player_tests": { ... },
  "audio_analysis": { ... },
  "ad_detection": { ... },
  "health_score": 95,
  "issues": [],
  "recommendations": []
}
```

## Security

The application includes comprehensive security features:
- URL validation and sanitization
- SSL/TLS certificate validation
- Resource limits (CPU, memory, disk)
- Input validation
- Secure key generation (test_run_id, stream_id)
- Unique identifiers for tracking

See `SPEC.md` for detailed security documentation.

## Supported Stream Types

- **MP3** (Icecast/Shoutcast)
- **AAC** (Icecast/Shoutcast)
- **HLS** (HTTP Live Streaming)

All three formats are fully supported and tested.

## Development

### Running Tests

```bash
# Run with a test stream (all phases)
python stream_checker.py --url https://example.com/stream.mp3 --verbose

# Test specific phase
python stream_checker.py --url https://example.com/stream.mp3 --phase 2

# Test different stream types
python stream_checker.py --url https://streams.radiobob.de/bob-live/mp3-192/mediaplayer
python stream_checker.py --url https://test-streams.mux.dev/x36xhzz/x36xhzz.m3u8
python stream_checker.py --url https://streams.radiomast.io/ref-128k-aaclc-stereo
```

### Code Structure

- `stream_checker.py`: Main CLI entry point
- `core/connectivity.py`: Phase 1 implementation
- `core/player_test.py`: Phase 2 implementation
- `core/audio_analysis.py`: Phase 3 implementation
- `core/ad_detection.py`: Phase 4 implementation
- `security/`: Security and validation modules
- `database/models.py`: Database models and operations

## Troubleshooting

### Connection Timeout

If you get connection timeouts, try:
- Increasing timeout in `config.yaml`: `security.connection_timeout`
- Checking if the stream URL is accessible
- Verifying network connectivity

### SSL Certificate Errors

If you get SSL errors:
- Check if the certificate is valid
- For self-signed certificates, the application will report them but continue
- Set `security.verify_ssl: false` in config (not recommended)

### Missing Dependencies

If you get import errors:
```bash
pip install -r requirements.txt
```

### VLC Not Found

If VLC player tests fail:
- Ensure VLC is installed and accessible
- The application will use command-line VLC as fallback
- Check that VLC is in your PATH or at `/Applications/VLC.app/Contents/MacOS/VLC` (macOS)

### ffmpeg Not Found

If audio analysis fails:
- Ensure ffmpeg is installed: `brew install ffmpeg` (macOS)
- Verify installation: `ffmpeg -version`
- The application will report an error if ffmpeg is not found

## License

[Add your license here]

## Contributing

[Add contribution guidelines here]

## Roadmap

- [x] Phase 1: Connectivity & Metadata
- [x] Phase 2: Player Testing
- [x] Phase 3: Audio Analysis
- [x] Phase 4: Ad Detection
- [ ] Future: AWS Cloud Deployment

See `SPEC.md` for detailed specification.
See `AWS_DEPLOYMENT_GUIDE.md` for AWS deployment steps and difficulty levels.
