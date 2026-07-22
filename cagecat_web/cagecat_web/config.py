"""Application configuration.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

#: Directory containing the ``cagecat_web`` Python package (``.../cagecat_web``).
PACKAGE_DIR = Path(__file__).resolve().parent


class Settings(BaseSettings):
    """Runtime configuration for the CAGECAT web application and workers.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_name: str = "CAGECAT"
    app_version: str = "2.0"

    # --- Job storage -------------------------------------------------------
    #: Root directory under which per-job working directories are created.
    jobs_dir: Path = PACKAGE_DIR / "upload"
    #: Delete stored job directories older than this many days.
    job_retention_days: int = 30
    #: Interval, in seconds, between cleanup sweeps.
    cleanup_interval_seconds: int = 24 * 60 * 60
    #: Hard wall-clock limit for a single tool invocation, in seconds.
    job_timeout_seconds: int = 60 * 60

    # --- Uploads -----------------------------------------------------------
    #: Maximum accepted size for a single uploaded file, in bytes (100 MiB).
    max_upload_bytes: int = 100 * 1024 * 1024
    #: Maximum number of individual sequences accepted in a query file.
    max_sequences: int = 10

    #: NCBI API key (raises the request rate limit from 3 to 10 req/s). Set via
    #: the ``CBLASTER_API_KEY`` environment variable / ``.env``.
    cblaster_api_key: str | None = None
    #: Contact email sent to NCBI Entrez (required by NCBI for E-utilities). Used
    #: by the geneNeighborhood viewer to fetch flanking genes. Set via the
    #: ``CBLASTER_EMAIL`` environment variable / ``.env``.
    cblaster_email: str | None = None

    # --- Gene neighborhood enrichment ------------------------------------
    #: Maximum loci enriched with NCBI-fetched neighbouring genes per request
    #: (bounds how many Entrez calls a single viewer load makes).
    max_neighborhood_fetch: int = 20
    #: Default flank, in bp, fetched on each side of a cluster when enriching.
    neighborhood_flank_bp: int = 5000
    #: Hard upper bound on the requested flank, in bp.
    max_neighborhood_flank_bp: int = 50_000

    # --- Result limits -----------------------------------------------------
    #: Maximum clusters cblaster draws in the plot (top N by score). Keeps the
    #: plot renderable for searches that return thousands of clusters.
    max_plot_clusters: int = 50
    #: Maximum clusters shown in the results selection table (top N by score).
    max_display_clusters: int = 500
    #: Maximum clusters extracted/downloaded at once. Extracting clusters from a
    #: remote session fetches each sequence from NCBI, so a high number hits
    #: NCBI's rate limit (HTTP 429). Higher limits apply when an API key is set.
    max_extract_clusters: int = 50
    max_extract_clusters_with_key: int = 150
    #: Maximum clusters forwarded to clinker (a readable comparison figure).
    max_clinker_clusters: int = 25
    max_clinker_clusters_with_key: int = 50

    def has_ncbi_api_key(self) -> bool:
        """Whether an NCBI API key is configured (raises rate limits)."""
        return bool((self.cblaster_api_key or "").strip())

    def extract_cluster_cap(self) -> int:
        """Effective cap for extracting/downloading clusters."""
        return (
            self.max_extract_clusters_with_key
            if self.has_ncbi_api_key()
            else self.max_extract_clusters
        )

    def clinker_cluster_cap(self) -> int:
        """Effective cap for forwarding clusters to clinker."""
        return (
            self.max_clinker_clusters_with_key
            if self.has_ncbi_api_key()
            else self.max_clinker_clusters
        )

    # --- HMM / local databases --------------------------------------------
    #: Directory holding the Pfam profile database (Pfam-A.hmm.gz + .dat.gz),
    #: used by cblaster HMM searches. Downloaded once.
    pfam_dir: Path = PACKAGE_DIR / "databases" / "pfam"
    #: Directory holding pre-built HMM/local search databases (``<name>.fasta``
    #: with a companion ``<name>.sqlite3``, built with ``cblaster makedb``).
    databases_dir: Path = PACKAGE_DIR / "databases"

    # --- Queue / broker ----------------------------------------------------
    redis_url: str = "redis://redis:6379/0"
    celery_broker_url: str | None = None
    celery_result_backend: str | None = None
    celery_task_always_eager: bool = False

    @property
    def broker_url(self) -> str:
        """Effective Celery broker URL."""
        return self.celery_broker_url or self.redis_url

    @property
    def result_backend(self) -> str:
        """Effective Celery result backend URL."""
        return self.celery_result_backend or self.redis_url

    def hmm_databases(self) -> dict[str, Path]:
        """Return databases usable for HMM search as ``name -> FASTA path``.

        A database is a ``<name>.fasta`` with a companion ``<name>.sqlite3`` in
        :attr:`databases_dir` (both produced by ``cblaster makedb``).
        """
        result: dict[str, Path] = {}
        if self.databases_dir.is_dir():
            for fasta in sorted(self.databases_dir.glob("*.fasta")):
                if fasta.with_suffix(".sqlite3").is_file():
                    result[fasta.stem] = fasta
        return result

    def local_databases(self) -> dict[str, Path]:
        """Return databases usable for local search as ``name -> DIAMOND path``.

        A database is a ``<name>.dmnd`` with a companion ``<name>.sqlite3`` in
        :attr:`databases_dir` (both produced by ``cblaster makedb``).
        """
        result: dict[str, Path] = {}
        if self.databases_dir.is_dir():
            for dmnd in sorted(self.databases_dir.glob("*.dmnd")):
                if dmnd.with_suffix(".sqlite3").is_file():
                    result[dmnd.stem] = dmnd
        return result

    def ensure_directories(self) -> None:
        """Create the directories this configuration depends on."""
        self.jobs_dir.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide :class:`Settings` singleton."""
    return Settings()
