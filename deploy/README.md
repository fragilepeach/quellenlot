# Private Quellenlot hosting

Deploy Quellenlot as a **single-editor private workspace** on a Linux host using Docker Compose, a Caddy HTTPS/basic-auth reverse proxy and Ollama on that same host. Authentication protects every page and API route. The Python API remains bound to 127.0.0.1; the reverse proxy is the only intended public entry point.

## Requirements

A Linux server with Docker Compose, ports 80/443 available for Caddy, a DNS record pointing your domain to that server, and an Ollama server available at 127.0.0.1:11434 with the five configured models. This Compose stack uses **host networking**, not portable Docker bridge networking, to ensure both Caddy and the app can reach the host loopback. Only the Caddy service should face the Internet.

## Setup

1. Copy `config.example.toml` to `deploy/models.toml` and edit the five local model names and any SearXNG settings. The local file is gitignored.
2. Generate a strong editor password and hash it with Caddy: `docker run --rm -it caddy:2.10 caddy hash-password`. Enter the password interactively. Do not put the plaintext password in Compose.
3. Create a local gitignored file `deploy/.env` containing `QUELLENLOT_DOMAIN=facts.example.org` and `QUELLENLOT_PASSWORD_HASH=<bcrypt-hash-output>`. Restrict its permissions and never commit it. The hash is still authentication material.
4. From the repo root, run `docker compose -f deploy/compose.yml up -d --build`. The app listens only at 127.0.0.1:8765. Caddy requests certificates for the supplied domain and authenticates **all** HTTP routes.
5. Visit `https://facts.example.org`, sign in as `editor` with the chosen password, and use the saved analysis, research, editorial draft, approval and reader-export functions over HTTPS.

If you operate Caddy without Compose, start `quellenlot-ui --config models.toml --public-origin https://facts.example.org` behind the same protected reverse proxy. The optional origin must be an exact HTTPS domain with no path or credentials. Do not rewrite browser Origin headers.

## Security and publication boundary

The Python API has no independent remote user authentication: **never expose its port or configure an unauthenticated proxy route**. It checks the configured Host/Origin pair and rejects cross-site POSTs but relies on the reverse proxy for authentication and TLS. Basic auth is best suited for one trusted editor. Add a stronger identity provider and separate editor authorization before any multi-user deployment.

Caddy authentication covers all saved analysis JSON, raw text snapshots, study searches, editor drafts, approval metadata and assets. Use current Docker/Caddy and Python dependency versions and protect backups of the `review_data` volume. Model calls remain local to host Ollama; remote source discovery and study APIs still receive search terms.

**Nothing is automatically released publicly.** Editorial approval remains tied to a saved report digest and draft revision. After human review and explicit approval, export the approved reader HTML/JSON and publish it separately if intended. This deployment is a private workspace, not a public publication server; no external publication action occurs simply by approving a draft.

Official docs: [Caddy basic authentication](https://caddyserver.com/docs/caddyfile/directives/basic_auth), [Caddy reverse proxy](https://caddyserver.com/docs/caddyfile/directives/reverse_proxy).
