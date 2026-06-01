"""Client HTTP partajat — generalizat din cdep-api-poc/scrapers/_http.py.

Adăugiri față de original:
- **throttle PER-HOST** (nu global) — fiecare domeniu are propriul ritm;
- integrare **BronzeStore** (fetch → cache content-addressed + provenance);
- client ca obiect (mai multe instanțe cu config diferit), nu doar funcție de modul.

Păstrat din original (necesar pentru cdep.ro / senat.ro):
- adaptor SSL legacy (Oracle HTTP Server 12c, cipher SHA1, SECLEVEL=1);
- truststore (cert store OS — fix antivirus/firewall MITM pe Windows);
- retry pe 429/5xx.
"""

from __future__ import annotations

import ssl
import threading
import time
from typing import Any
from urllib.parse import urlparse

import requests
import truststore
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from urllib3.util.ssl_ import create_urllib3_context

from romega_core.bronze import BronzeArtifact, BronzeStore

# Folosește OS cert store în loc de certifi (Windows + antivirus MITM).
truststore.inject_into_ssl()

DEFAULT_USER_AGENT = (
    "ROMEGA-bot/0.1 (+https://github.com/Endimion2k/romega; transparenta date publice)"
)


class HostThrottle:
    """Throttle thread-safe, independent per host."""

    def __init__(self, seconds: float = 1.0) -> None:
        self.seconds = seconds
        self._last: dict[str, float] = {}
        self._lock = threading.Lock()

    def wait(self, host: str) -> None:
        with self._lock:
            now = time.monotonic()
            elapsed = now - self._last.get(host, 0.0)
            if elapsed < self.seconds:
                time.sleep(self.seconds - elapsed)
            self._last[host] = time.monotonic()


class _LegacySSLAdapter(HTTPAdapter):
    """Permite TLS legacy (SHA1 cipher suites) — necesar pentru cdep.ro."""

    def init_poolmanager(self, *args: Any, **kwargs: Any) -> Any:
        ctx = create_urllib3_context()
        ctx.set_ciphers("DEFAULT:@SECLEVEL=1")
        ctx.options |= 0x4  # OP_LEGACY_SERVER_CONNECT
        ctx.minimum_version = ssl.TLSVersion.TLSv1
        kwargs["ssl_context"] = ctx
        return super().init_poolmanager(*args, **kwargs)


class Client:
    def __init__(
        self,
        throttle_seconds: float = 1.0,
        timeout: float = 30.0,
        user_agent: str = DEFAULT_USER_AGENT,
        bronze: BronzeStore | None = None,
        legacy_ssl: bool = True,
    ) -> None:
        self.timeout = timeout
        self.throttle = HostThrottle(throttle_seconds)
        self.bronze = bronze
        self.session = self._build_session(user_agent, legacy_ssl)

    @staticmethod
    def _build_session(user_agent: str, legacy_ssl: bool) -> requests.Session:
        session = requests.Session()
        session.headers.update({"User-Agent": user_agent})
        retry = Retry(
            total=5,
            backoff_factor=2.0,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=frozenset(["GET", "HEAD", "POST"]),
            raise_on_status=False,
        )
        adapter_cls = _LegacySSLAdapter if legacy_ssl else HTTPAdapter
        adapter = adapter_cls(max_retries=retry, pool_connections=10, pool_maxsize=10)
        session.mount("https://", adapter)
        session.mount("http://", adapter)
        return session

    def get(self, url: str, **kwargs: Any) -> requests.Response:
        self.throttle.wait(urlparse(url).netloc)
        kwargs.setdefault("timeout", self.timeout)
        return self.session.get(url, **kwargs)

    def post(self, url: str, **kwargs: Any) -> requests.Response:
        self.throttle.wait(urlparse(url).netloc)
        kwargs.setdefault("timeout", self.timeout)
        return self.session.post(url, **kwargs)

    def fetch(self, url: str, source_id: str, ext: str = "") -> tuple[bytes, BronzeArtifact | None]:
        """GET + salvare în bronze. Întoarce (content, artefact)."""
        resp = self.get(url)
        resp.raise_for_status()
        content = resp.content
        art = self.bronze.put(source_id, url, content, ext) if self.bronze else None
        return content, art


# Client default de modul (convenabil pentru scripturi simple).
default_client = Client()


def get(url: str, **kwargs: Any) -> requests.Response:
    return default_client.get(url, **kwargs)
