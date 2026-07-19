"""cblaster tool adapter.

Wraps ``cblaster search`` behind the generic :class:`Tool` interface. The
cblaster-specific parameter validation and argv construction live in
:mod:`cagecat_web.analysis.input_processor_cblaster`.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from cagecat_web.analysis import input_processor_cblaster as cblaster_input
from cagecat_web.analysis.tools.base import Tool

if TYPE_CHECKING:
    from pathlib import Path


class CblasterTool(Tool):
    """Search databases for homologous genes or gene clusters with cblaster."""

    name = "cblaster"
    label = "cblaster"
    accepted_formats = ("fasta", "genbank")
    # 0 because HMM searches use Pfam profiles instead of an uploaded query file
    min_inputs = 0
    max_inputs = 1

    def clean_params(self, raw: dict[str, Any]) -> dict[str, Any]:
        return cblaster_input.clean_search_params(raw)

    def build_command(
        self,
        *,
        input_paths: list[Path],
        output_dir: Path,
        params: dict[str, Any],
    ) -> list[str]:
        query_file = input_paths[0] if input_paths else None
        return cblaster_input.build_search_args(
            query_file=query_file,
            output_dir=output_dir,
            params=params,
        )

    def output_summary(self, output_dir: Path) -> dict[str, Any]:
        session = output_dir / cblaster_input.SESSION_FILE
        if not session.is_file():
            return {}
        try:
            data = json.loads(session.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        return {"cluster_count": cblaster_input.count_clusters(data)}
