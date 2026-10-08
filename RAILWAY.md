# Deploying on Railway

The image is a single Python process with no external dependencies, so Railway needs three
things: a port it can route (Railway injects `PORT`, the image already binds it), a volume so
accounts and usage survive a redeploy, and a panel password so the dashboard is not open with
the default `admin`.

Two ways in. Both end up running the same container.

## Path A — build from this repository (no registry, no secrets)

1. Railway → **New Project** → **Deploy from GitHub repo** → pick `dhodhoo/workbuddy2api-hub`.
   Railway finds the `Dockerfile` at the root and builds it; nothing else is needed to build.
2. Add storage. Either:
   - **two volumes**: one mounted at `/app/accounts`, one at `/app/usage`; or
   - **one volume** mounted at `/data`, plus the variables
     `ACCOUNTS_DIR=/data/accounts` and `WB_PROXY_USAGE_DIR=/data/usage`.

   Without a volume the container starts clean on every deploy: accounts, the panel password
   and the generated `/v1` API key are all lost.
3. Set variables (service → **Variables**):

   | Variable | Value | Why |
   |---|---|---|
   | `PANEL_PASSWORD` | a secret of your own | the dashboard password; without it the panel opens with `admin` |
   | `TZ` | e.g. `Asia/Jakarta` | the daily limits and the scheduler work on local midnight |
   | `API_KEY` | optional | pin the `/v1` key instead of letting the gateway generate one |

   `HOST` and `PORT` do not need to be set: the image already binds `0.0.0.0` and reads Railway's
   `PORT`.
4. **Generate a domain** (service → Settings → Networking) and open it. The healthcheck is
   `/health` (the image ships a `HEALTHCHECK` that follows `PORT`; Railway reads it, and
   `healthcheckPath = /health` can be set explicitly in the service settings).

## Path B — deploy the prebuilt image

The publish workflow pushes `ghcr.io/dhodhoo/workbuddy2api-hub` (`:latest`, the release tag, and
`sha-<commit>`). Trigger it with **Actions → Publish Docker image → Run workflow**, or by
publishing a GitHub Release.

1. Pull it: `docker pull ghcr.io/dhodhoo/workbuddy2api-hub:latest`. The package inherits this
   repository's public visibility, so an anonymous pull works - no registry credentials are
   needed on Railway. If you ever switch the package to private, give Railway registry
   credentials in the image source instead.
2. Railway → **New Project** → **Deploy from Docker Image** →
   `ghcr.io/dhodhoo/workbuddy2api-hub:latest`, then apply the same volumes, variables and
   domain as in Path A.

## First run

1. Open the domain. The panel asks for the panel password — this is `PANEL_PASSWORD`.
2. **+ Add account (OAuth)**. The panel shows an authorization link; open it in your own
   browser and finish the login there. The panel polls the gateway, and the account appears in
   the pool once the upstream hands over the token. This is a device-code style flow, so it
   works from a remote URL — no callback to your machine.
   The other option on the same screen imports an account JSON exported from another
   deployment.
3. The `/v1` API key is printed in the deploy logs at startup (look for `API Key : wb-…`) and is
   also visible in the panel's settings page. Use it as
   `Authorization: Bearer <key>` against `https://<your-domain>/v1`.

Quick check once deployed:

```bash
curl -s https://<your-domain>/health
curl -s https://<your-domain>/v1/models -H "Authorization: Bearer <key>"
```

## Notes

- **The panel is English; the gateway's own log lines and error messages are Chinese.** The
  `运行日志` tab, toasts carrying an upstream error, and auto-generated exit names
  (`美国 住宅`) come from the Python side and are not translated.
- **Everything the container writes lives under `ACCOUNTS_DIR` and `WB_PROXY_USAGE_DIR`**
  (`/app/accounts` and `/app/usage` by default). Mount volumes on those two paths, or point
  both variables at one volume.
- **The image runs as root**, so Railway's volume permissions work without extra variables.
- **One replica.** The scheduler and the usage accounting are in-process; running two replicas
  against the same volume would double the scheduled tasks and interleave the usage log.
- **`TZ` is applied at runtime**, so the container clock follows the variable (the image bakes
  `Asia/Shanghai` into `/etc/timezone` at build time, but the process reads `TZ`). Check it with
  `docker exec <container> date`.
