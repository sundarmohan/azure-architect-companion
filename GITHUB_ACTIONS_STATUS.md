# GitHub Actions CI/CD Workflow Status

## Pipeline Overview

This document tracks the GitHub Actions CI/CD deployment pipeline.

**Workflow File:** `.github/workflows/docker-build.yml`

**Trigger:** Push to `main` branch or manual workflow dispatch

**Architecture:**
```
Code Push to main
      ↓
[Test Job] - Run pytest with PostgreSQL
      ↓ (on success)
[Build & Push Job] - Build Docker image, push to Docker Hub
      ↓ (on success)
[Deploy Job] - Deploy to EC2 using SSH
      ↓ (on success)
[Health Check] - Verify application /health endpoint
      ↓
[Verify Containers] - Show container logs and status
```

## GitHub Environment: `dev`

All secrets are configured in GitHub Environment `dev`:
- `DOCKERHUB_USERNAME`
- `DOCKERHUB_PASSWORD`
- `EC2_HOST`
- `EC2_USERNAME`
- `EC2_SSH_KEY`

## Next Steps

1. Monitor workflow at: https://github.com/sundarmohan/azure-architect-companion/actions
2. Watch for pipeline completion (5-10 minutes typical)
3. Verify application health at: http://98.84.152.223:8001/health

## Troubleshooting

If workflow fails:
1. Check job logs in GitHub Actions UI
2. Verify EC2 has `.env` file at `/home/ec2-user/azure-architect-companion/.env`
3. SSH to EC2 and run: `docker compose ps` and `docker compose logs`

---

**Last Updated:** 2026-09-29
**Status:** Workflow ready to run
