# AWS Deployment Guide - Stream Checker Web Service

## Overview

This guide outlines the steps to deploy the Stream Checker application to AWS with a public web interface that allows users to input stream URLs and view results.

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                    Public Users                             │
└───────────────────────┬─────────────────────────────────────┘
                        │
                        ▼
            ┌───────────────────────┐
            │   CloudFront CDN      │  (Optional: DDoS protection, caching)
            └───────────┬───────────┘
                        │
                        ▼
            ┌───────────────────────┐
            │   API Gateway         │  (Public API endpoint)
            └───────────┬───────────┘
                        │
                        ▼
        ┌───────────────┴───────────────┐
        │                               │
        ▼                               ▼
┌───────────────┐              ┌───────────────┐
│  ALB          │              │  SQS Queue     │
│  (Web App)    │              │  (Test Jobs)  │
└───────┬───────┘              └───────┬───────┘
        │                               │
        ▼                               ▼
┌──────────────────────────┐   ┌──────────────────────────┐
│  ECS/EKS Cluster        │   │  ECS/EKS Cluster        │
│  (Web Dashboard)        │   │  (Test Workers)         │
│  - React/Vue.js         │   │  - Stream Checker       │
│  - Auto Scaling         │   │  - Auto Scaling         │
└──────────────────────────┘   └──────────────────────────┘
                                           │
        ┌──────────────────────────────────┼──────────────────┐
        │                                  │                  │
        ▼                                  ▼                  ▼
┌───────────────┐              ┌───────────────┐   ┌───────────────┐
│  RDS          │              │  ElastiCache   │   │  S3           │
│  (PostgreSQL) │              │  (Redis)      │   │  (Results)    │
└───────────────┘              └───────────────┘   └───────────────┘
```

## Deployment Steps & Difficulty Levels

### Phase 1: Infrastructure Setup (Difficulty: ⭐⭐⭐ Medium)

**Estimated Time:** 2-3 days

#### Step 1.1: AWS Account & IAM Setup
- **Difficulty:** ⭐ Easy
- **Time:** 1-2 hours
- **Tasks:**
  - Create AWS account (if needed)
  - Set up IAM users/roles with appropriate permissions
  - Configure AWS CLI credentials
  - Set up billing alerts
- **Tools:** AWS Console, AWS CLI

#### Step 1.2: VPC & Networking
- **Difficulty:** ⭐⭐ Medium
- **Time:** 2-3 hours
- **Tasks:**
  - Create VPC with public/private subnets (2-3 AZs)
  - Set up Internet Gateway
  - Configure NAT Gateway (for private subnets)
  - Set up Security Groups
  - Configure Route Tables
- **Tools:** AWS Console, Terraform (optional)
- **Cost:** ~$32/month (NAT Gateway)

#### Step 1.3: Database Setup (RDS PostgreSQL)
- **Difficulty:** ⭐⭐ Medium
- **Time:** 1-2 hours
- **Tasks:**
  - Create RDS PostgreSQL instance (Multi-AZ)
  - Configure security groups
  - Set up automated backups
  - Create database schema (migrate from SQLite)
  - Set up RDS Proxy (for connection pooling)
- **Tools:** AWS Console, psql, migration scripts
- **Cost:** ~$150-300/month (db.t3.medium Multi-AZ)

#### Step 1.4: ElastiCache Redis
- **Difficulty:** ⭐⭐ Medium
- **Time:** 1 hour
- **Tasks:**
  - Create ElastiCache Redis cluster
  - Configure security groups
  - Set up replication
- **Tools:** AWS Console
- **Cost:** ~$50-100/month

#### Step 1.5: S3 Buckets
- **Difficulty:** ⭐ Easy
- **Time:** 30 minutes
- **Tasks:**
  - Create S3 buckets (results, backups, static assets)
  - Configure bucket policies
  - Set up lifecycle policies
  - Enable versioning
- **Tools:** AWS Console, AWS CLI
- **Cost:** ~$5-20/month

---

### Phase 2: Application Containerization (Difficulty: ⭐⭐ Medium)

**Estimated Time:** 1-2 days

#### Step 2.1: Dockerize Application
- **Difficulty:** ⭐⭐ Medium
- **Time:** 4-6 hours
- **Tasks:**
  - Create Dockerfile for stream checker
  - Install system dependencies (VLC, ffmpeg)
  - Configure environment variables
  - Test container locally
- **Files to create:**
  - `Dockerfile`
  - `docker-compose.yml` (for local testing)
  - `.dockerignore`
- **Challenges:**
  - VLC installation in container
  - ffmpeg installation
  - Audio processing in container

#### Step 2.2: Create ECR Repository
- **Difficulty:** ⭐ Easy
- **Time:** 30 minutes
- **Tasks:**
  - Create ECR repository
  - Push Docker image
  - Set up CI/CD pipeline (optional)
- **Tools:** AWS Console, Docker

---

### Phase 3: Queue & Worker System (Difficulty: ⭐⭐⭐ Medium-Hard)

**Estimated Time:** 2-3 days

#### Step 3.1: SQS Queue Setup
- **Difficulty:** ⭐⭐ Medium
- **Time:** 2-3 hours
- **Tasks:**
  - Create SQS standard queue
  - Create Dead Letter Queue (DLQ)
  - Configure message retention
  - Set up CloudWatch alarms
- **Tools:** AWS Console, boto3

#### Step 3.2: ECS/EKS Cluster for Workers
- **Difficulty:** ⭐⭐⭐ Medium-Hard
- **Time:** 1-2 days
- **Tasks:**
  - Create ECS cluster (Fargate recommended)
  - Define task definitions
  - Configure auto-scaling
  - Set up health checks
  - Configure logging (CloudWatch)
- **Tools:** AWS Console, ECS CLI, Terraform
- **Cost:** ~$50-200/month (depending on usage)

#### Step 3.3: Worker Application Updates
- **Difficulty:** ⭐⭐ Medium
- **Time:** 4-6 hours
- **Tasks:**
  - Modify application to read from SQS
  - Add result storage to S3
  - Update database connection (RDS)
  - Add Redis caching
  - Implement retry logic
  - Add error handling
- **Code changes needed:**
  - New module: `stream_checker/workers/sqs_worker.py`
  - Update database models for RDS
  - Add S3 result storage

---

### Phase 4: Web Application (Difficulty: ⭐⭐⭐⭐ Hard)

**Estimated Time:** 3-5 days

#### Step 4.1: Frontend Development
- **Difficulty:** ⭐⭐⭐ Medium
- **Time:** 2-3 days
- **Tasks:**
  - Choose framework (React recommended)
  - Create UI components:
    - Stream input form
    - Results display
    - Status indicators
    - Historical charts
  - Set up routing
  - Add real-time updates (WebSockets or polling)
- **Tech Stack Options:**
  - React + TypeScript (recommended)
  - Vue.js
  - Next.js (for SSR)
- **Files to create:**
  - Frontend application structure
  - API client library
  - UI components

#### Step 4.2: Backend API
- **Difficulty:** ⭐⭐⭐ Medium
- **Time:** 1-2 days
- **Tasks:**
  - Create REST API (Flask/FastAPI)
  - Endpoints:
    - `POST /api/streams/check` - Submit stream for testing
    - `GET /api/streams/{stream_id}/results` - Get results
    - `GET /api/streams/{stream_id}/history` - Get history
  - Add input validation
  - Implement rate limiting
  - Add authentication (optional for public)
- **Tech Stack:**
  - FastAPI (recommended - async, fast, auto-docs)
  - Flask (simpler, more familiar)
- **Files to create:**
  - `api/app.py` - Main API application
  - `api/routes/` - API endpoints
  - `api/models/` - Data models

#### Step 4.3: API Gateway Setup
- **Difficulty:** ⭐⭐ Medium
- **Time:** 2-3 hours
- **Tasks:**
  - Create API Gateway REST API
  - Configure routes
  - Set up CORS
  - Configure rate limiting
  - Set up API keys (optional)
- **Tools:** AWS Console, Terraform

#### Step 4.4: Application Load Balancer
- **Difficulty:** ⭐⭐ Medium
- **Time:** 1-2 hours
- **Tasks:**
  - Create ALB
  - Configure target groups
  - Set up health checks
  - Configure SSL certificate (ACM)
- **Cost:** ~$16/month (ALB)

---

### Phase 5: Security & Public Access (Difficulty: ⭐⭐⭐ Medium-Hard)

**Estimated Time:** 2-3 days

#### Step 5.1: Public Access Security
- **Difficulty:** ⭐⭐⭐ Medium-Hard
- **Time:** 1-2 days
- **Tasks:**
  - Implement rate limiting per IP
  - Add CAPTCHA (optional but recommended)
  - Input validation and sanitization
  - DDoS protection (AWS Shield)
  - WAF rules (AWS WAF)
  - Set up CloudFront for caching/DDoS protection
- **Security measures:**
  - Rate limiting: 10 requests/hour per IP
  - URL validation (already implemented)
  - Request size limits
  - Timeout limits
- **Cost:** 
  - AWS Shield Standard: Free
  - AWS Shield Advanced: ~$3000/month (optional)
  - WAF: ~$5-50/month

#### Step 5.2: Authentication (Optional)
- **Difficulty:** ⭐⭐ Medium
- **Time:** 1 day
- **Tasks:**
  - Implement user registration/login
  - JWT token authentication
  - API key generation
  - User dashboard
- **If keeping public:**
  - Skip authentication
  - Use IP-based rate limiting
  - Add CAPTCHA for abuse prevention

---

### Phase 6: Monitoring & Operations (Difficulty: ⭐⭐ Medium)

**Estimated Time:** 1-2 days

#### Step 6.1: CloudWatch Setup
- **Difficulty:** ⭐⭐ Medium
- **Time:** 4-6 hours
- **Tasks:**
  - Create CloudWatch dashboards
  - Set up alarms (errors, latency, queue depth)
  - Configure log aggregation
  - Set up SNS notifications
- **Cost:** ~$10-50/month

#### Step 6.2: CI/CD Pipeline
- **Difficulty:** ⭐⭐⭐ Medium
- **Time:** 1 day
- **Tasks:**
  - Set up GitHub Actions or AWS CodePipeline
  - Automated testing
  - Automated deployment
  - Blue/green deployments
- **Tools:** GitHub Actions, AWS CodePipeline

---

## Complete Deployment Checklist

### Infrastructure (Week 1)
- [ ] AWS account setup
- [ ] VPC and networking
- [ ] RDS PostgreSQL database
- [ ] ElastiCache Redis
- [ ] S3 buckets
- [ ] IAM roles and policies

### Application (Week 2)
- [ ] Dockerize application
- [ ] Create ECR repository
- [ ] SQS queue setup
- [ ] ECS cluster for workers
- [ ] Worker application updates
- [ ] Database migration (SQLite → PostgreSQL)

### Web Interface (Week 3)
- [ ] Frontend development
- [ ] Backend API development
- [ ] API Gateway configuration
- [ ] Application Load Balancer
- [ ] SSL certificate (ACM)
- [ ] CloudFront setup (optional)

### Security & Polish (Week 4)
- [ ] Rate limiting
- [ ] CAPTCHA integration
- [ ] WAF rules
- [ ] Monitoring and alerts
- [ ] Documentation
- [ ] Load testing

---

## Code Changes Required

### 1. Database Migration
**File:** `stream_checker/database/models.py`
- Change from SQLite to PostgreSQL
- Update connection string
- Add connection pooling
- Migrate schema

### 2. SQS Worker
**New File:** `stream_checker/workers/sqs_worker.py`
```python
# Worker that polls SQS and processes stream checks
```

### 3. API Server
**New Directory:** `api/`
- `api/app.py` - FastAPI/Flask application
- `api/routes/streams.py` - Stream checking endpoints
- `api/routes/results.py` - Results retrieval endpoints

### 4. Frontend Application
**New Directory:** `frontend/`
- React/Vue.js application
- Stream input form
- Results display
- Real-time updates

### 5. Configuration Updates
- Environment variables for AWS services
- RDS connection strings
- S3 bucket names
- SQS queue URLs

---

## Estimated Costs (Monthly)

### Small Scale (100-500 tests/day)
- **RDS (db.t3.small):** ~$30-50
- **ECS Fargate:** ~$20-50
- **S3 Storage:** ~$5-10
- **ElastiCache:** ~$15-30
- **ALB:** ~$16
- **Data Transfer:** ~$10-20
- **CloudWatch:** ~$5-10
- **Total:** ~$100-200/month

### Medium Scale (1,000-5,000 tests/day)
- **RDS (db.t3.medium):** ~$150-300
- **ECS Fargate:** ~$100-300
- **S3 Storage:** ~$20-50
- **ElastiCache:** ~$50-100
- **ALB:** ~$16
- **Data Transfer:** ~$50-100
- **CloudWatch:** ~$20-50
- **Total:** ~$400-900/month

### Large Scale (10,000+ tests/day)
- **RDS (db.r5.large):** ~$300-500
- **ECS Fargate:** ~$500-1000
- **S3 Storage:** ~$50-100
- **ElastiCache:** ~$100-200
- **ALB:** ~$16
- **Data Transfer:** ~$200-500
- **CloudWatch:** ~$50-100
- **Total:** ~$1,200-2,400/month

---

## Difficulty Summary

| Phase | Difficulty | Time Estimate | Key Challenges |
|-------|-----------|---------------|----------------|
| Infrastructure Setup | ⭐⭐⭐ Medium | 2-3 days | VPC networking, RDS configuration |
| Containerization | ⭐⭐ Medium | 1-2 days | VLC/ffmpeg in containers |
| Queue & Workers | ⭐⭐⭐ Medium-Hard | 2-3 days | Auto-scaling, error handling |
| Web Application | ⭐⭐⭐⭐ Hard | 3-5 days | Full-stack development |
| Security | ⭐⭐⭐ Medium-Hard | 2-3 days | Rate limiting, DDoS protection |
| Monitoring | ⭐⭐ Medium | 1-2 days | CloudWatch setup |

**Total Estimated Time:** 2-3 weeks for experienced developer
**Total Estimated Time:** 4-6 weeks for learning/development

---

## Recommended Approach

### Option 1: Minimal Viable Product (MVP) - 1-2 weeks
**Difficulty:** ⭐⭐ Medium

1. **Simplified Architecture:**
   - Single EC2 instance running everything
   - SQLite database (or small RDS)
   - Simple Flask API
   - Basic HTML/JavaScript frontend
   - No queue system (synchronous processing)

2. **Pros:**
   - Fastest to deploy
   - Lower cost (~$50-100/month)
   - Easier to debug
   - Good for testing

3. **Cons:**
   - Not scalable
   - Single point of failure
   - Limited concurrent users

### Option 2: Full Production (Recommended) - 3-4 weeks
**Difficulty:** ⭐⭐⭐ Medium-Hard

1. **Full Architecture:**
   - ECS Fargate for workers
   - RDS PostgreSQL
   - SQS queue
   - API Gateway + ALB
   - React frontend
   - Auto-scaling

2. **Pros:**
   - Scalable
   - Fault tolerant
   - Production-ready
   - Can handle growth

3. **Cons:**
   - More complex
   - Higher cost
   - More moving parts

### Option 3: Serverless (Alternative) - 2-3 weeks
**Difficulty:** ⭐⭐⭐ Medium

1. **Architecture:**
   - Lambda functions for workers
   - API Gateway for API
   - DynamoDB for storage
   - S3 for results
   - CloudFront for frontend

2. **Pros:**
   - Pay per use
   - Auto-scaling
   - Less infrastructure management

3. **Cons:**
   - Lambda limitations (15 min timeout)
   - Cold starts
   - VLC/ffmpeg in Lambda is challenging

---

## Step-by-Step: MVP Deployment (Easiest Path)

### Week 1: Basic Web Interface

**Day 1-2: Simple API**
- Create Flask/FastAPI app
- Single endpoint: `POST /check` - accepts stream URL
- Runs stream checker synchronously
- Returns JSON results
- **Difficulty:** ⭐⭐ Medium

**Day 3-4: Frontend**
- Simple HTML page with form
- JavaScript to call API
- Display results in table
- **Difficulty:** ⭐⭐ Medium

**Day 5: Deployment**
- Deploy to single EC2 instance
- Set up nginx reverse proxy
- Configure SSL (Let's Encrypt)
- **Difficulty:** ⭐⭐ Medium

### Week 2: AWS Migration

**Day 1-2: Move to AWS**
- Launch EC2 instance
- Install dependencies
- Deploy application
- Set up RDS (optional, can use SQLite initially)

**Day 3-4: Production Setup**
- Set up domain name
- Configure Route 53
- Set up CloudFront (optional)
- Add monitoring

**Day 5: Testing & Polish**
- Load testing
- Security review
- Documentation

---

## Key Technologies to Learn

### Essential
1. **AWS Services:**
   - EC2 (compute)
   - RDS (database)
   - S3 (storage)
   - IAM (security)

### Intermediate
2. **Containerization:**
   - Docker
   - ECS/EKS

### Advanced
3. **Orchestration:**
   - ECS/EKS
   - Auto Scaling
   - Load Balancing

4. **Frontend:**
   - React or Vue.js
   - API integration
   - Real-time updates

---

## Security Considerations for Public Access

### Critical
1. **Rate Limiting:** Prevent abuse
   - Per IP: 10 requests/hour
   - Per stream URL: 1 request/5 minutes
   - Global: 100 requests/minute

2. **Input Validation:** Already implemented
   - URL validation
   - Private IP blocking (configurable)
   - Length limits

3. **Resource Limits:**
   - Max test duration: 5 minutes
   - Max concurrent tests: 10 per IP
   - Queue depth limits

### Recommended
4. **CAPTCHA:** Prevent bots
   - Google reCAPTCHA v3
   - hCaptcha (privacy-friendly alternative)

5. **Monitoring:**
   - Track abuse patterns
   - Alert on suspicious activity
   - Auto-block malicious IPs

6. **Cost Controls:**
   - Budget alerts
   - Auto-shutdown on high costs
   - Usage quotas

---

## Quick Start: MVP Deployment Script

Here's a simplified deployment path:

```bash
# 1. Launch EC2 instance (t3.medium recommended)
# 2. Install dependencies
sudo apt-get update
sudo apt-get install -y python3 python3-pip nginx vlc ffmpeg
pip3 install -r requirements.txt

# 3. Clone and deploy application
git clone <repo>
cd stream_checker

# 4. Set up systemd service
sudo nano /etc/systemd/system/stream-checker.service

# 5. Configure nginx
sudo nano /etc/nginx/sites-available/stream-checker

# 6. Start services
sudo systemctl start stream-checker
sudo systemctl enable stream-checker
sudo systemctl restart nginx
```

---

## Next Steps

1. **Start with MVP** (Option 1) to get something working quickly
2. **Test with real users** to understand usage patterns
3. **Iterate based on feedback**
4. **Scale up** to full architecture when needed

Would you like me to:
1. Create the MVP API and frontend code?
2. Create deployment scripts?
3. Set up a specific part of the architecture?
