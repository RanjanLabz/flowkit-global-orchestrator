# Flow Worker Appliance

Production-oriented VPS worker for running multiple isolated Google Flow / FlowKit browser accounts on one Ubuntu host.

## What It Provides

- One isolated Chrome profile per account.
- Visible Chrome sessions under Xvfb + Fluxbox.
- Per-account x11vnc debug ports.
- Optional per-account proxy.
- FlowKit-compatible Chrome extension bridge per account.
- Redis-backed job queue with active, delayed, retry, and completed job state.
- FastAPI account and job management API.
- Recovery engine for reconnecting Playwright, clearing `labs.google` storage, refreshing Flow, and restarting Chrome.
- Docker Compose deployment with Redis and auto-start on reboot.

## Quick Install

On a fresh Ubuntu 22.04+ VPS:

```bash
curl -fsSL https://raw.githubusercontent.com/<owner>/<repo>/main/install.sh | REPO_URL=https://github.com/<owner>/<repo>.git bash
```

For a local checkout on the VPS:

```bash
sudo APP_DIR=/opt/flow-worker ./scripts/install.sh
```

The installer installs Docker and Chrome, creates persistent directories, builds the worker container, starts Compose, and installs a systemd unit.

## New VPS From GitHub

1. Push this repository to GitHub.
2. On every new VPS, run:

```bash
curl -fsSL https://raw.githubusercontent.com/<owner>/<repo>/main/install.sh | REPO_URL=https://github.com/<owner>/<repo>.git bash
```

This clones the repo into `/opt/flow-worker`, installs Docker and Chrome, starts Redis and the worker, and enables auto-start on reboot.

To update an existing VPS:

```bash
cd /opt/flow-worker
sudo bash ./scripts/update.sh
```

## Runtime Ports

- API: `8080`
- VNC accounts: `5901-5999`
- Chrome remote debugging inside container: `9222-9322`

## API Examples

Create an account:

```bash
curl -X POST http://localhost:8080/accounts \
  -H 'content-type: application/json' \
  -d '{"id":"acc-1","proxy_enabled":false}'
```

Create an account with a proxy:

```bash
curl -X POST http://localhost:8080/accounts \
  -H 'content-type: application/json' \
  -d '{"id":"acc-2","proxy_enabled":true,"proxy_url":"http://user:pass@host:8080"}'
```

Submit a job:

```bash
curl -X POST http://localhost:8080/jobs \
  -H 'content-type: application/json' \
  -d '{"prompt":"Create a short cinematic clip of a city at sunrise"}'
```

Check health:

```bash
curl http://localhost:8080/health
```

## Account States

`READY`, `BUSY`, `COOLDOWN`, `CAPTCHA_REQUIRED`, `TOKEN_EXPIRED`, `BROKEN_SESSION`, `BLOCKED`

## Job States

`QUEUED`, `ASSIGNED`, `PROCESSING`, `RETRYING`, `COMPLETED`, `FAILED`, `TIMEOUT`

## Configuration

Edit `config/worker.yaml` or override key values with environment variables:

- `WORKER_ID`
- `REDIS_URL`
- `WORKER_CONFIG`
- `CHROME_BINARY`
- `FLOW_URL`
- `VNC_PASSWORD`
- `autostart_accounts` in YAML controls whether persisted accounts relaunch after container restart.

## Persistent Data

- `chrome-profiles/`: isolated Chrome user data dirs.
- `worker/accounts/`: account YAML definitions.
- `worker/logs/`: worker logs.
- `extension/`: FlowKit extension mount. The installer can populate this from the FlowKit repository, and this checkout already uses the FlowKit extension layout.

## FlowKit Integration

The worker is designed around the existing FlowKit extension from `https://github.com/crisng95/flowkit`.

Put the unpacked FlowKit `extension/` directory at `/extension` in the container, or let `scripts/install.sh` copy it from the FlowKit repo. For each account, the worker creates a runtime copy of `/extension` and rewrites only the local bridge URLs:

- FlowKit extension WebSocket: `ws://127.0.0.1:<per-account-port>`
- FlowKit callback: `http://127.0.0.1:8080/flowkit/<account-id>/callback`

Chrome extension files, manifest shape, content scripts, injected captcha flow, request patterns, and Google Flow compatibility are otherwise preserved.

To submit a native FlowKit bridge request through the worker queue, send a job with a `flowkit` object:

```bash
curl -X POST http://localhost:8080/jobs \
  -H 'content-type: application/json' \
  -d '{
    "prompt": "FlowKit bridge request",
    "flowkit": {
      "method": "api_request",
      "params": {
        "url": "https://aisandbox-pa.googleapis.com/v1/credits?key=<google-api-key>",
        "method": "GET",
        "headers": {}
      }
    }
  }'
```

## Notes For Operations

Use VNC to manually sign in to each Google account the first time. Sessions persist in the account Chrome profile. Do not share profile directories across accounts.

The worker intentionally runs Chrome visibly in a virtual display rather than fully headless. This improves compatibility with Google Flow and makes account recovery/debugging possible.
