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
from cagecat_web.analysis.tools.cblaster_actions import (
    CblasterExtractClustersTool,
    CblasterExtractSequencesTool,
    CblasterGneTool,
    CblasterRecomputeTool,
)
from cagecat_web.analysis.tools.clinker import (
    CblasterClinkerTool,
    ClinkerClustersTool,
    ClinkerTool,
)
from cagecat_web.analysis.tools.neighborhood import (
    CblasterNeighborhoodTool,
    NeighborhoodSearchTool,
)

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
    """Return the sorted names of all primary (non-derived) tools."""
    return sorted(name for name, tool in _REGISTRY.items() if not tool.is_derived)


def actions_for(tool_name: str) -> list[Tool]:
    """Return the derived tools that can run against ``tool_name``'s output."""
    return [
        tool
        for tool in _REGISTRY.values()
        if tool.is_derived and tool_name in tool.parent_tools
    ]


# Primary tools (accept uploads).
register(CblasterTool())
register(ClinkerTool())
register(NeighborhoodSearchTool())

# Derived cblaster tools (operate on a search session).
register(CblasterRecomputeTool())
register(CblasterGneTool())
register(CblasterExtractSequencesTool())
register(CblasterExtractClustersTool())

# cblaster -> clinker handoffs.
register(ClinkerClustersTool())
register(CblasterClinkerTool())

# cblaster -> geneNeighborhood handoff.
register(CblasterNeighborhoodTool())

__all__ = [
    "ParameterError",
    "Tool",
    "ToolError",
    "UnknownToolError",
    "actions_for",
    "available_tools",
    "get_tool",
    "register",
]
