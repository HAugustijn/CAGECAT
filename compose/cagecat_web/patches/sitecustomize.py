"""Runtime patch for cblaster's NCBI IPG (genomic-context) fetching.

cblaster 1.4.0 requests the Identical Protein Groups (IPG) table from NCBI in
chunks of 1000 identifiers with ``retmax=1000``. When the hits expand to more
than 1000 IPG records (common — a protein has many identical copies across
genomes) NCBI truncates the response, producing partial rows with missing
fields. cblaster then crashes (``Entry(*fields)`` TypeError for ``nr``; a
``ChunkedEncodingError`` for ClusteredNR). This is the cblaster author's
recommended fix: query fewer ids per request and raise ``retmax``.

Applied via ``sitecustomize`` (auto-imported at interpreter startup) so it is
active inside the ``cblaster`` subprocess. It self-gates on ``sys.argv[0]`` so
it only touches cblaster runs — importing/patching nothing for the web app,
the Celery worker, clinker, or anything else that shares this PYTHONPATH.

Remove this patch (and the PYTHONPATH entry in the Dockerfile) once cblaster
ships a release with the fix.
"""

from __future__ import annotations

import sys

#: Ids per NCBI IPG efetch request (cblaster default is 1000; the author
#: reproduced failures until dropping it to ~100).
_IPG_CHUNK = 100
#: Maximum records NCBI returns per request (cblaster 1.4.0 uses 1000).
_RETMAX = 10000


def _apply() -> None:
    import cblaster.context as ctx
    from Bio import Entrez

    def efetch_request(ids):
        return Entrez.efetch(
            "ipg", rettype="ipg", retmode="text", id=ids, retmax=_RETMAX
        )

    def efetch_IPGs(ids, output_file=None):
        if not ids:
            raise ValueError("No ids specified")
        table: list[str] = []
        for start in range(0, len(ids), _IPG_CHUNK):
            chunk = ids[start : start + _IPG_CHUNK]
            handle = efetch_request(chunk)
            if handle.code != 200:
                raise RuntimeError(f"Bad response from NCBI [code {handle.code}]")
            for line in handle:
                if isinstance(line, bytes):
                    line = line.decode()
                table.append(line.strip("\n"))
        if output_file:
            with open(output_file, "w") as fp:
                for line in table:
                    fp.write(line + "\n")
        return table

    ctx.efetch_request = efetch_request
    ctx.efetch_IPGs = efetch_IPGs


# Only patch when the running program is cblaster itself.
if sys.argv and sys.argv[0].rsplit("/", 1)[-1].startswith("cblaster"):
    try:
        _apply()
    except Exception:
        pass
