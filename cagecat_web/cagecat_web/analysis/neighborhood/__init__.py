"""geneNeighborhood analysis implementation.

Groups the feature's internals in one place:

* :mod:`~cagecat_web.analysis.neighborhood.ncbi`   — fetch a cluster's flanking
  genes from NCBI Entrez and merge them with the cblaster hits.
* :mod:`~cagecat_web.analysis.neighborhood.runner` — the subprocess entry point
  the job worker runs to write ``neighborhood.json``.

The registered :class:`~cagecat_web.analysis.tools.base.Tool` adapters live in
:mod:`cagecat_web.analysis.tools.neighborhood` (alongside the other tools).
"""
