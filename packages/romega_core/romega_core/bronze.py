"""BronzeStore — cache content-addressed pentru artefacte brute (stratul bronze).

Orice fetch se salvează aici, imuabil, identificat prin sha256 al conținutului. Asigură:
- provenance (din ce a fost derivat orice fapt),
- reprocesare fără re-descărcare (index pe URL → re-rulările NU re-descarcă),
- dedup (același conținut = un singur fișier),
- thread-safe (descărcări paralele scriu în siguranță).

Layout: data/raw/{source_id}/{sha[:2]}/{sha}{ext} + un manifest.jsonl la rădăcină.
"""

from __future__ import annotations

import hashlib
import json
import threading
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path


@dataclass(frozen=True)
class BronzeArtifact:
    source_id: str
    url: str
    fetched_at: str  # ISO 8601 UTC
    sha256: str
    path: str        # relativ la rădăcina store-ului

    def source_ref(self):
        from romega_core.provenance import SourceRef

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
        self._lock = threading.Lock()
        self._by_url: dict[str, dict] = {}  # url -> artifact dict
        self._load_index()

    def _load_index(self) -> None:
        if not self.manifest.exists():
            return
        with self.manifest.open(encoding="utf-8") as f:
            for line in f:
                try:
                    a = json.loads(line)
                    self._by_url[a["url"]] = a
                except Exception:
                    continue

    def _path_for(self, source_id: str, sha: str, ext: str) -> Path:
        return self.root / source_id / sha[:2] / f"{sha}{ext}"

    def has(self, source_id: str, sha: str, ext: str = "") -> bool:
        return self._path_for(source_id, sha, ext).exists()

    def has_url(self, url: str) -> bool:
        return url in self._by_url

    def put(self, source_id: str, url: str, content: bytes, ext: str = "") -> BronzeArtifact:
        """Salvează conținutul (dedup pe sha256, thread-safe). Manifest + index actualizate o dată."""
        sha = hashlib.sha256(content).hexdigest()
        path = self._path_for(source_id, sha, ext)
        art = BronzeArtifact(
            source_id=source_id,
            url=url,
            fetched_at=datetime.now(timezone.utc).isoformat(),
            sha256=sha,
            path=str(path.relative_to(self.root)),
        )
        with self._lock:
            if not path.exists():
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(content)
            if url not in self._by_url:
                self._by_url[url] = asdict(art)
                with self.manifest.open("a", encoding="utf-8") as f:
                    f.write(json.dumps(asdict(art), ensure_ascii=False) + "\n")
        return art

    def get(self, source_id: str, sha: str, ext: str = "") -> bytes | None:
        path = self._path_for(source_id, sha, ext)
        return path.read_bytes() if path.exists() else None

    def get_by_url(self, url: str) -> bytes | None:
        """Conținutul cache-uit pentru un URL (None dacă nu e cache-uit) — sare peste re-download."""
        a = self._by_url.get(url)
        if not a:
            return None
        path = self.root / a["path"]
        return path.read_bytes() if path.exists() else None

    def artifact_for_url(self, url: str) -> BronzeArtifact | None:
        a = self._by_url.get(url)
        return BronzeArtifact(**a) if a else None

    def count(self) -> int:
        return len(self._by_url)
