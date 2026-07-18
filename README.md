# CAGECAT v2

**CAGECAT** — the Comparative Gene Cluster Analysis Toolbox — is a web server for
sequence-similarity searches and publication-quality visualisation of microbial
operons and homologous gene clusters. 

- **Live service:** https://cagecat.bioinformatics.nl
- **Source:** https://github.com/malanjary-wur/CAGECAT

This repository contains CAGECAT v2, the successor to
[CAGECAT v1](https://doi.org/10.1186/s12859-023-05311-2).

---

## Running CAGECAT standalone with Docker

CAGECAT ships as a self-contained Docker Compose stack, so you can run the full
web application offline on your own machine or server.



### Prerequisites

- [Docker Engine](https://docs.docker.com/engine/install/) 20.10+
- [Docker Compose v2](https://docs.docker.com/compose/) (`docker compose ...`)

### 1. Get the code

```bash
git clone https://github.com/HAugustijn/CAGECAT.git
cd CAGECAT
```

### 2. Configure (optional)

All host-facing settings live in a `.env` file. Copy the template and edit it if
you need different ports; the defaults work out of the box:

```bash
cp .env.example .env
```

| Variable    | Default | Description                                             |
|-------------|---------|---------------------------------------------------------|
| `HTTP_PORT` | `1340`  | Public port for the web interface (served via nginx).   |
| `WEB_PORT`  | `8004`  | Localhost-only port for direct access to the FastAPI app. |

> **Note:** `.env` is git-ignored. Keep any secrets (passwords, API keys, SMTP
> credentials) there.

### 3. Build and start

```bash
docker compose up -d --build
```

The first build downloads the base images and compiles dependencies, so it may
take a few minutes. Once it finishes, open:

```
http://localhost:1340
```

---

## Development

The application source lives in [`cagecat_web/`](cagecat_web/) and is packaged
with `hatchling` (see [`pyproject.toml`](cagecat_web/pyproject.toml)).

```bash
cd cagecat_web
pip install -e ".[dev]"      # install app
pip install -e ".[tools]"    # install tools
pre-commit install
pytest                       # run the test suite
ruff check .                 # lint
```

To run the full stack locally without Docker you need a reachable Redis instance,
the web app and a Celery worker:

```bash
export REDIS_URL=redis://localhost:6379/0
uvicorn cagecat_web.main:app --reload --port 8004
celery -A cagecat_web.celery_app.celery_app worker --loglevel=info
```

---

## License

Released under the MIT License. See [LICENSE](LICENSE).

---

## Citation

If you use CAGECAT, please cite:

> van den Belt, M., Gilchrist, C., Booth, T.J. et al. *CAGECAT: The CompArative
> GEne Cluster Analysis Toolbox for rapid search and visualisation of homologous
> gene clusters.* BMC Bioinformatics 24, 181 (2023).
> https://doi.org/10.1186/s12859-023-05311-2
