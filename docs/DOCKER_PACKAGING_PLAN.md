# Docker Packaging Plan: stream_checker

Plan for packaging stream_checker as a Docker image that runs on **macOS** (Docker Desktop), **Raspberry Pi** (ARM), and **AWS** (x86/ARM). Includes a readiness assessment of the existing codebase by category.

---

## 1. Readiness Assessment by Category

### 1.1 Dependencies & Environment

| Area | Readiness | Notes |
|------|-----------|--------|
| **Python deps** | ✅ Ready | `requirements.txt` is pinned and self-contained. No system-level pip packages. |
| **System binaries** | ⚠️ Needs image | **ffmpeg** is required (Phase 3); code uses `shutil.which("ffmpeg")` and fallback paths (`/usr/bin/ffmpeg`, `/usr/local/bin/ffmpeg`, `/opt/homebrew/bin/ffmpeg`). In Docker, install via package manager (e.g. `apt-get install ffmpeg`). |
| **VLC** | ⚠️ Optional | Phase 2 uses VLC (python-vlc or CLI). Code gracefully degrades if VLC is missing. For minimal images: omit VLC and accept Phase 2 as “skipped” or use headless `cvlc` on Linux. |
| **Config file** | ✅ Ready | `config.yaml` + `~/.stream_checker/config.yaml` + `--config`. Defaults work; paths use `expand_path()` (~ and env vars). In Docker, set `HOME` or mount config. |
| **Env vars** | ✅ Ready | `STREAM_CHECKER_*` used for debug/tracing only. No hard requirement for deployment. |

**Verdict:** Ready once base image includes ffmpeg (and optionally VLC/cvlc). No code changes required for dependency discovery.

---

### 1.2 Paths & Storage

| Area | Readiness | Notes |
|------|-----------|--------|
| **Database** | ✅ Ready | SQLite at `database.path` (default `~/.stream_checker/stream_checker.db`). `Path.expanduser()` and `mkdir(parents=True, exist_ok=True)` used. In Docker, use a volume or env-overridable path. |
| **Temp dir** | ✅ Ready | Default `storage.temp_dir: "/tmp/stream_checker"`. `/tmp` exists in Linux containers; config is overridable. |
| **Results / logs** | ✅ Ready | Defaults under `~/.stream_checker/results` and `~/.stream_checker/logs`. All go through `expand_path()`. Ensure writable `HOME` or override via config. |
| **Hardcoded paths** | ⚠️ Minor | `audio_analysis._find_ffmpeg()` and `player_test._find_vlc_command()` use known paths (e.g. `/opt/homebrew/bin/ffmpeg`). Relying on PATH in Docker is sufficient; no change required. |

**Verdict:** Ready. Use a single writable dir (e.g. `/app/data` or `HOME=/app/data`) and optionally mount config with overrides for `database.path`, `storage.temp_dir`, `logging.file`, `storage.results_dir`.

---

### 1.3 Platform & Architecture

| Area | Readiness | Notes |
|------|-----------|--------|
| **macOS (Darwin)** | ✅ Handled | Multiprocessing forced to `spawn`; subprocess runs via helper process to avoid fork crashes. Works in Docker on Mac (Linux VM). |
| **Linux** | ✅ Ready | Primary container OS. No Darwin-specific branches required at runtime. |
| **Raspberry Pi** | ⚠️ Build-time | Python and ffmpeg have ARM builds. Use multi-stage build with `arm32v7` or `arm64v8` base. `numpy`/binary wheels may need build for armv7. |
| **AWS** | ✅ Ready | x86_64 (amd64) and Graviton (arm64) supported via standard Linux images. |

**Verdict:** Ready. Use multi-arch build (e.g. `buildx`) for `linux/amd64` and `linux/arm64` (and optionally `linux/arm/v7` for older Pi).

---

### 1.4 Execution Model

| Area | Readiness | Notes |
|------|-----------|--------|
| **CLI entrypoint** | ✅ Ready | Single process: `stream_checker.py --url ... --phase N`. Ideal for Docker (one-shot or cron). |
| **No embedded server** | ✅ Ready | This repo has no Flask/FastAPI server; `API_USAGE_EXAMPLE.py` is sample code. Deployment is “run CLI” or “call as library.” |
| **Subprocess safety** | ✅ Ready | `run_subprocess_safe` uses spawn helper on macOS; in Linux containers it runs subprocess directly. No change needed. |
| **Concurrency** | ✅ Ready | No assumption of multiple workers in one process; scaling is via multiple containers or invocations. |

**Verdict:** Fully suitable for containerized one-shot or scheduled runs.

---

### 1.5 Security & Configuration

| Area | Readiness | Notes |
|------|-----------|--------|
| **Secrets** | ✅ N/A | No DB passwords or API keys in this app. Config is URL/timeouts/limits. |
| **Network** | ✅ Ready | Outbound HTTP/HTTPS only. No inbound ports required. |
| **User** | ⚠️ Recommended | Run as non-root in Docker; ensure data dir is writable (e.g. `chown` in Dockerfile or use numeric user). |
| **Config validation** | ✅ Ready | `Config` validates timeouts, phases, paths; invalid values fall back to defaults. |

**Verdict:** Ready. Add non-root user and writable data dir in Dockerfile for production.

---

### 1.6 Summary Table

| Category | Readiness | Blocker? |
|----------|-----------|----------|
| Dependencies & environment | Ready (add ffmpeg in image) | No |
| Paths & storage | Ready | No |
| Platform & architecture | Ready (multi-arch build) | No |
| Execution model | Ready | No |
| Security & config | Ready (add non-root) | No |

**Overall:** Codebase is **Docker-ready**. Work is in Dockerfile, optional docker-compose, and docs (not in application code), with optional small improvements (env override for data dir, or config template).

---

## 2. Docker Strategy

### 2.1 Base Image

- **Recommendation:** `python:3.11-slim-bookworm` or `python:3.12-slim-bookworm`.
- **Why:** Debian has `ffmpeg` in apt; slim keeps image smaller; Bookworm is current stable.
- **Alternative for minimal:** Alpine (`python:3.11-alpine`) plus `ffmpeg` from Alpine packages—smaller but more caveats with binary wheels (e.g. numpy); prefer Debian unless image size is critical.

### 2.2 System Packages

- **Required:** `ffmpeg` (Phase 3).
- **Optional:** `vlc` or `vlc-nox` / `cvlc` for Phase 2 (or omit and accept Phase 2 skipped).

Example (Debian):

```dockerfile
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*
```

Optional VLC (headless):

```dockerfile
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg vlc-nox \
    && rm -rf /var/lib/apt/lists/*
```

### 2.3 Multi-Platform (Mac, Pi, AWS)

- **Mac (Docker Desktop):** Typically runs `linux/amd64` (Intel) or `linux/arm64` (Apple Silicon). Build for these.
- **Raspberry Pi:** Usually `linux/arm/v7` (32-bit) or `linux/arm64` (Pi 4/5 64-bit). Build `arm64` and optionally `arm/v7`.
- **AWS:** `linux/amd64` (x86), `linux/arm64` (Graviton). Same two platforms.

Use Docker Buildx:

```bash
docker buildx create --use
docker buildx build --platform linux/amd64,linux/arm64 -t stream_checker:latest .
```

Optional for older Pi:

```bash
docker buildx build --platform linux/amd64,linux/arm64,linux/arm/v7 -t stream_checker:latest .
```

### 2.4 Image Layout (Suggested)

- **Working dir:** `/app`.
- **Copy:** `stream_checker/`, `stream_checker.py`, `config.yaml`, `requirements.txt`.
- **Install:** `pip install -r requirements.txt` (no editable install required if paths are set).
- **Data:** Either:
  - `HOME=/app/data` and use default `~/.stream_checker/*`, or
  - Mount a volume at `/app/data` and pass `--config /app/data/config.yaml` with `database.path`, `storage.temp_dir`, `logging.file`, `storage.results_dir` under `/app/data`.

### 2.5 Entrypoint

- Default: run the CLI.
- Example: `ENTRYPOINT ["python", "-u", "/app/stream_checker.py"]` with `CMD ["--help"]` so `docker run ... --url ... --phase 4` works.
- Ensure Python is unbuffered (`-u`) for logs in real time.

### 2.6 Non-Root User

- Create user e.g. `app` or `streamcheck` with a fixed UID.
- Set ownership of `/app` and `/app/data` (if used).
- `USER app` before `ENTRYPOINT`.

---

## 3. Implementation Plan

### Phase A: Minimal Dockerfile (single platform)

1. Add `Dockerfile` in project root:
   - FROM `python:3.11-slim-bookworm`
   - Install `ffmpeg` (and optionally `vlc-nox`).
   - Set `WORKDIR /app`, copy app + requirements, `pip install -r requirements.txt`.
   - Create non-root user and set `HOME`/data dir.
   - `ENTRYPOINT`/`CMD` as above.
2. Add `.dockerignore` (e.g. `venv/`, `*.pyc`, `.git`, `tests/`, `scratch/`, `docs/` if not needed in image).
3. Document in README: how to build, run one-shot, and mount config/data.

### Phase B: Multi-arch and optional docker-compose

4. Add `docker-compose.yml` (optional):
   - Build context and image name.
   - Volume for data/config.
   - Example `command: ["--url", "https://example.com/stream", "--phase", "4", "--output-format", "json"]`.
5. Document Buildx for `linux/amd64` and `linux/arm64` (and optionally `arm/v7`).
6. Optionally add a small `config.docker.yaml` or env-based defaults (e.g. `STORAGE_TEMP_DIR=/tmp/stream_checker`, `DATABASE_PATH=/app/data/stream_checker.db`) if you later add env parsing in config.

### Phase C: AWS / Production tweaks

7. **ECS/Fargate:** Use same image; run as task with command override; store results in S3 or external DB if needed (would require code changes for S3).
8. **EC2 / EKS:** Same image; cron or job runner to invoke CLI; persist DB/results on volume.
9. **Lambda:** Not a natural fit (long-running ffmpeg, binary deps); prefer ECS/EC2 or batch.

---

## 4. Optional Code Improvements (Low Priority)

- **Config:** Support env vars for key paths (e.g. `STREAM_CHECKER_DB_PATH`, `STREAM_CHECKER_TEMP_DIR`) so Docker can configure without mounting a full config file.
- **Discovery:** Rely only on PATH for ffmpeg/VLC in containers; current code already prefers `shutil.which()`, so no change required unless you want to remove hardcoded paths for clarity.
- **Health:** For long-running or orchestrated use, optional “readiness” could be a tiny script that runs `stream_checker.py --url ... --phase 1` and exits 0/1; not required for one-shot CLI.

---

## 5. File Checklist

| File | Purpose |
|------|---------|
| `Dockerfile` | Multi-stage or single-stage build; Python slim + ffmpeg; non-root user; ENTRYPOINT/CMD. |
| `.dockerignore` | Exclude venv, tests, .git, scratch, large or sensitive files. |
| `docker-compose.yml` | (Optional) Build, volume, example command. |
| `docs/DOCKER_PACKAGING_PLAN.md` | This plan and readiness assessment. |
| `README.md` | Add “Docker” section: build, run, platforms, volumes. |

---

## 6. Quick Reference: Run Examples

**One-shot (after image built):**

```bash
docker run --rm -e HOME=/app/data -v $(pwd)/data:/app/data stream_checker:latest \
  --url "https://example.com/stream.mp3" --phase 4 --output-format json
```

**With config mount:**

```bash
docker run --rm -v $(pwd)/data:/app/data -v $(pwd)/config.yaml:/app/config.yaml stream_checker:latest \
  --config /app/config.yaml --url "https://example.com/stream.mp3" --phase 4
```

**Raspberry Pi (arm64):**

```bash
docker run --rm --platform linux/arm64 -v ./data:/app/data stream_checker:latest --url "..." --phase 3
```

This plan and the readiness assessment give a clear path to a single Dockerfile that works on Mac, Raspberry Pi, and AWS with minimal or no code changes.
