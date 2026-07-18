"""clinker tool adapter.

Wraps ``clinker`` behind the generic :class:`Tool` interface to align and
visualise two or more annotated gene clusters.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from cagecat_web.analysis.tools.base import ParameterError, Tool

if TYPE_CHECKING:
    from pathlib import Path


class ClinkerTool(Tool):
    """Align and visualise homologous gene clusters with clinker."""

    name = "clinker"
    label = "clinker"
    accepted_formats = ("genbank", "embl", "gff")
    min_inputs = 2
    max_inputs = 50

    def clean_params(self, raw: dict[str, Any]) -> dict[str, Any]:
        cleaned: dict[str, Any] = {}
        identity = raw.get("min_identity", raw.get("identity"))
        if identity is not None and str(identity).strip() != "":
            try:
                value = float(identity)
            except (TypeError, ValueError) as exc:
                raise ParameterError("'min_identity' must be a number.") from exc
            if not 0.0 <= value <= 1.0:
                raise ParameterError("'min_identity' must be between 0 and 1.")
            cleaned["min_identity"] = value
        return cleaned

    def build_command(
        self,
        *,
        input_paths: list[Path],
        output_dir: Path,
        params: dict[str, Any],
    ) -> list[str]:
        args: list[str] = ["clinker", *[str(p) for p in input_paths]]
        args += ["--plot", str(output_dir / "plot.html")]
        args += ["--output", str(output_dir / "alignments.csv")]
        if "min_identity" in params:
            args += ["--identity", str(params["min_identity"])]
        return args
