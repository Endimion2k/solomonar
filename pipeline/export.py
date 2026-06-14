"""Export — gold → data/v1/*.json (stratul public).

v0: wrapper subțire peste solomonar_core.io. Pe măsură ce cresc entitățile, aici se adaugă
export-ul pe colecții (persoane/, organizatii/, companii/, ...) + status.json + feeds.
"""

from __future__ import annotations

from solomonar_core.io import export_collection

__all__ = ["export_collection"]
