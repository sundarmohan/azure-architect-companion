# Azure Architect Companion - Deployment Guide

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [CI/CD Pipeline](#cicd-pipeline)
3. [Docker Configuration](#docker-configuration)
4. [GitHub Secrets Configuration](#github-secrets-configuration)
5. [EC2 Initial Setup](#ec2-initial-setup)
6. [Environment Variables](#environment-variables)
7. [Deployment Process](#deployment-process)
8. [Health Checks](#health-checks)
9. [Rollback Procedure](#rollback-procedure)
10. [Troubleshooting](#troubleshooting)

---

## Architecture Overview

The Azure Architect Companion deployment follows this architecture:

```
GitHub Repository (main branch)
    ↓
GitHub Actions Workflow (docker-deploy.yml)
    ├─ Test Stage (pytest)
    ├─ Build Stage (Docker)
    ├─ Push Stage (Docker Hub)
    └─ Deploy Stage (SSH to EC2)
        ↓
Docker Hub Repository: sms300/azure-architect-companion
    ↓
AWS EC2 Instance (18.206.107.29)
    ├─ PostgreSQL Container (port 5432)
    └─ FastAPI Application Container (port 8001)
```

### Components

- **Application**: FastAPI backend service
- **Database**: PostgreSQL 15
- **Container Registry**: Docker Hub (public)
- **Deployment Host**: AWS EC2 (us-east-1)
- **Reverse Proxy**: None (direct port binding)

---

## CI/CD Pipeline

### Workflow: `.github/workflows/docker-deploy.yml`

The GitHub Actions workflow is triggered on every push to the `main` branch.

#### Pipeline Stages

**Stage 1: Test**
- Checkout repository
- Set up Python 3.11
- Install dependencies from `backend/requirements.txt`
- Run pytest with PostgreSQL service
- If tests fail: Stop pipeline, do NOT push image, do NOT deploy

**Stage 2: Build and Push**
- Set up Docker Buildx (for efficient builds)
- Log in to Docker Hub using credentials from GitHub Secrets
- Build Docker image from `Dockerfile`
- Push two tags:
  - `sms300/azure-architect-companion:latest` (mutable reference)
  - `sms300/azure-architect-companion:${GITHUB_SHA}` (immutable commit reference)

**Stage 3: Deploy**
- Copy deployment files to EC2:
  - `docker-compose.yml`
  - `deploy/deploy.sh`
  - `.env.example`
- Execute deployment script on EC2
- Perform health check against `http://localhost:8001/health`

### Failure Handling

The pipeline stops immediately if any of these fail:
- ❌ Test execution
- ❌ Docker image build
- ❌ Docker Hub push
- ❌ SSH connection to EC2
- ❌ Container startup
- ❌ Database migration
- ❌ Health check

---

## Docker Configuration

### Dockerfile

**Location**: `./Dockerfile`

**Base Image**: `python:3.11-slim`

**Key Features**:
- Non-root user (`appuser`) for security
- Health check configured
- PostgreSQL client tools included
- Production-ready Uvicorn startup
- Binds to `0.0.0.0:8000` (accepts external connections)

**Build Context**: Root directory (includes `backend/` and other paths)

### Image Tags

Images are tagged with two references for maximum flexibility:

1. **Latest Tag** (mutable):
   ```
   sms300/azure-architect-companion:latest
   ```
   - Points to most recent successful build
   - Use for quick deployments
   - May point to different commits over time

2. **SHA Tag** (immutable):
   ```
   sms300/azure-architect-companion:<commit-sha>
   ```
   - Tied to specific commit (e.g., `abc123def456`)
   - Use for production rollbacks
   - Ensures consistent deployments

### .dockerignore

**Location**: `./.dockerignore`

**Excluded Files**:
- `.env` files (secrets)
- `.git` directory
- Test artifacts (`.pytest_cache`, etc.)
- Python cache (`__pycache__`, `.pyc`)
- IDE configuration (`.vscode`, `.idea`)
- Documentation files

---

## GitHub Secrets Configuration

### Required Secrets

Create these secrets in GitHub repository settings (`Settings → Secrets and variables → Actions`):

| Secret | Value | Description |
|--------|-------|-------------|
| `DOCKERHUB_USERNAME` | `sms300` | Docker Hub username |
| `DOCKERHUB_TOKEN` | `dckr_pat_...` | Docker Hub Personal Access Token |
| `EC2_HOST` | `18.206.107.29` | EC2 public IP address |
| `EC2_USER` | `ec2-user` | SSH username (Amazon Linux default) |
| `EC2_SSH_PRIVATE_KEY` | Private key content | SSH private key for EC2 authentication |

### Creating Docker Hub Token

1. Go to [Docker Hub Account Settings](https://hub.docker.com/settings/security)
2. Click "New Access Token"
3. Name: `github-actions`
4. Permissions: Select `Read & Write`
5. Copy the token
6. Add to GitHub Secrets as `DOCKERHUB_TOKEN`

### SSH Private Key Setup

1. Generate or obtain the EC2 SSH private key
2. Keep it secure (never commit to Git)
3. Copy the full private key content
4. Add to GitHub Secrets as `EC2_SSH_PRIVATE_KEY`

**WARNING**: Never paste SSH keys into code, configs, or logs.

---

## EC2 Initial Setup

### Prerequisites

- EC2 instance running Amazon Linux 2 or compatible
- Public IP: `18.206.107.29`
- SSH access via keypair
- Existing installation: Docker 25.x, Docker Compose v2.x

### First-Time Setup

1. **SSH into EC2**:
   ```bash
   ssh -i your-key.pem ec2-user@18.206.107.29
   ```

2. **Create deployment directory**:
   ```bash
   mkdir -p ~/azure-architect-companion
   cd ~/azure-architect-companion
   ```

3. **Create `.env` file**:
   ```bash
   cat > .env << 'EOF'
   DATABASE_URL=postgresql://postgres:postgres@localhost:5432/azure_architect
   POSTGRES_USER=postgres
   POSTGRES_PASSWORD=postgres
   POSTGRES_DB=azure_architect
   APP_NAME=Azure Architect Companion
   DEBUG=False
   IMAGE_TAG=latest
   EOF
   ```
   
   **Security Note**: Update `POSTGRES_PASSWORD` to a strong random value in production.

4. **Verify Docker and Docker Compose**:
   ```bash
   docker --version
   docker compose version
   ```

5. **Test Docker Hub access** (for public repository, this is optional):
   ```bash
   docker pull sms300/azure-architect-companion:latest
   ```

6. **Create deploy directory** (if not yet cloned):
   ```bash
   mkdir -p deploy
   ```

### Post-Setup Verification

After GitHub Actions deploys successfully, verify:

```bash
cd ~/azure-architect-companion

# Check running containers
docker compose ps

# Check application logs
docker compose logs app

# Verify database is ready
docker compose logs postgres

# Test health endpoint
curl http://localhost:8001/health
```

---

## Environment Variables

### Application Configuration

Variables defined in `.env.example` (copied to EC2):

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | `postgresql://postgres:postgres@localhost:5432/azure_architect` | PostgreSQL connection string |
| `POSTGRES_USER` | `postgres` | PostgreSQL username |
| `POSTGRES_PASSWORD` | `postgres` | PostgreSQL password (**change in production**) |
| `POSTGRES_DB` | `azure_architect` | Database name |
| `APP_NAME` | `Azure Architect Companion` | Application display name |
| `DEBUG` | `False` | FastAPI debug mode (use `False` in production) |
| `IMAGE_TAG` | `latest` | Docker image tag to deploy |

### Security Notes

- ❌ Never commit `.env` with real credentials to Git
- ❌ Never include passwords in Docker images
- ❌ Never print secrets in CI/CD logs
- ✅ Use GitHub Secrets for CI/CD credentials
- ✅ Use `.env` on EC2 only (not in Git)
- ✅ Rotate `POSTGRES_PASSWORD` regularly

---

## Deployment Process

### Automatic Deployment (Recommended)

1. **Push to main branch**:
   ```bash
   git add .
   git commit -m "Your message"
   git push origin main
   ```

2. **GitHub Actions automatically**:
   - Runs tests
   - Builds Docker image
   - Pushes to Docker Hub
   - Deploys to EC2
   - Performs health checks

3. **Monitor deployment**:
   - Go to GitHub repository → Actions tab
   - Click the latest workflow run
   - Watch stages: test → build-and-push → deploy
   - Check for green checkmarks ✓

### Manual Deployment (Advanced)

If automated deployment fails or you need to redeploy:

```bash
# SSH to EC2
ssh -i your-key.pem ec2-user@18.206.107.29

# Navigate to deployment directory
cd ~/azure-architect-companion

# Manually deploy (pulls image and starts containers)
export IMAGE_TAG=latest  # or specific commit SHA
bash deploy/deploy.sh
```

---

## Health Checks

### Application Health Endpoint

**Endpoint**: `GET /health`  
**Port**: `8001` (external)  
**Response**: 
```json
{"status": "ok"}
```

### GitHub Actions Health Check

The GitHub Actions workflow automatically verifies:

```bash
curl -f http://localhost:8001/health
```

If this returns HTTP 200, deployment is successful.

### Manual Health Check

```bash
# From your machine or EC2
curl http://18.206.107.29:8001/health

# Expected response
{"status": "ok"}
```

### Container Health Status

Check if containers are healthy:

```bash
docker compose ps

# Output format:
# NAME              STATUS
# azure-architect-postgres    Up 2 minutes (healthy)
# azure-architect-app         Up 1 minute (healthy)
```

---

## Rollback Procedure

### Rollback by Commit SHA

Each Docker image is tagged with its commit SHA, enabling point-in-time rollback.

**Example**: To rollback to a previous commit:

```bash
# SSH to EC2
ssh -i your-key.pem ec2-user@18.206.107.29
cd ~/azure-architect-companion

# List available images on Docker Hub
docker search sms300/azure-architect-companion
# or manually check: https://hub.docker.com/r/sms300/azure-architect-companion/tags

# Rollback to specific commit (e.g., abc123def456)
export IMAGE_TAG=abc123def456
docker compose pull
docker compose down
docker compose up -d

# Verify deployment
sleep 10
curl http://localhost:8001/health
```

### Rollback by Latest Tag

To rollback to the most recently deployed version:

```bash
cd ~/azure-architect-companion
export IMAGE_TAG=latest
docker compose pull
docker compose down
docker compose up -d

# Verify
curl http://localhost:8001/health
```

### Identifying Previous Versions

**Via GitHub**:
1. Go to repository → Commits
2. Find the commit SHA you want to rollback to
3. Use SHA in rollback procedure

**Via Docker Hub**:
1. Visit [Docker Hub Tags](https://hub.docker.com/r/sms300/azure-architect-companion/tags)
2. Find the tag (commit SHA) you want to use

**Via EC2 Docker History**:
```bash
docker images sms300/azure-architect-companion

# Output shows all available tags locally
# REPOSITORY                                  TAG              IMAGE ID
# sms300/azure-architect-companion            latest           abc123...
# sms300/azure-architect-companion            abc123def456     abc123...
```

---

## Troubleshooting

### Deployment Stuck or Slow

**Check GitHub Actions logs**:
1. Go to repository → Actions
2. Click the workflow run
3. Expand each stage to see logs

**Common issues**:
- Tests failing (check test output)
- Docker Hub login failing (verify secrets)
- SSH timeout (check EC2 security group)

### Application Not Starting

```bash
# SSH to EC2
ssh -i your-key.pem ec2-user@18.206.107.29
cd ~/azure-architect-companion

# Check container logs
docker compose logs app

# Look for errors like:
# - Database connection refused
# - Port already in use
# - Migration failed
```

### Database Connection Failed

```bash
# Verify PostgreSQL is running
docker compose logs postgres

# Check if postgres container is healthy
docker compose ps postgres

# Manually test connection
docker compose exec postgres psql -U postgres -c "SELECT 1;"
```

### Port Already in Use

If port 8001 or 5432 is in use:

```bash
# Find what's using port 8001
sudo lsof -i :8001

# Stop old containers
docker compose down --remove-orphans

# If needed, restart Docker
sudo systemctl restart docker
```

### Health Check Failing

```bash
# Check if application is actually running
docker compose ps app

# Test endpoint directly from EC2
curl -v http://localhost:8001/health

# Check application logs for errors
docker compose logs app --tail=50

# If database migration failed
docker compose logs app | grep -i alembic
```

### SSH Connection Issues

**Verify security group allows SSH**:
```
Inbound Rule: SSH (22) from your IP
```

**Verify key permissions**:
```bash
chmod 600 your-key.pem
ssh -i your-key.pem ec2-user@18.206.107.29
```

### Out of Disk Space

```bash
# Check disk usage on EC2
df -h

# Clean up old Docker images
docker image prune -a --force

# Clean up unused volumes
docker volume prune --force

# Clean up old logs (caution)
docker compose logs --tail=100 > logs.txt
```

### Network Issues

**Verify containers are on same network**:
```bash
docker compose ps
docker network ls
docker network inspect azure-architect-companion_app-network
```

**Database URL format**:
```
Good:  postgresql://postgres:postgres@postgres:5432/azure_architect
Bad:   postgresql://postgres:postgres@localhost:5432/azure_architect
# (inside container, use service name "postgres", not "localhost")
```

### Viewing Logs

```bash
# All logs
docker compose logs

# Only application
docker compose logs app

# Only database
docker compose logs postgres

# Follow logs in real-time
docker compose logs -f

# Last N lines
docker compose logs --tail=100

# Since specific time
docker compose logs --since 5m

# Save logs to file
docker compose logs > deployment_logs.txt
```

### Common Docker Commands

```bash
# Check container status
docker compose ps

# Restart containers
docker compose restart

# Stop all containers
docker compose down

# Start containers
docker compose up -d

# Rebuild image (not recommended in production)
docker compose up -d --build

# Remove unused resources
docker system prune

# Check disk usage
docker system df
```

### Database Migration Issues

**Check if migrations ran**:
```bash
docker compose exec postgres psql -U postgres -d azure_architect -c "
SELECT version, installed_on FROM alembic_version;
"
```

**Manually run migrations** (if needed):
```bash
docker compose exec app alembic upgrade head
```

**Rollback migrations** (caution):
```bash
docker compose exec app alembic downgrade -1
```

---

## Security Checklist

- [ ] `.env` file NOT committed to Git
- [ ] SSH private key NOT in repository
- [ ] Docker Hub token stored in GitHub Secrets only
- [ ] PostgreSQL password changed from default
- [ ] EC2 security group restricted to necessary IPs
- [ ] `DEBUG=False` in production
- [ ] Regular backups of PostgreSQL data volume
- [ ] Regular review of deployed image tags

---

## Quick Reference

### Deployment Status
```bash
# Check GitHub Actions
# Open: https://github.com/sms300/azure-architect-companion/actions

# Check EC2 containers
ssh ec2-user@18.206.107.29
docker compose ps
curl http://localhost:8001/health
```

### Key Files
- Workflow: `.github/workflows/docker-deploy.yml`
- Docker: `Dockerfile`, `.dockerignore`
- Compose: `docker-compose.yml`
- Deployment: `deploy/deploy.sh`
- Config: `backend/.env.example`, `.env` (EC2 only)

### Useful Links
- GitHub Actions: https://github.com/sms300/azure-architect-companion/actions
- Docker Hub: https://hub.docker.com/r/sms300/azure-architect-companion
- EC2 Instance: `18.206.107.29:8001`
- Health Check: `http://18.206.107.29:8001/health`

---

## Support

For issues or questions:
1. Check GitHub Actions logs for build/deployment errors
2. SSH to EC2 and check `docker compose logs`
3. Review this guide's Troubleshooting section
4. Check PostgreSQL health: `docker compose logs postgres`
5. Review application logs: `docker compose logs app`
