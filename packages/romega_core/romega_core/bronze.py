"""BronzeStore — cache content-addressed pentru artefacte brute (stratul bronze).

Orice fetch se salvează aici, imuabil, identificat prin sha256 al conținutului. Asigură:
- provenance (din ce a fost derivat orice fapt),
- reprocesare fără re-descărcare,
- dedup (același conținut = un singur fișier).

Layout: data/raw/{source_id}/{sha[:2]}/{sha}{ext} + un manifest.jsonl la rădăcină.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from romega_core.provenance import SourceRef


@dataclass(frozen=True)
class BronzeArtifact:
    source_id: str
    url: str
    fetched_at: str  # ISO 8601 UTC
    sha256: str
    path: str        # relativ la rădăcina store-ului

    def source_ref(self) -> SourceRef:
        return SourceRef(
            source_id=self.source_id,
            source_url=self.url,
            fetched_at=datetime.fromisoformat(self.fetched_at),
            bronze_sha256=self.sha256,
        )


class BronzeStore:
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.manifest = self.root / "manifest.jsonl"

    def _path_for(self, source_id: str, sha: str, ext: str) -> Path:
        return self.root / source_id / sha[:2] / f"{sha}{ext}"

    def has(self, source_id: str, sha: str, ext: str = "") -> bool:
        return self._path_for(source_id, sha, ext).exists()

    def put(self, source_id: str, url: str, content: bytes, ext: str = "") -> BronzeArtifact:
        """Salvează conținutul (dedup pe sha256). Manifestul primește o linie doar dacă e nou."""
        sha = hashlib.sha256(content).hexdigest()
        path = self._path_for(source_id, sha, ext)
        art = BronzeArtifact(
            source_id=source_id,
            url=url,
            fetched_at=datetime.now(timezone.utc).isoformat(),
            sha256=sha,
            path=str(path.relative_to(self.root)),
        )
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
            with self.manifest.open("a", encoding="utf-8") as f:
                f.write(json.dumps(asdict(art), ensure_ascii=False) + "\n")
        return art

    def get(self, source_id: str, sha: str, ext: str = "") -> bytes | None:
        path = self._path_for(source_id, sha, ext)
        return path.read_bytes() if path.exists() else None

    def count(self) -> int:
        if not self.manifest.exists():
            return 0
        with self.manifest.open(encoding="utf-8") as f:
            return sum(1 for _ in f)
