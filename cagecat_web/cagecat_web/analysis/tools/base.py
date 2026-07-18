"""Interface shared by every analysis tool.

New tools become available to the whole platform by subclassing :class:`Tool`
and registering an instance (see :mod:`cagecat_web.analysis.tools`).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pathlib import Path


class ToolError(Exception):
    """Base class for tool-related errors."""


class UnknownToolError(ToolError, KeyError):
    """Raised when a requested tool name is not registered."""


class ParameterError(ToolError, ValueError):
    """Raised when submitted parameters are invalid. Message is client-safe."""


class Tool(ABC):
    """A runnable analysis tool.

    Subclasses declare which input formats they accept and how many input
    files they expect, clean the user-supplied parameters, and translate a job
    into an executable command line.
    """

    name: str
    label: str
    accepted_formats: tuple[str, ...] = ()
    min_inputs: int = 1
    max_inputs: int = 1

    def clean_params(self, raw: dict[str, Any]) -> dict[str, Any]:
        """Validate and normalise raw form parameters.

        The default implementation accepts no parameters. Override to coerce
        and bound-check values, raising :class:`ParameterError` on bad input.
        """
        return {}

    @abstractmethod
    def build_command(
        self,
        *,
        input_paths: list[Path],
        output_dir: Path,
        params: dict[str, Any],
    ) -> list[str]:
        """Return the command-line invocation for this tool as an argv list."""

    def output_summary(self, output_dir: Path) -> dict[str, Any]:
        """Return a small, JSON-serialisable summary of the results.

        Override to surface tool-specific highlights (e.g. hit counts). The
        default returns an empty mapping.
        """
        return {}
