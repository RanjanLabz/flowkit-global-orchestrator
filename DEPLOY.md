# Deploying To VPS

This repo is designed so every new Ubuntu VPS can be created from GitHub with one command.

## 1. Push This Repo To GitHub

From your local machine:

```bash
git init
git add .
git commit -m "Initial Flow worker appliance"
git branch -M main
git remote add origin https://github.com/<owner>/<repo>.git
git push -u origin main
```

If the GitHub repo already exists locally, only run:

```bash
git add .
git commit -m "Update Flow worker appliance"
git push
```

## 2. Install On A Fresh VPS

SSH into the VPS and run:

```bash
curl -fsSL https://raw.githubusercontent.com/<owner>/<repo>/main/install.sh | REPO_URL=https://github.com/<owner>/<repo>.git bash
```

Optional overrides:

```bash
curl -fsSL https://raw.githubusercontent.com/<owner>/<repo>/main/install.sh | \
  APP_DIR=/opt/flow-worker \
  BRANCH=main \
  REPO_URL=https://github.com/<owner>/<repo>.git \
  bash
```

## 3. Update Existing VPS

```bash
cd /opt/flow-worker
sudo bash ./scripts/update.sh
```

## 4. Check Worker

```bash
curl http://127.0.0.1:8080/health
docker compose ps
```

## 5. Add Account

```bash
curl -X POST http://127.0.0.1:8080/accounts \
  -H 'content-type: application/json' \
  -d '{"id":"acc-1"}'
```

Then connect to VNC port `5902` for `acc-1`, sign in to Google Flow once, and the profile persists under `/opt/flow-worker/chrome-profiles/acc-1`.
