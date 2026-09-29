# Azure Architect Companion - EC2 Deployment Guide

**Target EC2 Instance**: `98.84.152.223`  
**SSH User**: `ec2-user`  
**Docker Hub Repository**: `sms300/azure-architect-companion`

---

## Prerequisites

### On EC2 Server
Verify the following are installed:
```bash
ssh ec2-user@98.84.152.223

# Verify Docker
docker --version
# Expected: Docker 25.0.8

# Verify Docker Compose
docker compose version
# Expected: Docker Compose v2.25.0

# Verify Git
git --version
# Expected: Git 2.50.1

# Check if ports are available
sudo ss -lntp | grep -E ':(8001|8002|5432)'
# Should return nothing (ports available)
```

### GitHub Secrets (for GitHub Actions)
Set these in GitHub repository settings (`Settings → Secrets and variables → Actions`):

| Secret | Value | Notes |
|--------|-------|-------|
| `DOCKERHUB_USERNAME` | `sms300` | Docker Hub username |
| `DOCKERHUB_TOKEN` | Personal Access Token | Generate at hub.docker.com → Account Settings → Security |

---

## Step 1: Create Deployment Directory on EC2

```bash
ssh ec2-user@98.84.152.223

# Create deployment directory
mkdir -p /home/ec2-user/azure-architect-companion
cd /home/ec2-user/azure-architect-companion
```

---

## Step 2: Create `.env` Configuration File

Create `.env` on the EC2 server (not in Git):

```bash
cat > /home/ec2-user/azure-architect-companion/.env << 'EOF'
# Database Configuration
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/azure_architect
POSTGRES_USER=postgres
POSTGRES_PASSWORD=postgres
POSTGRES_DB=azure_architect

# Application Settings
APP_NAME=Azure Architect Companion
DEBUG=False

# Docker Image Tag (updated during deployment)
IMAGE_TAG=latest
EOF
```

**Important**: Keep `.env` on EC2 only. Never commit it to Git.

---

## Step 3: GitHub Actions Workflow

When you push to `main` branch, GitHub Actions automatically:

1. **Tests** the application using pytest
2. **Builds** Docker image from Dockerfile
3. **Pushes** to Docker Hub with tags:
   - `sms300/azure-architect-companion:latest`
   - `sms300/azure-architect-companion:${GITHUB_SHA}` (commit SHA)

**Workflow File**: `.github/workflows/docker-build.yml`

**Manual Trigger** (if needed):
- Go to GitHub repository → Actions → Docker Build and Push
- Click "Run workflow"
- Select branch: `main`

---

## Step 4: Initial Deployment

After GitHub Actions successfully pushes the image to Docker Hub:

### 4a. SSH into EC2

```bash
ssh ec2-user@98.84.152.223
cd /home/ec2-user/azure-architect-companion
```

### 4b. Copy deployment files

From your local machine:
```bash
scp -r docker-compose.yml deploy-ec2.sh ec2-user@98.84.152.223:/home/ec2-user/azure-architect-companion/
```

Or from EC2, clone/pull from Git:
```bash
git clone <repo-url> temp-clone
cp temp-clone/docker-compose.yml .
cp temp-clone/deploy/deploy-ec2.sh .
chmod +x deploy-ec2.sh
rm -rf temp-clone
```

### 4c. Run the deployment script

```bash
cd /home/ec2-user/azure-architect-companion

# Deploy latest image
./deploy-ec2.sh

# Or deploy specific commit SHA
IMAGE_TAG=abc123def456 ./deploy-ec2.sh
```

**Expected Output**:
```
=== Azure Architect Companion EC2 Deployment ===
Image Tag: latest
Deployment Directory: .
Docker Image: sms300/azure-architect-companion:latest

Step 1: Pulling Docker image
✓ Image pulled successfully

Step 2: Stopping existing containers
✓ Existing containers stopped

Step 3: Starting application with database migration
✓ Containers started

Step 4: Waiting for application to be ready
Checking health (attempt 1/5)... ✓ Application is ready

=== Deployment Successful ===
Application is running at http://localhost:8001
Health check: http://localhost:8001/health
```

---

## Step 5: Verify Deployment

### 5a. Check container status

```bash
docker ps

# Expected output:
# NAME                          STATUS
# azure-architect-postgres      Up 1 minute (healthy)
# azure-architect-app           Up 1 minute (healthy)
```

### 5b. View application logs

```bash
docker compose logs app --tail=50
```

### 5c. Test health endpoint

From EC2:
```bash
curl http://localhost:8001/health
# Expected: {"status":"ok"}
```

From your local machine:
```bash
curl http://98.84.152.223:8001/health
# Expected: {"status":"ok"}
```

### 5d. Check FastAPI Swagger UI

Visit in browser (if port 8001 is accessible):
```
http://98.84.152.223:8001/docs
```

---

## Step 6: Automated Deployment (Optional)

If you want automatic deployment to EC2 after successful GitHub Actions build, add an `EC2_*` secrets and extend `.github/workflows/docker-build.yml` with a deployment job.

For now, deployment is manual using `deploy-ec2.sh`.

---

## Updating Application

### Method 1: Update Image (Recommended)

```bash
# On your local machine
git push origin main
# → GitHub Actions builds and pushes new image to Docker Hub

# On EC2
cd /home/ec2-user/azure-architect-companion
./deploy-ec2.sh
# → Pulls latest image and restarts containers
```

### Method 2: Specific Commit Rollback

```bash
cd /home/ec2-user/azure-architect-companion
IMAGE_TAG=abc123def456 ./deploy-ec2.sh
# → Uses specific commit SHA image
```

---

## Database Migrations

Database migrations run automatically when the container starts:

```bash
alembic upgrade head
```

This executes before Uvicorn starts the application.

**To check migration status**:
```bash
docker compose exec postgres psql -U postgres -d azure_architect -c "SELECT version, installed_on FROM alembic_version;"
```

---

## Troubleshooting

### Application won't start

```bash
docker compose logs app --tail=100
# Look for errors related to:
# - Database connection
# - Migration failures
# - Port conflicts
```

### Port already in use

```bash
# Check what's using port 8001
sudo ss -lntp | grep 8001

# Stop all containers
docker compose down --remove-orphans

# Restart
./deploy-ec2.sh
```

### Database connection failed

```bash
# Check PostgreSQL container
docker compose logs postgres --tail=50

# Test connection manually
docker compose exec postgres psql -U postgres -c "SELECT 1;"
```

### Health check failing

```bash
# Check if app container is running
docker compose ps app

# Test endpoint from EC2
curl -v http://localhost:8001/health

# Check application logs
docker compose logs app --tail=50
```

### Disk space issues

```bash
# Check usage
df -h

# Clean up old images
docker image prune -a --force

# Clean up unused volumes
docker volume prune --force
```

---

## Useful Commands

### Container Management
```bash
# View running containers
docker compose ps

# View all containers (including stopped)
docker compose ps -a

# View container logs
docker compose logs app
docker compose logs postgres
docker compose logs           # All services

# Follow logs in real-time
docker compose logs -f

# View last N lines
docker compose logs --tail=100

# Restart containers
docker compose restart

# Stop containers
docker compose down

# Remove containers and volumes
docker compose down -v

# Remove stopped containers
docker container prune
```

### Image Management
```bash
# View local images
docker images sms300/azure-architect-companion

# View Docker Hub tags
# https://hub.docker.com/r/sms300/azure-architect-companion/tags

# Pull specific tag
docker pull sms300/azure-architect-companion:abc123def456

# Remove local image
docker rmi sms300/azure-architect-companion:latest
```

### System
```bash
# Check disk usage
docker system df

# Clean up unused resources
docker system prune

# Remove all stopped containers
docker container prune -f

# Remove unused volumes
docker volume prune -f
```

---

## Security Checklist

- [ ] `.env` created on EC2 only (not in Git)
- [ ] `.env` contains secure PostgreSQL password
- [ ] SSH key protected with appropriate permissions (`chmod 600`)
- [ ] Docker Hub token stored in GitHub Secrets only
- [ ] No secrets in Dockerfile, docker-compose.yml, or workflows
- [ ] `DEBUG=False` in production `.env`
- [ ] Regular backups of PostgreSQL data volume

---

## Rollback Procedure

Each build creates an immutable image tagged with the commit SHA. To rollback:

### 1. Identify previous working commit

```bash
# View available images
docker images sms300/azure-architect-companion

# Or check Docker Hub tags
# https://hub.docker.com/r/sms300/azure-architect-companion/tags
```

### 2. Rollback to specific commit

```bash
cd /home/ec2-user/azure-architect-companion

# Redeploy with specific commit SHA
IMAGE_TAG=abc123def456 ./deploy-ec2.sh
```

### 3. Verify rollback

```bash
curl http://localhost:8001/health
docker compose ps
```

---

## Directory Structure

```
/home/ec2-user/azure-architect-companion/
├── .env                       (created manually on EC2)
├── docker-compose.yml         (copied from repo)
├── deploy-ec2.sh              (copied from repo)
└── postgres_data/             (Docker volume, auto-created)
```

---

## File Descriptions

### `docker-compose.yml`
- Defines PostgreSQL 15 service
- Defines FastAPI application service
- Configures persistent database storage
- Sets up health checks
- Loads environment from `.env`

### `deploy-ec2.sh`
- Pulls Docker image from Docker Hub
- Stops old containers
- Starts new containers via `docker compose up -d`
- Runs database migrations (Alembic)
- Waits for application to be ready
- Performs health check

### `.env` (EC2 only)
- Database connection string
- PostgreSQL credentials
- Application settings
- Docker image tag

---

## Next Steps

1. **Configure EC2**:
   - SSH: `ssh ec2-user@98.84.152.223`
   - Create deployment directory
   - Create `.env` file

2. **Push to main**:
   - GitHub Actions builds and pushes to Docker Hub

3. **Deploy**:
   - Copy files to EC2
   - Run `./deploy-ec2.sh`

4. **Verify**:
   - Check `docker compose ps`
   - Test health endpoint
   - View logs if issues

---

## Support

For issues:
1. Check GitHub Actions logs (build status)
2. SSH to EC2 and review `docker compose logs`
3. Verify `.env` is properly configured
4. Ensure ports 8001 (app) and 5432 (postgres) are available
5. Check Docker Hub repository for image availability
