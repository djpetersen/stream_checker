# Stream Checker Application - Specification

## Overview

A Python-based application for monitoring and validating internet audio streams. The application will check stream health, metadata, connectivity, audio quality, and detect advertising markers.

**Primary Focus: Desktop/Laptop Version**
- Run directly on macOS (and other platforms)
- Single-stream testing via command-line
- Local SQLite database for results
- Terminal-based output
- No cloud dependencies required

**Future Migration: AWS Service**
- Scalable cloud deployment (Phase 5+)
- Multi-stream scheduling
- Web dashboard and API
- Customer management
- See "Future: AWS Deployment" section for details

## Supported Stream Types

- **MP3** (Icecast/Shoutcast)
- **AAC** (Icecast/Shoutcast)
- **HLS** (HTTP Live Streaming)

## Technical Stack

- **Language**: Python 3.9+
- **Key Libraries**:
  - `requests` / `httpx` - HTTP stream access
  - `mutagen` / `eyed3` - Metadata extraction
  - `ffmpeg-python` / `subprocess` - Audio processing
  - `pydub` - Audio analysis
  - `cryptography` - SSL/TLS certificate validation
  - `vlc` (python-vlc) - Player testing
  - `selenium` / `playwright` - Browser-based testing (future)
  - `uuid` - Unique key generation
  - `secrets` - Cryptographically secure random generation
  - `hashlib` - Secure hashing for stream identification

## Key Management System

### Unique Identifiers

The application uses a hierarchical key system for tracking and security:

1. **Test Run ID** (`test_run_id`)
   - Unique identifier for each test execution
   - Format: UUID v4 (e.g., `550e8400-e29b-41d4-a716-446655440000`)
   - Generated at the start of each test run
   - Used for: Logging, result tracking, audit trails
   - Lifetime: Permanent (stored in results)

2. **Stream ID** (`stream_id`)
   - Unique identifier for each stream URL
   - Format: SHA-256 hash of normalized URL (first 16 chars of hex)
   - Generated from: Normalized stream URL (lowercase, remove query params for identification)
   - Used for: Stream deduplication, historical tracking, customer association
   - Lifetime: Permanent (persistent across test runs)
   - Example: `https://example.com/stream.mp3` → `a1b2c3d4e5f6g7h8`

3. **Customer ID** (`customer_id`) - Future Service
   - Unique identifier for each customer account
   - Format: UUID v4
   - Generated: During customer registration
   - Used for: Access control, billing, stream ownership
   - Lifetime: Permanent (until account deletion)

### Key Generation

```python
import uuid
import hashlib
from urllib.parse import urlparse

# Test Run ID
test_run_id = str(uuid.uuid4())

# Stream ID (deterministic from URL)
def generate_stream_id(url: str) -> str:
    # Normalize URL: lowercase, remove fragment, sort query params
    parsed = urlparse(url.lower())
    normalized = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
    if parsed.query:
        # Sort query params for consistency
        params = sorted(parsed.query.split('&'))
        normalized += '?' + '&'.join(params)
    
    # Generate SHA-256 hash, use first 16 characters
    stream_hash = hashlib.sha256(normalized.encode()).hexdigest()
    return stream_hash[:16]

# Customer ID (future)
customer_id = str(uuid.uuid4())
```

### Key Storage & Association

**Desktop Version:**
- Store in local SQLite database or JSON file
- Schema:
  ```sql
  streams (
    stream_id TEXT PRIMARY KEY,
    url TEXT UNIQUE NOT NULL,
    created_at TIMESTAMP,
    last_tested TIMESTAMP
  )
  
  test_runs (
    test_run_id TEXT PRIMARY KEY,
    stream_id TEXT,
    timestamp TIMESTAMP,
    phase INTEGER,
    results JSON
  )
  ```

**Future Service Version:**
- Store in PostgreSQL/MySQL database
- Schema:
  ```sql
  customers (
    customer_id UUID PRIMARY KEY,
    email TEXT UNIQUE,
    api_key_hash TEXT,
    created_at TIMESTAMP,
    status TEXT
  )
  
  streams (
    stream_id TEXT PRIMARY KEY,
    customer_id UUID REFERENCES customers(customer_id),
    url TEXT NOT NULL,
    name TEXT,
    created_at TIMESTAMP,
    last_tested TIMESTAMP
  )
  
  test_runs (
    test_run_id UUID PRIMARY KEY,
    stream_id TEXT REFERENCES streams(stream_id),
    customer_id UUID REFERENCES customers(customer_id),
    timestamp TIMESTAMP,
    phase INTEGER,
    results JSONB,
    INDEX(customer_id, timestamp),
    INDEX(stream_id, timestamp)
  )
  ```

## Security Features

### 1. Input Validation & Sanitization

**URL Validation:**
- Whitelist allowed URL schemes: `http://`, `https://`
- Block dangerous schemes: `file://`, `ftp://`, `javascript:`, `data:`
- Validate URL format using `urllib.parse`
- Maximum URL length: 2048 characters
- Block private/internal IP ranges (configurable):
  - `127.0.0.0/8` (localhost)
  - `10.0.0.0/8` (private)
  - `172.16.0.0/12` (private)
  - `192.168.0.0/16` (private)
  - `169.254.0.0/16` (link-local)
- DNS resolution validation before connection
- Rate limit: Maximum 10 unique URLs per minute (configurable)

**Parameter Validation:**
- Validate all command-line arguments
- Type checking for numeric parameters
- Range validation (e.g., silence threshold: -100 to 0 dB)
- Sanitize file paths if writing results to disk
- Prevent path traversal attacks

### 2. Network Security

**Connection Security:**
- Enforce TLS 1.2+ for HTTPS connections
- Verify SSL certificates (no insecure connections)
- Connection timeout: 30 seconds (configurable)
- Read timeout: 60 seconds (configurable)
- Maximum redirects: 5
- User-Agent: Identifiable but non-aggressive
- Rate limiting: Maximum 1 request per second per stream
- Connection pooling with limits

**DDoS Protection:**
- Request throttling per IP address
- Maximum concurrent connections: 10 (configurable)
- Circuit breaker pattern for failing streams
- Exponential backoff for retries
- Blacklist known malicious URLs/IPs (optional)

**Network Isolation:**
- Use separate network namespace (if available)
- Firewall rules to restrict outbound connections
- Monitor network usage and alert on anomalies

### 3. Resource Limits & Sandboxing

**CPU Limits:**
- Maximum CPU time per test: 5 minutes
- CPU usage monitoring and throttling
- Process priority management

**Memory Limits:**
- Maximum memory per test: 512 MB
- Memory usage monitoring
- Automatic cleanup of large buffers
- Garbage collection optimization

**Disk Limits:**
- Maximum temporary file size: 100 MB per test
- Automatic cleanup of temporary files
- Secure file deletion (overwrite before delete)
- Disk quota monitoring

**Process Isolation:**
- Run each test in separate subprocess
- Process timeout enforcement
- Kill hung processes automatically
- Resource limits via `resource` module (Unix) or job objects (Windows)

**Sandboxing (Future):**
- Docker containers for test execution
- Restricted filesystem access
- Network namespace isolation
- Capability dropping (Linux)

### 4. Secure Storage

**Credentials & Secrets:**
- Never store API keys, passwords in plaintext
- Use environment variables or secure vaults
- Encrypt sensitive configuration files
- Key derivation: Use `cryptography.fernet` or `bcrypt`
- Rotate keys periodically

**Result Storage:**
- Encrypt sensitive data at rest
- Hash stream URLs before storage (for privacy)
- Secure deletion of old results
- Access control on result files

**Database Security:**
- Use parameterized queries (prevent SQL injection)
- Encrypt database connections (TLS)
- Regular backups with encryption
- Access logging and audit trails

### 5. Secure Logging & Audit Trails

**Logging Best Practices:**
- Never log sensitive data (passwords, API keys, full URLs)
- Log test run IDs for traceability
- Structured logging (JSON format)
- Log levels: DEBUG, INFO, WARNING, ERROR, CRITICAL
- Rotate logs automatically

**Audit Trails:**
- Log all test executions with test_run_id
- Track user actions (for future service)
- Log authentication attempts
- Record configuration changes
- Store audit logs separately with integrity protection

**Log Security:**
- Encrypt log files at rest
- Restrict log file permissions (600 or 640)
- Monitor log file sizes
- Alert on suspicious patterns

### 6. Authentication & Authorization (Future Service)

**API Authentication:**
- API key-based authentication
- Keys stored as bcrypt hashes
- Key rotation support
- Rate limiting per API key
- IP whitelisting (optional)

**User Authentication:**
- Multi-factor authentication (MFA) support
- Password complexity requirements
- Account lockout after failed attempts
- Session management with secure cookies
- OAuth 2.0 / OpenID Connect support

**Authorization:**
- Role-based access control (RBAC)
- Stream ownership validation
- Resource-level permissions
- Principle of least privilege

### 7. API Security

**Rate Limiting:**
- Per-customer rate limits
- Per-IP rate limits
- Per-API-key rate limits
- Sliding window algorithm
- Return appropriate HTTP 429 responses

**Input Validation:**
- Validate all API inputs
- Use JSON schema validation
- Sanitize user-provided data
- Prevent injection attacks (SQL, NoSQL, command)

**Output Security:**
- Sanitize error messages (no stack traces in production)
- CORS configuration (restrict origins)
- Content Security Policy headers
- XSS prevention in web dashboard

### 8. Secure Configuration Management

**Configuration Security:**
- Separate development/production configs
- Never commit secrets to version control
- Use `.env` files with `.gitignore`
- Environment variable precedence
- Configuration validation on startup

**Secret Management:**
- Use secret management services (AWS Secrets Manager, HashiCorp Vault)
- Rotate secrets regularly
- Audit secret access
- Encrypt configuration files

### 9. Dependency Security

**Vulnerability Scanning:**
- Regular dependency updates
- Use `pip-audit` or `safety` for vulnerability scanning
- Pin dependency versions in `requirements.txt`
- Monitor security advisories
- Automated dependency updates (Dependabot, Renovate)

**Supply Chain Security:**
- Verify package integrity (checksums)
- Use private package repositories if needed
- Lock file for reproducible builds
- Review dependency licenses

### 10. Secure Error Handling

**Error Messages:**
- Generic error messages for users
- Detailed errors only in logs
- No stack traces in production
- No sensitive data in error responses
- Proper HTTP status codes

**Exception Handling:**
- Catch and log all exceptions
- Never expose internal errors
- Graceful degradation
- Retry logic with exponential backoff

### 11. Data Privacy & Compliance

**Data Minimization:**
- Only collect necessary data
- Don't store audio content permanently
- Hash or anonymize sensitive identifiers
- Data retention policies

**Privacy Controls:**
- Allow customers to delete their data
- Export data in standard formats
- Clear data retention policies
- GDPR compliance considerations

**Encryption:**
- Encrypt data in transit (TLS 1.2+)
- Encrypt data at rest
- Use strong encryption algorithms (AES-256)
- Key management best practices

### 12. Monitoring & Incident Response

**Security Monitoring:**
- Monitor for suspicious activity
- Failed authentication attempts
- Unusual API usage patterns
- Resource exhaustion alerts
- Network anomaly detection

**Incident Response:**
- Automated alerting on security events
- Incident response playbook
- Log retention for forensics
- Regular security audits
- Penetration testing

### 13. Secure Development Practices

**Code Security:**
- Code reviews for security issues
- Static analysis tools (Bandit, Semgrep)
- Secure coding guidelines
- Regular security training

**Testing:**
- Security testing in CI/CD
- Fuzzing for input validation
- Penetration testing
- Dependency vulnerability scanning

## Security Configuration

### Security Settings (config.yaml)

```yaml
security:
  # Network Security
  allowed_schemes: ["http", "https"]
  block_private_ips: true
  connection_timeout: 30
  read_timeout: 60
  max_redirects: 5
  rate_limit_per_stream: 1  # requests per second
  max_concurrent_connections: 10
  
  # Resource Limits
  max_cpu_time_seconds: 300
  max_memory_mb: 512
  max_temp_file_size_mb: 100
  
  # Input Validation
  max_url_length: 2048
  max_urls_per_minute: 10
  
  # TLS
  min_tls_version: "1.2"
  verify_ssl: true
  
  # Logging
  log_level: "INFO"
  log_sensitive_data: false
  encrypt_logs: true
  
  # API Security (Future)
  api_rate_limit: 100  # requests per hour per key
  api_key_rotation_days: 90
  session_timeout_minutes: 60
```

## Desktop Version Architecture

### Local Storage

**SQLite Database:**
- Lightweight, file-based database
- No server required
- Perfect for single-user desktop application
- Schema:
  ```sql
  -- Streams table
  CREATE TABLE streams (
    stream_id TEXT PRIMARY KEY,
    url TEXT UNIQUE NOT NULL,
    name TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_tested TIMESTAMP,
    test_count INTEGER DEFAULT 0
  );
  
  -- Test runs table
  CREATE TABLE test_runs (
    test_run_id TEXT PRIMARY KEY,
    stream_id TEXT NOT NULL,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    phase INTEGER NOT NULL,
    results JSON,
    FOREIGN KEY (stream_id) REFERENCES streams(stream_id)
  );
  
  -- Indexes for performance
  CREATE INDEX idx_test_runs_stream_timestamp ON test_runs(stream_id, timestamp);
  CREATE INDEX idx_test_runs_timestamp ON test_runs(timestamp);
  ```

**Local File Storage:**
- Results stored in JSON files (optional)
- Temporary audio files: System temp directory
- Automatic cleanup after test completion
- Configurable retention period

### Desktop Application Structure

```
stream_checker/
├── stream_checker.py          # Main CLI application
├── core/
│   ├── __init__.py
│   ├── connectivity.py        # Phase 1: Connectivity & metadata
│   ├── player_test.py         # Phase 2: Player testing
│   ├── audio_analysis.py      # Phase 3: Audio analysis
│   ├── ad_detection.py        # Phase 4: Ad detection
│   └── reporting.py           # Report generation
├── security/
│   ├── __init__.py
│   ├── validation.py          # Input validation
│   ├── resource_limits.py     # Resource management
│   └── key_management.py      # Key generation
├── database/
│   ├── __init__.py
│   ├── models.py              # Database models
│   └── db.py                  # Database connection
├── utils/
│   ├── __init__.py
│   ├── logging.py             # Logging configuration
│   └── config.py              # Configuration management
├── requirements.txt
├── config.yaml                # Configuration file
└── README.md
```

### Desktop Features

**Command-Line Interface:**
- Simple, intuitive CLI
- Progress indicators
- Color-coded output
- JSON or text output formats

**Local Database:**
- SQLite for result storage
- Query historical results
- Track stream testing history
- Export results to JSON/CSV

**Resource Management:**
- Process isolation per test
- Resource limits (CPU, memory, disk)
- Automatic cleanup
- Timeout handling

**No External Dependencies:**
- Runs entirely on local machine
- No cloud services required
- No internet required (except for testing streams)
- Works offline for historical data queries

### Desktop Configuration

```yaml
# config.yaml for desktop version
database:
  path: "~/.stream_checker/stream_checker.db"
  backup_enabled: true
  backup_retention_days: 30

storage:
  results_dir: "~/.stream_checker/results"
  temp_dir: "/tmp/stream_checker"
  cleanup_after_test: true
  max_temp_file_size_mb: 100

security:
  allowed_schemes: ["http", "https"]
  block_private_ips: false  # Allow local testing
  connection_timeout: 30
  read_timeout: 60
  max_url_length: 2048

resource_limits:
  max_cpu_time_seconds: 300
  max_memory_mb: 512
  max_temp_file_size_mb: 100

logging:
  level: "INFO"
  file: "~/.stream_checker/logs/stream_checker.log"
  max_file_size_mb: 10
  backup_count: 5
```

## Configuration (Desktop Version)

### Command-Line Arguments

```bash
stream_checker.py
  --url <stream_url>          # Required: Stream URL to test
  --phase <1|2|3|4>           # Optional: Specific phase (default: all)
  --silence-threshold <db>    # Optional: Silence threshold in dB (default: -40)
  --sample-duration <seconds> # Optional: Audio sample duration (default: 10)
  --output-format <json|text> # Optional: Output format (default: text)
  --test-run-id <uuid>        # Optional: Use existing test run ID (default: generate new)
  --verbose                   # Optional: Detailed logging
  --config <path>             # Optional: Path to config file
```

### Configuration File

```yaml
# config.yaml for desktop version
database:
  path: "~/.stream_checker/stream_checker.db"
  backup_enabled: true
  backup_retention_days: 30

storage:
  results_dir: "~/.stream_checker/results"
  temp_dir: "/tmp/stream_checker"
  cleanup_after_test: true
  max_temp_file_size_mb: 100

security:
  allowed_schemes: ["http", "https"]
  block_private_ips: false  # Allow local testing
  connection_timeout: 30
  read_timeout: 60
  max_url_length: 2048

resource_limits:
  max_cpu_time_seconds: 300
  max_memory_mb: 512
  max_temp_file_size_mb: 100

logging:
  level: "INFO"
  file: "~/.stream_checker/logs/stream_checker.log"
  max_file_size_mb: 10
  backup_count: 5
```

## Implementation Phases (Desktop Version)

---

```
┌─────────────────────────────────────────────────────────────┐
│                    Internet / Users                         │
└───────────────────────┬─────────────────────────────────────┘
                        │
                        ▼
            ┌───────────────────────┐
            │   CloudFront CDN      │  (Static assets, caching)
            └───────────┬───────────┘
                        │
                        ▼
            ┌───────────────────────┐
            │   API Gateway         │  (API routing, rate limiting)
            └───────────┬───────────┘
                        │
        ┌───────────────┴───────────────┐
        │                               │
        ▼                               ▼
┌───────────────┐              ┌───────────────┐
│  ALB          │              │  ALB          │
│  (Web)        │              │  (API)        │
└───────┬───────┘              └───────┬───────┘
        │                               │
        ▼                               ▼
┌──────────────────────────┐   ┌──────────────────────────┐
│  ECS/EKS Cluster        │   │  │  ECS/EKS Cluster       │
│  (Web Dashboard)        │   │  │  (API Workers)        │
│  - Auto Scaling         │   │  │  - Auto Scaling       │
│  - Multi-AZ             │   │  │  - Multi-AZ           │
└──────────────────────────┘   └───────────┬──────────────┘
                                           │
                                           ▼
                                  ┌─────────────────┐
                                  │  SQS Queue      │  (Test jobs)
                                  │  - DLQ          │
                                  └────────┬────────┘
                                           │
                                           ▼
                                  ┌─────────────────┐
                                  │  ECS/EKS        │
                                  │  (Test Workers) │
                                  │  - Auto Scaling │
                                  │  - Spot Instances│
                                  └─────────────────┘
                                           │
        ┌──────────────────────────────────┼──────────────────┐
        │                                  │                  │
        ▼                                  ▼                  ▼
┌───────────────┐              ┌───────────────┐   ┌───────────────┐
│  RDS          │              │  ElastiCache  │   │  S3           │
│  (PostgreSQL) │              │  (Redis)      │   │  (Results)    │
│  - Multi-AZ   │              │  - Cluster    │   │  - Versioning │
│  - Read Replicas│            │  - Replication│   │  - Lifecycle  │
└───────────────┘              └───────────────┘   └───────────────┘
        │
        ▼
┌───────────────┐
│  CloudWatch   │  (Monitoring, Logs, Alarms)
│  - Logs       │
│  - Metrics    │
│  - Alarms     │
└───────────────┘
```

### Scalability Features

#### 1. Horizontal Scaling

**Worker Auto-Scaling:**
- **ECS/EKS Auto Scaling**: Scale workers based on SQS queue depth
- **Scaling Policy**:
  - Scale up when queue depth > 100 messages
  - Scale down when queue depth < 10 messages
  - Min workers: 2, Max workers: 100
  - Target: 50% CPU utilization, 70% memory utilization

**API Auto-Scaling:**
- **Application Load Balancer (ALB)**: Distribute API requests
- **Target Group Auto Scaling**: Scale API servers based on:
  - Request count per target
  - Average response time
  - CPU/memory utilization
- **Min instances**: 2, **Max instances**: 50

**Database Scaling:**
- **RDS Read Replicas**: 2-5 read replicas for query distribution
- **Connection Pooling**: PgBouncer or RDS Proxy
- **Read/Write Splitting**: Route reads to replicas, writes to primary
- **Vertical Scaling**: Upgrade instance types as needed

#### 2. Queue-Based Architecture

**Amazon SQS Configuration:**
- **Standard Queue**: For test job distribution
- **Dead Letter Queue (DLQ)**: For failed jobs after 3 retries
- **Visibility Timeout**: 5 minutes (max test duration)
- **Message Retention**: 14 days
- **Batch Processing**: Process up to 10 messages per worker

**Queue Management:**
- **Priority Queues**: Separate queues for urgent vs. scheduled tests
- **FIFO Queues**: For ordered processing (if needed)
- **Queue Monitoring**: CloudWatch metrics for queue depth, age

**Job Distribution:**
- **Round-Robin**: Distribute jobs evenly across workers
- **Stream Affinity**: Optionally route same stream to same worker (caching)
- **Load Balancing**: Distribute based on worker capacity

#### 3. Caching Strategy

**ElastiCache (Redis) Configuration:**
- **Cluster Mode**: Multi-node cluster for high availability
- **Replication**: Automatic replication across AZs
- **TTL Strategy**:
  - Stream metadata: 1 hour
  - Test results: 15 minutes
  - Customer config: 5 minutes
  - API responses: 30 seconds

**Cache Layers:**
1. **Application Cache**: In-memory cache for frequently accessed data
2. **Redis Cache**: Shared cache across workers
3. **CloudFront**: CDN for static assets and API responses

**Cache Invalidation:**
- **Time-based**: TTL expiration
- **Event-based**: Invalidate on stream config changes
- **Manual**: Admin-triggered invalidation

#### 4. Database Scaling

**RDS PostgreSQL Configuration:**
- **Multi-AZ Deployment**: Automatic failover
- **Read Replicas**: 2-5 replicas in different AZs
- **Instance Types**: Start with db.t3.medium, scale to db.r5.xlarge+
- **Storage**: gp3 SSD with auto-scaling (up to 64 TB)
- **Connection Pooling**: RDS Proxy (max 1,000 connections)

**Database Optimization:**
- **Indexing**: Strategic indexes on frequently queried columns
  - `test_runs(customer_id, timestamp)`
  - `test_runs(stream_id, timestamp)`
  - `streams(customer_id)`
- **Partitioning**: Partition `test_runs` table by date (monthly)
- **Archival**: Move old data (>90 days) to S3/Glacier
- **Vacuuming**: Automated VACUUM and ANALYZE

**Connection Management:**
- **Connection Pooling**: PgBouncer or RDS Proxy
- **Max Connections**: Configure based on instance size
- **Connection Timeout**: 30 seconds
- **Query Timeout**: 60 seconds

#### 5. Stateless Design

**Application Statelessness:**
- **No Local State**: All state in database/cache
- **Session Storage**: Redis for sessions (not local memory)
- **File Storage**: S3 for temporary files, not local disk
- **Configuration**: Environment variables or Parameter Store

**Worker Statelessness:**
- **No Persistent Connections**: Each test is independent
- **Temporary Files**: Use S3 or ephemeral storage only
- **Cleanup**: Automatic cleanup after test completion

### Fault Tolerance Features

#### 1. Retry Mechanisms

**Exponential Backoff:**
- **Initial Delay**: 1 second
- **Max Delay**: 60 seconds
- **Max Retries**: 3 attempts
- **Backoff Multiplier**: 2x per retry
- **Jitter**: Random 0-25% to prevent thundering herd

**Retryable Operations:**
- Network requests (connection failures)
- Database operations (transient errors)
- S3 operations (temporary failures)
- Queue operations (visibility timeout)

**Non-Retryable Operations:**
- Authentication failures
- Invalid input validation
- Permanent errors (404, 403)

#### 2. Circuit Breaker Pattern

**Circuit Breaker States:**
- **Closed**: Normal operation
- **Open**: Failing, reject requests immediately
- **Half-Open**: Testing if service recovered

**Configuration:**
- **Failure Threshold**: 5 failures in 60 seconds
- **Timeout**: 30 seconds before attempting half-open
- **Success Threshold**: 2 successful requests to close

**Implementation:**
- Use `pybreaker` or custom implementation
- Per-stream circuit breakers
- Per-external-service circuit breakers

#### 3. Health Checks

**Application Health Checks:**
- **Liveness Probe**: Is application running?
  - Endpoint: `/health/live`
  - Check: Process alive, can respond
  - Interval: 30 seconds
  - Timeout: 5 seconds

- **Readiness Probe**: Is application ready?
  - Endpoint: `/health/ready`
  - Check: Database connected, cache accessible, queue accessible
  - Interval: 10 seconds
  - Timeout: 5 seconds

- **Startup Probe**: Is application starting?
  - Endpoint: `/health/startup`
  - Check: Initial setup complete
  - Interval: 5 seconds
  - Timeout: 10 seconds

**Infrastructure Health Checks:**
- **ALB Health Checks**: Route traffic only to healthy targets
- **ECS Service Health**: Automatic task replacement on failure
- **RDS Health**: Multi-AZ automatic failover
- **ElastiCache Health**: Automatic failover to replica

#### 4. Graceful Degradation

**Degradation Strategies:**
- **Cache-Only Mode**: Serve cached results if database unavailable
- **Read-Only Mode**: Disable writes if database primary fails
- **Reduced Functionality**: Skip non-critical phases if resources limited
- **Queue Throttling**: Reduce test frequency during high load

**Priority Levels:**
1. **Critical**: Connectivity tests (Phase 1)
2. **High**: Player tests (Phase 2)
3. **Medium**: Audio analysis (Phase 3)
4. **Low**: Ad detection (Phase 4)

#### 5. Redundancy & High Availability

**Multi-AZ Deployment:**
- **All Services**: Deploy across at least 2 Availability Zones
- **Database**: Multi-AZ with automatic failover (< 60 seconds)
- **Cache**: Redis cluster mode (automatic failover)
- **Load Balancers**: Cross-AZ load balancing

**Data Redundancy:**
- **Database Backups**: Automated daily backups, 30-day retention
- **S3 Versioning**: Enable versioning for result storage
- **Cross-Region Replication**: Optional for disaster recovery
- **Point-in-Time Recovery**: RDS PITR for last 7 days

#### 6. Disaster Recovery

**Recovery Time Objective (RTO)**: 1 hour
**Recovery Point Objective (RPO)**: 15 minutes

**Backup Strategy:**
- **Database**: Automated daily snapshots + continuous backups
- **Configuration**: Version control (Git) + Parameter Store
- **Results**: S3 with versioning and cross-region replication
- **Backup Testing**: Monthly restore tests

**Disaster Recovery Plan:**
1. **Detection**: CloudWatch alarms trigger DR procedures
2. **Failover**: Automated failover to secondary region (if configured)
3. **Restore**: Restore from backups in secondary region
4. **Validation**: Verify system functionality
5. **Communication**: Notify customers of service disruption

#### 7. Error Handling & Monitoring

**Error Classification:**
- **Transient Errors**: Retry with exponential backoff
- **Permanent Errors**: Log and alert, don't retry
- **Rate Limit Errors**: Back off and retry
- **Timeout Errors**: Retry with longer timeout

**Monitoring & Alerting:**
- **CloudWatch Metrics**:
  - Queue depth, processing rate
  - Worker CPU, memory, error rate
  - Database connections, query latency
  - API request rate, latency, error rate
  - Cache hit rate, eviction rate

- **CloudWatch Alarms**:
  - High queue depth (> 1000 messages)
  - High error rate (> 5% failures)
  - Database connection exhaustion
  - Worker health check failures
  - API latency > 2 seconds

- **Logging**:
  - Centralized logging: CloudWatch Logs
  - Log aggregation: CloudWatch Logs Insights
  - Structured logging: JSON format
  - Log retention: 30 days (hot), 90 days (cold)

#### 8. Load Testing & Capacity Planning

**Load Testing:**
- **Tools**: Locust, k6, or AWS Distributed Load Testing
- **Scenarios**:
  - Normal load: 2,000 streams/hour
  - Peak load: 5,000 streams/hour
  - Stress test: 10,000 streams/hour
- **Metrics**: Response time, throughput, error rate, resource utilization

**Capacity Planning:**
- **Baseline**: 2 workers per 100 streams/hour
- **Scaling**: Add 1 worker per 50 additional streams/hour
- **Database**: 1 read replica per 1,000 streams/hour
- **Cache**: 1 node per 2,000 streams/hour

### AWS Service Recommendations

#### Compute
- **ECS Fargate**: Serverless containers (recommended for simplicity)
- **ECS EC2**: More control, cost optimization
- **EKS**: Kubernetes (if multi-cloud needed)
- **Lambda**: For lightweight operations (webhooks, notifications)

#### Storage
- **S3**: Test results, temporary files, backups
- **EBS**: Database storage (via RDS)
- **EFS**: Shared file system (if needed)

#### Database
- **RDS PostgreSQL**: Primary database
- **DynamoDB**: Optional for high-throughput use cases
- **RDS Proxy**: Connection pooling and failover

#### Caching
- **ElastiCache Redis**: Application cache
- **CloudFront**: CDN for static assets

#### Messaging
- **SQS**: Test job queue
- **SNS**: Notifications and alerts
- **EventBridge**: Scheduled events (hourly tests)

#### Monitoring
- **CloudWatch**: Metrics, logs, alarms
- **X-Ray**: Distributed tracing (optional)
- **CloudTrail**: API audit logs

#### Networking
- **VPC**: Isolated network environment
- **ALB**: Application Load Balancer
- **Route 53**: DNS and health checks
- **CloudFront**: CDN and DDoS protection

### Scalability Configuration

```yaml
scalability:
  # Worker Auto-Scaling
  workers:
    min_instances: 2
    max_instances: 100
    target_cpu: 50
    target_memory: 70
    scale_up_threshold: 100  # queue depth
    scale_down_threshold: 10
    instance_type: "t3.medium"
    spot_instances: true  # Use spot for cost savings
    
  # API Auto-Scaling
  api:
    min_instances: 2
    max_instances: 50
    target_request_count: 1000  # per target per minute
    target_response_time: 500  # ms
    instance_type: "t3.small"
    
  # Database
  database:
    instance_type: "db.t3.medium"
    read_replicas: 2
    max_connections: 500
    storage_autoscaling: true
    storage_max: 1000  # GB
    
  # Cache
  cache:
    node_type: "cache.t3.medium"
    num_nodes: 2
    replication: true
    
  # Queue
  queue:
    visibility_timeout: 300  # seconds
    message_retention: 1209600  # 14 days
    max_receive_count: 3
    batch_size: 10
```

### Fault Tolerance Configuration

```yaml
fault_tolerance:
  # Retry Configuration
  retry:
    max_attempts: 3
    initial_delay: 1  # seconds
    max_delay: 60
    backoff_multiplier: 2
    jitter: 0.25
    
  # Circuit Breaker
  circuit_breaker:
    failure_threshold: 5
    timeout: 30  # seconds
    success_threshold: 2
    
  # Health Checks
  health_check:
    liveness_interval: 30
    readiness_interval: 10
    startup_interval: 5
    timeout: 5
    
  # Graceful Degradation
  degradation:
    enable_cache_only_mode: true
    enable_read_only_mode: true
    skip_optional_phases: true
    
  # Disaster Recovery
  disaster_recovery:
    rto_minutes: 60
    rpo_minutes: 15
    backup_retention_days: 30
    cross_region_replication: false
```

### Cost Optimization

**Strategies:**
- **Spot Instances**: Use for test workers (up to 90% savings)
- **Reserved Instances**: For database and API servers (1-3 year terms)
- **Auto Scaling**: Scale down during low-traffic periods
- **S3 Lifecycle Policies**: Move old data to Glacier
- **Cache Optimization**: Reduce cache misses to lower database load
- **Right-Sizing**: Monitor and adjust instance types

**Estimated Monthly Costs (2,000 streams, hourly tests):**
- Compute (ECS): ~$200-400
- Database (RDS): ~$150-300
- Cache (ElastiCache): ~$50-100
- Storage (S3): ~$20-50
- Data Transfer: ~$50-100
- **Total**: ~$470-950/month

---

## Phase 1: Basic Stream Connectivity & Metadata Extraction

**Goal**: Verify stream is accessible and extract all available metadata and technical parameters.

### Features

1. **Stream Connectivity**
   - HTTP/HTTPS connection test
   - Response time measurement
   - HTTP status code validation
   - Connection timeout handling

2. **SSL/TLS Certificate Validation**
   - Certificate validity check
   - Expiration date extraction
   - Days until expiration calculation
   - Certificate chain validation
   - Self-signed certificate detection

3. **Stream Parameters Extraction**
   - **Bitrate** (kbps)
   - **Codec** (MP3, AAC, etc.)
   - **Sample Rate** (Hz)
   - **Channels** (Mono, Stereo, etc.)
   - **Container Format** (if applicable)

4. **Stream Type Identification**
   - **Stream Protocol/Type** identification and reporting
   - Detect and report stream server type:
     - **Icecast** (detected via ICY headers and Server header)
     - **Shoutcast** (detected via ICY headers and Server header)
     - **ICY Stream** (generic ICY-compatible stream)
     - **HLS** (HTTP Live Streaming - detected via playlist format)
     - **Direct HTTP/HTTPS** (standard HTTP audio stream)
     - **Unknown/Other** (if type cannot be determined)
   - Detection methods:
     - ICY metadata headers (`icy-*` headers indicate ICY-compatible streams)
     - Server header analysis (e.g., "Icecast 2.4.0", "SHOUTcast")
     - Content-Type and URL pattern analysis
     - HLS playlist detection (`.m3u8` extension or playlist format)
   - Report stream type in results for user visibility

5. **Stream Metadata Extraction**
   - Stream title
   - Genre
   - Artist/Station name
   - Description
   - URL
   - Any ICY metadata (for Icecast/Shoutcast)

6. **Server Headers Analysis**
   - Content-Type validation
   - CORS headers presence
   - Cache-Control headers
   - Server identification
   - Content-Length (if available)

7. **HLS-Specific Checks**
   - Playlist parsing
   - Segment availability
   - Master playlist validation
   - Variant stream detection

### Output Format

```json
{
  "test_run_id": "550e8400-e29b-41d4-a716-446655440000",
  "stream_id": "a1b2c3d4e5f6g7h8",
  "stream_url": "https://example.com/stream.mp3",
  "timestamp": "2026-01-23T10:00:00Z",
  "phase": 1,
  "connectivity": {
    "status": "success",
    "response_time_ms": 245,
    "http_status": 200,
    "content_type": "audio/mpeg"
  },
  "ssl_certificate": {
    "valid": true,
    "expires": "2026-12-31T23:59:59Z",
    "days_until_expiration": 342,
    "issuer": "Let's Encrypt",
    "self_signed": false
  },
  "stream_parameters": {
    "bitrate_kbps": 128,
    "codec": "MP3",
    "sample_rate_hz": 44100,
    "channels": "stereo",
    "container": "MP3"
  },
  "stream_type": {
    "type": "Icecast",
    "detected_via": ["icy_headers", "server_header"],
    "server_version": "Icecast 2.4.0"
  },
  "metadata": {
    "title": "Example Radio Station",
    "genre": "Pop",
    "artist": "Radio Station Name",
    "description": "Stream description"
  },
  "server_headers": {
    "server": "Icecast 2.4.0",
    "cors_enabled": false,
    "cache_control": "no-cache"
  },
  "hls_info": null
}
```

### Test Command

```bash
python stream_checker.py --url "https://example.com/stream.mp3" --phase 1
```

### Success Criteria

- Successfully connects to stream
- Extracts all available technical parameters
- Identifies and reports stream type (Icecast/Shoutcast/ICY/HLS/Direct HTTP)
- Validates SSL certificate (if HTTPS)
- Parses stream metadata
- Handles connection errors gracefully

---

## Phase 2: Player Connectivity Testing

**Goal**: Verify that actual media players can successfully connect to and play the stream.

### Features

1. **VLC Player Testing**
   - Launch VLC in headless mode
   - Attempt to open stream URL
   - Monitor connection status
   - Measure time to first audio packet
   - Detect playback errors
   - Capture VLC error messages
   - Test playback duration (minimum 5 seconds)

2. **Connection Quality Metrics**
   - Time to establish connection
   - Buffering events
   - Packet loss detection (if possible)
   - Stream stability over test duration

3. **Stream Format Validation**
   - Verify player can decode stream
   - Confirm codec compatibility
   - Check for format errors

### Output Format

```json
{
  "test_run_id": "550e8400-e29b-41d4-a716-446655440000",
  "stream_id": "a1b2c3d4e5f6g7h8",
  "stream_url": "https://example.com/stream.mp3",
  "timestamp": "2026-01-23T10:00:00Z",
  "phase": 2,
  "player_tests": {
    "vlc": {
      "status": "success",
      "connection_time_ms": 1200,
      "playback_duration_seconds": 5,
      "errors": [],
      "buffering_events": 0,
      "format_supported": true
    }
  },
  "connection_quality": {
    "stable": true,
    "packet_loss_detected": false
  }
}
```

### Test Command

```bash
python stream_checker.py --url "https://example.com/stream.mp3" --phase 2
```

### Success Criteria

- VLC successfully connects and plays stream
- Captures connection timing metrics
- Detects and reports playback failures
- Handles player crashes gracefully

### Dependencies

- VLC media player installed on system
- `python-vlc` library

---

## Phase 3: Audio Analysis - Silence & Error Detection

**Goal**: Sample stream audio to detect silence periods and error messages.

### Features

1. **Audio Sampling**
   - Download/capture 10 seconds of audio
   - Use ffmpeg for audio extraction
   - Support MP3, AAC, and HLS formats

2. **Silence Detection**
   - Analyze audio amplitude levels
   - Detect silence periods (> 2 seconds)
   - Calculate silence percentage
   - Threshold: RMS amplitude < -40 dB (configurable)
   - Report silence duration and location

3. **Error Message Detection**
   - Audio-to-text transcription (optional, using speech recognition)
   - Pattern matching for common error phrases:
     - "Stream unavailable"
     - "Connection error"
     - "Service temporarily unavailable"
     - "404 Not Found" (if spoken)
   - Detect repetitive error audio patterns

4. **Audio Quality Metrics**
   - Average volume level
   - Peak volume level
   - Dynamic range
   - Audio clipping detection

### Silence Threshold

**Recommended**: RMS amplitude < -40 dB for > 2 seconds
- This threshold can be adjusted based on testing
- Accounts for background noise in live streams
- Configurable via command-line parameter

### Output Format

```json
{
  "test_run_id": "550e8400-e29b-41d4-a716-446655440000",
  "stream_id": "a1b2c3d4e5f6g7h8",
  "stream_url": "https://example.com/stream.mp3",
  "timestamp": "2026-01-23T10:00:00Z",
  "phase": 3,
  "audio_analysis": {
    "sample_duration_seconds": 10,
    "silence_detection": {
      "silence_detected": false,
      "silence_percentage": 0.0,
      "silence_periods": [],
      "threshold_db": -40
    },
    "error_detection": {
      "error_detected": false,
      "error_messages": [],
      "repetitive_pattern_detected": false
    },
    "audio_quality": {
      "average_volume_db": -12.5,
      "peak_volume_db": -3.2,
      "dynamic_range_db": 9.3,
      "clipping_detected": false
    }
  }
}
```

### Test Command

```bash
python stream_checker.py --url "https://example.com/stream.mp3" --phase 3 --silence-threshold -40
```

### Success Criteria

- Successfully samples 10 seconds of audio
- Accurately detects silence periods
- Identifies common error messages
- Provides audio quality metrics
- Handles unsupported formats gracefully

### Dependencies

- `ffmpeg` installed on system
- `pydub` library for audio analysis
- `numpy` for audio processing
- Optional: `speech_recognition` for error message detection

---

## Phase 4: Ad Detection & Enhanced Reporting

**Goal**: Detect advertising markers and provide comprehensive reporting.

### Features

1. **Ad Marker Detection via Metadata**
   - Monitor ICY metadata for ad markers
   - Detect common ad metadata patterns:
     - Title changes to "Commercial" / "Advertisement"
     - Genre field changes
     - Custom ad markers in metadata
   - Track ad break start/end times
   - Calculate ad break duration

2. **Ad Pattern Recognition**
   - Identify repetitive metadata patterns
   - Detect scheduled ad breaks
   - Track ad frequency

3. **Enhanced Reporting**
   - Combine all phase results
   - Generate comprehensive health report
   - Calculate overall stream health score
   - Identify issues and recommendations

4. **Terminal Output Formatting**
   - Color-coded status indicators
   - Summary table view
   - Detailed section breakdown
   - Progress indicators during testing

### Output Format

```json
{
  "test_run_id": "550e8400-e29b-41d4-a716-446655440000",
  "stream_id": "a1b2c3d4e5f6g7h8",
  "stream_url": "https://example.com/stream.mp3",
  "timestamp": "2026-01-23T10:00:00Z",
  "phase": 4,
  "ad_detection": {
    "ads_detected": true,
    "ad_breaks": [
      {
        "start_time": "2026-01-23T10:05:00Z",
        "end_time": "2026-01-23T10:05:30Z",
        "duration_seconds": 30,
        "detection_method": "metadata_marker"
      }
    ],
    "total_ad_time_seconds": 30,
    "ad_frequency_per_hour": 12
  },
  "health_score": 95,
  "issues": [],
  "recommendations": []
}
```

### Terminal Output Example

```
╔══════════════════════════════════════════════════════════════╗
║           Stream Health Check Report                         ║
╚══════════════════════════════════════════════════════════════╝

Test Run ID: 550e8400-e29b-41d4-a716-446655440000
Stream ID:   a1b2c3d4e5f6g7h8
Stream URL:  https://example.com/stream.mp3
Test Time:   2026-01-23 10:00:00 UTC
Overall Health Score: 95/100

┌─ Connectivity ──────────────────────────────────────────────┐
│ Status:        ✓ SUCCESS                                     │
│ Response Time: 245 ms                                        │
│ HTTP Status:   200 OK                                        │
└──────────────────────────────────────────────────────────────┘

┌─ SSL Certificate ───────────────────────────────────────────┐
│ Valid:         ✓ YES                                         │
│ Expires:       2026-12-31 (342 days)                         │
│ Issuer:        Let's Encrypt                                 │
└──────────────────────────────────────────────────────────────┘

┌─ Stream Parameters ─────────────────────────────────────────┐
│ Bitrate:       128 kbps                                      │
│ Codec:         MP3                                           │
│ Sample Rate:   44100 Hz                                      │
│ Channels:      Stereo                                       │
└──────────────────────────────────────────────────────────────┘

┌─ Player Tests ──────────────────────────────────────────────┐
│ VLC:           ✓ SUCCESS (1.2s connection)                  │
└──────────────────────────────────────────────────────────────┘

┌─ Audio Analysis ─────────────────────────────────────────────┐
│ Silence:       ✗ NONE DETECTED                               │
│ Errors:        ✗ NONE DETECTED                               │
│ Avg Volume:    -12.5 dB                                      │
└──────────────────────────────────────────────────────────────┘

┌─ Ad Detection ───────────────────────────────────────────────┐
│ Ads Detected:  ✓ YES (12 per hour)                          │
│ Avg Duration:  30 seconds                                   │
└──────────────────────────────────────────────────────────────┘
```

### Test Command

```bash
python stream_checker.py --url "https://example.com/stream.mp3" --phase 4
```

### Success Criteria

- Detects ad markers in stream metadata
- Calculates ad break durations accurately
- Generates comprehensive health report
- Provides clear terminal output
- Combines all previous phase results

## Future Service Architecture

### Scale Requirements
- **Streams**: 2,000 streams (2 per customer × 1,000 customers)
- **Testing Frequency**: Hourly
- **Tests per Day**: 48,000 tests
- **Tests per Month**: ~1.44 million tests
- **Peak Load**: 5,000+ concurrent tests during peak hours
- **API Requests**: 100,000+ requests/day

### Service Components

1. **Scheduler Service**
   - AWS EventBridge for scheduled events (hourly triggers)
   - SQS queue for test job distribution
   - Distribute tests across time to avoid spikes
   - Retry logic with exponential backoff
   - Dead Letter Queue for failed jobs
   - Auto-scaling based on queue depth

2. **Database (RDS PostgreSQL)**
   - Multi-AZ deployment for high availability
   - Read replicas for query distribution
   - Automated backups with point-in-time recovery
   - Partitioned tables for performance
   - Data archival to S3 for old results
   - Connection pooling via RDS Proxy

3. **Web Dashboard**
   - React/Vue.js frontend
   - Served via CloudFront CDN
   - Real-time updates via WebSockets
   - Historical charts and graphs
   - Alert management interface
   - Customer account management
   - Auto-scaling ECS/EKS cluster

4. **Notification System**
   - AWS SNS for email/SMS alerts
   - Configurable alert thresholds per customer
   - Webhook support for integrations
   - Retry logic for failed notifications
   - Notification preferences per customer

5. **API (RESTful)**
   - API Gateway for routing and rate limiting
   - Application Load Balancer for distribution
   - Auto-scaling API workers
   - API key authentication
   - Rate limiting per customer
   - Webhook endpoints
   - Comprehensive API documentation

6. **Security Service**
   - API key management and rotation
   - Authentication service (JWT tokens)
   - Rate limiting service (per customer/IP)
   - Security monitoring and alerting
   - Audit log aggregation (CloudTrail)
   - DDoS protection (AWS Shield)

7. **Test Execution Workers**
   - ECS/EKS cluster for test workers
   - Auto-scaling based on queue depth
   - Spot instances for cost optimization
   - Multi-AZ deployment
   - Health checks and automatic replacement
   - Resource limits per worker

8. **Caching Layer (ElastiCache Redis)**
   - Cluster mode for high availability
   - Multi-AZ replication
   - Cache stream metadata and recent results
   - Session storage
   - Rate limiting counters
   - Auto-scaling cache nodes

9. **Storage (S3)**
   - Test result storage (JSON files)
   - Temporary file storage
   - Database backup storage
   - Lifecycle policies (move to Glacier after 90 days)
   - Versioning enabled
   - Cross-region replication (optional)

10. **Monitoring & Observability**
    - CloudWatch for metrics and logs
    - Custom dashboards for key metrics
    - Automated alarms for critical issues
    - Distributed tracing (optional: X-Ray)
    - Log aggregation and analysis
    - Performance monitoring

### Deployment Architecture

**Primary Region (us-east-1):**
- All services deployed in Multi-AZ
- Primary database with read replicas
- Active workers and API servers

**Secondary Region (us-west-2) - Optional:**
- Standby database replica
- Disaster recovery capability
- Can activate within 1 hour (RTO)

### High Availability Design

- **No Single Points of Failure**: All services Multi-AZ
- **Automatic Failover**: Database, cache, load balancers
- **Health Checks**: Continuous monitoring and auto-recovery
- **Graceful Degradation**: System continues with reduced functionality
- **Circuit Breakers**: Prevent cascading failures

### Scalability Design

- **Horizontal Scaling**: All compute services auto-scale
- **Queue-Based**: Decoupled architecture for independent scaling
- **Caching**: Reduce database load
- **Read Replicas**: Distribute database queries
- **CDN**: Reduce origin server load

See **Scalability & Fault Tolerance** section below for detailed architecture and configuration.

---

## Scalability & Fault Tolerance (AWS)

> **Note**: This section describes AWS-specific scalability and fault tolerance features for the future cloud deployment. These are not required for the desktop version.

### Design Principles

1. **Horizontal Scaling**: Design for stateless workers that can scale horizontally
2. **Queue-Based Architecture**: Decouple test execution from API requests
3. **Idempotency**: All operations must be idempotent (safe to retry)
4. **Graceful Degradation**: System continues operating with reduced functionality during failures
5. **Circuit Breakers**: Prevent cascading failures
6. **Health Checks**: Continuous monitoring of system health
7. **Redundancy**: No single points of failure

### AWS Architecture Overview

## Error Handling

- Network timeouts: 30 seconds default
- Invalid URLs: Clear error messages
- Unsupported formats: Graceful degradation
- Missing dependencies: Installation instructions
- Player failures: Detailed error reporting

---

## Testing Strategy

Each phase should be independently testable with:
- Valid working streams
- Invalid/broken streams
- Streams with known issues (expired certs, silence, etc.)
- Different stream formats (MP3, AAC, HLS)

### Security Testing

- **Input Validation Testing:**
  - Malformed URLs
  - Injection attempts (SQL, command, path traversal)
  - Extremely long URLs
  - Private IP addresses
  - Invalid schemes

- **Resource Limit Testing:**
  - Memory exhaustion attempts
  - CPU-intensive operations
  - Large file downloads
  - Concurrent connection limits

- **Authentication Testing:**
  - Invalid API keys
  - Expired keys
  - Brute force attempts
  - Session hijacking attempts

- **Network Security Testing:**
  - SSL/TLS version enforcement
  - Certificate validation
  - Connection timeout handling
  - Rate limiting effectiveness

- **Dependency Vulnerability Testing:**
  - Regular `pip-audit` scans
  - `safety` checks
  - Automated dependency updates

---

## Dependencies Installation

```bash
pip install requests httpx mutagen eyed3 ffmpeg-python pydub numpy python-vlc cryptography bcrypt python-dotenv
```

**Security-related dependencies:**
- `cryptography` - SSL/TLS, encryption
- `bcrypt` - Password/API key hashing
- `python-dotenv` - Secure configuration management
- `bandit` - Security linting (dev dependency)
- `safety` - Dependency vulnerability scanning (dev dependency)

System dependencies:
- VLC media player
- ffmpeg

**Security Tools (Development):**
```bash
pip install bandit safety pip-audit
```

---

## Development Roadmap

### Desktop Version (Initial Implementation)

1. **Week 1-2**: Phase 1 implementation
   - Basic connectivity and metadata extraction
   - Key management system (test_run_id, stream_id)
   - Security: Input validation, URL sanitization
   - Local SQLite database for results

2. **Week 3**: Phase 2 implementation
   - VLC player testing
   - Error handling and retry logic
   - Security: Resource limits, process isolation

3. **Week 4**: Phase 3 implementation
   - Audio analysis (silence, error detection)
   - Security: Secure file handling, cleanup

4. **Week 5**: Phase 4 implementation
   - Ad detection
   - Enhanced reporting
   - Security: Secure logging, audit trails

5. **Week 6**: Testing, bug fixes, documentation
   - Security testing
   - Performance testing
   - Documentation

---

## Future: AWS Deployment

> **Note**: This section describes the future cloud deployment architecture. The desktop version should be fully implemented first (Phases 1-4). AWS deployment is Phase 5+ and can be implemented after the desktop version is stable and tested.

### Service Version (AWS Deployment) - Phase 5+

**Prerequisites**: Desktop version (Phases 1-4) must be complete and tested.

6. **Week 7-8**: Infrastructure Setup
   - AWS account setup and IAM configuration
   - VPC and networking setup
   - RDS database setup (Multi-AZ)
   - S3 buckets and lifecycle policies
   - ElastiCache Redis cluster

7. **Week 9-10**: Queue & Worker System
   - SQS queue setup
   - ECS/EKS cluster configuration
   - Worker auto-scaling setup
   - Health checks and monitoring
   - Circuit breaker implementation

8. **Week 11-12**: API & Web Dashboard
   - API Gateway setup
   - RESTful API implementation
   - Web dashboard (React/Vue.js)
   - Authentication and authorization
   - Rate limiting

9. **Week 13-14**: Scheduler & Notifications
   - EventBridge scheduled events
   - SNS notification system
   - Alert configuration
   - Webhook support

10. **Week 15-16**: Monitoring & Optimization
    - CloudWatch dashboards
    - Alarms and alerting
    - Performance optimization
    - Cost optimization
    - Load testing

11. **Week 17+**: Production Hardening
    - Security audit
    - Penetration testing
    - Disaster recovery testing
    - Documentation
    - Customer onboarding process

---

## Notes

- All phases should be backward compatible (can run previous phases)
- Each phase builds upon previous phases
- Results should be cacheable to avoid redundant tests
- Privacy: No audio content should be stored permanently (only analysis results)

### Desktop Version Notes

- All phases should be backward compatible (can run previous phases)
- Each phase builds upon previous phases
- Results stored locally in SQLite database
- No cloud dependencies required
- Can run completely offline (except for testing streams)
- Designed to be portable and easy to run on any macOS/Linux/Windows machine

### Future Migration Considerations

When ready to migrate to AWS (Phase 5+), the desktop version is designed with:
- **Stateless Design**: All state in database, ready for cloud deployment
- **Idempotency**: All operations are idempotent for safe retries
- **Key Management**: Already uses test_run_id and stream_id for tracking
- **Modular Architecture**: Easy to extract components for cloud deployment

See **"Future: AWS Deployment"** section below for cloud architecture details.
