# Running the fork on a NAS

This runs Mealie, its Postgres database and a Cloudflare Tunnel as one Docker project on the NAS. The tunnel gives Mealie a public HTTPS address without opening any port on your router, which is what claude.ai needs to connect.

Works on any NAS that runs Docker Compose: Synology (Container Manager, DSM 7.2+), QNAP (Container Station), Unraid, TrueNAS SCALE. The image is built for both Intel/AMD and ARM NAS models.

## What you need

- A domain managed by Cloudflare (free plan is fine). The tunnel publishes Mealie as a subdomain of it, for example `mealie.yourdomain.com`.
- About 1 GB of RAM free on the NAS.

## 1. Create the tunnel in Cloudflare

1. Cloudflare dashboard, **Zero Trust**, **Networks**, **Tunnels**, **Create a tunnel**, type **Cloudflared**, name it `mealie`.
2. On the install screen choose **Docker** and copy the long token after `--token`. Do not run the command shown; the NAS project runs it.
3. **Leave the public hostname for later** (step 4). Until it exists the tunnel publishes nothing, which gives you time to replace Mealie's default admin password before the address goes public.

The token is a password for this tunnel: anyone holding it can run a connector that answers for your hostname. Keep it only in the NAS settings (the `.env` file or Portainer's environment variables), never in the repository or a chat. If it leaks, open the tunnel in Cloudflare and refresh its token; the old one stops working.

## 2. Put the files on the NAS

Create a folder, for example `/volume1/docker/mealie` on Synology, with two files:

- `docker-compose.yml`: a copy of `docker-compose.nas.yml` from this repository.
- `.env` with these lines, filled in:

  ```
  # exactly the hostname from step 1, with https:// and no trailing slash
  BASE_URL=https://mealie.yourdomain.com
  # the token from step 1
  TUNNEL_TOKEN=
  # a long random password, chosen before the first start (changing it later here does not change the database)
  POSTGRES_PASSWORD=
  POSTGRES_USER=mealie
  POSTGRES_DB=mealie
  TZ=Europe/Brussels
  ```

The project creates `data/` and `pgdata/` next to these files on first start. Include the whole folder in your NAS backups.

## 3. Start it

**Synology**: Container Manager, **Project**, **Create**, name `mealie`, path = the folder above, source **Use existing docker-compose.yml**, then **Next** until **Done**. It pulls the images and starts the three containers.

**QNAP**: Container Station, **Applications**, **Create**, paste the compose file and set the environment values from `.env`.

**Any other NAS with SSH**:

```
cd /volume1/docker/mealie
docker compose up -d
```

### With Portainer

Portainer can deploy the same file straight from GitHub, with the settings typed into its interface instead of a `.env` file.

1. Create the data folders on the NAS first, for example `/volume1/docker/mealie/data` and `/volume1/docker/mealie/pgdata`.
2. **Stacks**, **Add stack**, name `mealie`, build method **Repository**:
   - Repository URL `https://github.com/Christophe668/mealie`, reference `refs/heads/main`
   - Compose path `docker-compose.nas.yml`
3. **Environment variables**: add `BASE_URL`, `TUNNEL_TOKEN`, `POSTGRES_PASSWORD`, plus `DATA_DIR=/volume1/docker/mealie/data` and `PG_DATA_DIR=/volume1/docker/mealie/pgdata`. The two folder variables matter: without them Portainer stores the database inside its own internal volume, outside your NAS backups, and deleting the stack can delete your recipes.
4. **Deploy the stack**.

To update later: open the stack, **Pull and redeploy**, with **Re-pull image** switched on. Do not rely on Portainer's automatic GitOps polling for updates: it redeploys as soon as the repository changes, which is about 15 minutes before the new image finishes building, so it would restart on the old image.

## 4. First login, then go public

1. On your home network, open `http://<nas-ip>:9925` and sign in with the default admin, `changeme@example.com` / `MyPassword`. Change the email and a strong password straight away in your profile. Do this before step 2: once the address is public, anyone who finds it can try the default login.
2. Back in Cloudflare, open the tunnel, **Public hostname**, **Add**: subdomain `mealie`, your domain, service type **HTTP**, URL `mealie:9000`. Save. `https://mealie.yourdomain.com` now works from anywhere.

To bring recipes from another Mealie instance (for example the one on your Mac), use **Settings**, **Backups** there to create a backup, download it, then upload and restore it on the NAS.

## 5. Connect Claude

In claude.ai: **Settings**, **Connectors**, **Add custom connector**, URL `https://mealie.yourdomain.com/mcp`. Claude opens Mealie's consent page; approve, and the connector also works in the Claude mobile app.

Check from any computer that the MCP endpoint answers and refuses anonymous calls:

```
curl -s https://mealie.yourdomain.com/.well-known/oauth-protected-resource/mcp
curl -s -o /dev/null -w '%{http_code}\n' -X POST https://mealie.yourdomain.com/mcp
```

The first prints JSON naming your address; the second prints `401`.

## Updating

Each push to `main` publishes a new image. On the NAS: Synology **Project**, `mealie`, **Action**, **Build** (it pulls the latest image and recreates the containers), or over SSH:

```
docker compose pull && docker compose up -d
```

Database migrations run automatically when the new container starts. Take a NAS snapshot or a Mealie backup first if you want an easy way back.

## Without a Cloudflare domain

Two alternatives give the same public HTTPS address:

- **Tailscale Funnel**: install Tailscale on the NAS, run `tailscale funnel 9925`, and use the `https://<nas>.<tailnet>.ts.net` address as `BASE_URL`. Remove the `cloudflared` service and `TUNNEL_TOKEN`.
- **Synology reverse proxy**: a `synology.me` DDNS name with a Let's Encrypt certificate, a reverse proxy rule from `https://mealie.<name>.synology.me` to `http://localhost:9925`, and port 443 forwarded on your router. Remove the `cloudflared` service.
