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

| Variable          | Default | Description                                             |
|-------------------|---------|---------------------------------------------------------|
| `HTTP_PORT`       | `1340`  | Public port for the web interface (served via nginx).   |
| `WEB_PORT`        | `8004`  | Localhost-only port for direct access to the FastAPI app. |

> **Note:** `.env` is git-ignored. Keep any secrets (passwords, API keys, SMTP
> credentials) there. Remote cblaster searches will not start unless
> `CBLASTER_EMAIL` is set — NCBI requires a contact address.

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

## Using cblaster

1. Open **cblaster**, upload a protein FASTA query (or enter NCBI accessions),
   choose a database and parameters, and submit. Remote searches use NCBI and
   require `CBLASTER_EMAIL` to be set (see configuration above).
2. You are taken to a **results page** that polls the job and, once finished,
   shows an interactive cluster plot, downloadable result files, and a set of
   **downstream analyses**:
   - *Search again* — recompute with different filtering/clustering thresholds
   - *Gene neighbourhood* — estimate a suitable maximum intergenic gap (`gne`)
   - *Extract sequences* — hit sequences, optionally as FASTA (`extract`)
   - *Extract clusters* — clusters as GenBank/BiG-SCAPE (`extract_clusters`)
   - *Visualise clusters* — a clinker figure (`plot_clusters`)
3. Your jobs are listed in the left sidebar. This history is stored **in your
   browser only** (no login), so you see your runs and not other users'. Paste a
   job ID under *cblaster → Results for existing job* to reopen any job.

The HTTP API mirrors this: `POST /api/jobs/cblaster` to submit,
`GET /api/jobs/{id}` to poll, `GET /api/jobs/{id}/results` for outputs, and
`POST /api/jobs/{id}/actions/{action}` to run a downstream analysis. Adding a new
tool means subclassing `Tool` in
[`analysis/tools/`](cagecat_web/cagecat_web/analysis/tools) and registering it.

### Search modes

- **Remote** (NCBI BLAST) — searches `nr`/RefSeq/Swissprot with a sequence or
  NCBI-accession query. Note: cblaster 1.4.0's remote result parsing is currently
  broken against NCBI (both `nr` and ClusteredNR); this is an upstream bug.
- **HMM** — searches a **local database** with Pfam profiles (no query file).
  This is fully local and works today. It requires two one-time setups:

  1. **Pfam profiles** in `./data/pfam` (the container blocks FTP, so fetch via
     HTTPS):
     ```bash
     mkdir -p data/pfam
     base=https://ftp.ebi.ac.uk/pub/databases/Pfam/current_release
     curl -o data/pfam/Pfam-A.hmm.gz     "$base/Pfam-A.hmm.gz"
     curl -o data/pfam/Pfam-A.hmm.dat.gz "$base/Pfam-A.hmm.dat.gz"
     ```
  2. **A search database** in `./data/databases`, built from genome files with
     `cblaster makedb` (produces `<name>.fasta` + `.sqlite3`, which the app then
     lists automatically in the HMM "database" dropdown):
     ```bash
     docker compose exec celery_worker \
       cblaster makedb /data/databases/genome1.gbff /data/databases/genome2.gbff \
       -n mydb
     ```

  All job results and databases live under `./data` (bind-mounted), so they are
  visible on the host and persist across restarts.

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
