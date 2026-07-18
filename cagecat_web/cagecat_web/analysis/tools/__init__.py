"""Registry of available analysis tools.

Import this module to obtain a :class:`~cagecat_web.analysis.tools.base.Tool`
by name. Register a new tool with :func:`register`.
"""

from __future__ import annotations

from cagecat_web.analysis.tools.base import (
    ParameterError,
    Tool,
    ToolError,
    UnknownToolError,
)
from cagecat_web.analysis.tools.cblaster import CblasterTool
from cagecat_web.analysis.tools.clinker import ClinkerTool

_REGISTRY: dict[str, Tool] = {}


def register(tool: Tool) -> Tool:
    """Register ``tool`` under its :attr:`~Tool.name`, returning it."""
    _REGISTRY[tool.name] = tool
    return tool


def get_tool(name: str) -> Tool:
    """Return the registered tool called ``name``.

    Raises:
        UnknownToolError: If no tool with that name is registered.
    """
    try:
        return _REGISTRY[name]
    except KeyError as exc:
        raise UnknownToolError(name) from exc


def available_tools() -> list[str]:
    """Return the sorted names of all registered tools."""
    return sorted(_REGISTRY)


register(CblasterTool())
register(ClinkerTool())

__all__ = [
    "ParameterError",
    "Tool",
    "ToolError",
    "UnknownToolError",
    "available_tools",
    "get_tool",
    "register",
]
