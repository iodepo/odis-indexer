"""Load and validate config.yaml."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

@dataclass(frozen=True)
class ObjectStoreConfig:
    address: str
    port: int
    access_key: str
    secret_key: str
    ssl: bool
    bucket: str
    region: str = "us-east-1"

    @property
    def endpoint(self) -> str:
        """Host:port for the MinIO client."""
        return f"{self.address}:{self.port}"

    @property
    def base_url(self) -> str:
        scheme = "https" if self.ssl else "http"
        return f"{scheme}://{self.endpoint}"


@dataclass(frozen=True)
class SummonerConfig:
    """Crawl settings including optional Browserless headless endpoint."""

    headless_timeout_ms: int
    headless_concurrent: int
    headless_wait_ms: int
    threads: int
    delay: int
    user_agent: str
    headless: str = ""
    headless_token: str = ""
    headless_wait_for_ldjson: bool = True
    headless_block_assets: bool = True
    # hybrid: try static first even when source.headless=true; fall back to Browserless
    headless_hybrid: bool = True

    @property
    def headless_configured(self) -> bool:
        return bool(self.headless and self.headless.strip())


@dataclass(frozen=True)
class SourceConfig:
    sourceid: str
    url: str
    sourcetype: str = "sitemap"
    active: bool = True
    headless: bool = False
    name: str = ""
    # Extra fields from YAML are ignored at construction time.


@dataclass(frozen=True)
class AppConfig:
    objectstore: ObjectStoreConfig
    summoner: SummonerConfig
    sources: list[SourceConfig] = field(default_factory=list)

    def select_sources(self, sourceid: str | None = None) -> list[SourceConfig]:
        """Return active sources, optionally filtered by sourceid."""
        selected = [s for s in self.sources if s.active]
        if sourceid is not None:
            selected = [s for s in selected if s.sourceid == sourceid]
        return selected


def _require(data: dict[str, Any], key: str, ctx: str) -> Any:
    if key not in data:
        raise ValueError(f"Missing required key '{key}' in {ctx}")
    return data[key]


def _parse_objectstore(raw: dict[str, Any]) -> ObjectStoreConfig:
    return ObjectStoreConfig(
        address=str(_require(raw, "address", "objectstore")),
        port=int(_require(raw, "port", "objectstore")),
        access_key=str(_require(raw, "accessKey", "objectstore")),
        secret_key=str(_require(raw, "secretKey", "objectstore")),
        ssl=bool(raw.get("ssl", False)),
        bucket=str(_require(raw, "bucket", "objectstore")),
        region=str(raw.get("region", "us-east-1")),
    )


def _parse_summoner(raw: dict[str, Any] | None) -> SummonerConfig:
    if not raw:
        raise ValueError("Missing 'summoner' section in config")

    token = os.environ.get("BROWSERLESS_TOKEN", "")
    if not token:
        token = str(raw.get("headless_token", "") or raw.get("headlessToken", "") or "")

    return SummonerConfig(
        headless=str(raw.get("headless", "") or ""),
        headless_token=token,
        headless_timeout_ms=int(
            raw.get("headless_timeout_ms", raw.get("headlessTimeoutMs", 0))
            or _require(raw, "headless_timeout_ms", "summoner")
        ),
        headless_concurrent=int(
            raw.get("headless_concurrent", raw.get("headlessConcurrent", 0))
            or _require(raw, "headless_concurrent", "summoner")
        ),
        headless_wait_ms=int(
            raw.get("headless_wait_ms", raw.get("headlessWaitMs", 0))
            or _require(raw, "headless_wait_ms", "summoner")
        ),
        headless_wait_for_ldjson=bool(
            raw.get("headless_wait_for_ldjson", raw.get("headlessWaitForLdjson", True))
        ),
        headless_block_assets=bool(
            raw.get("headless_block_assets", raw.get("headlessBlockAssets", True))
        ),
        headless_hybrid=bool(raw.get("headless_hybrid", raw.get("headlessHybrid", True))),
        threads=int(_require(raw, "threads", "summoner")),
        delay=int(_require(raw, "delay", "summoner")),
        user_agent=str(_require(raw, "user_agent", "summoner")),
    )


def _parse_source(raw: dict[str, Any]) -> SourceConfig:
    sourceid = str(_require(raw, "sourceid", "sources[]"))
    url = str(_require(raw, "url", f"sources[{sourceid}]"))
    return SourceConfig(
        sourceid=sourceid,
        url=url,
        sourcetype=str(raw.get("sourcetype", "sitemap") or "sitemap"),
        active=bool(raw.get("active", True)),
        headless=bool(raw.get("headless", False)),
        name=str(raw.get("name", "") or ""),
    )


def load_sources_yaml(path: str | Path) -> list[SourceConfig]:
    """Load sources from an external YAML file (e.g. sources.yaml)."""
    sources_path = Path(path)
    if not sources_path.is_file():
        return []

    with sources_path.open(encoding="utf-8") as fh:
        data = yaml.safe_load(fh)

    if not isinstance(data, dict):
        return []

    raw_sources = data.get("sources") or []
    if not isinstance(raw_sources, list):
        return []

    return [_parse_source(item) for item in raw_sources if isinstance(item, dict)]


def load_config(path: str | Path) -> AppConfig:
    """Load and validate configuration from a YAML file."""
    config_path = Path(path)
    if not config_path.is_file():
        raise FileNotFoundError(f"Config file not found: {config_path}")

    with config_path.open(encoding="utf-8") as fh:
        data = yaml.safe_load(fh)

    if not isinstance(data, dict):
        raise ValueError(f"Config root must be a mapping: {config_path}")

    objectstore = _parse_objectstore(_require(data, "objectstore", "config"))
    summoner = _parse_summoner(data.get("summoner"))
    raw_sources = data.get("sources") or []
    if not isinstance(raw_sources, list):
        raise ValueError("'sources' must be a list")

    sources = [_parse_source(item) for item in raw_sources if isinstance(item, dict)]

    # If no sources in config.yaml, try loading from sources.yaml in same directory
    if not sources:
        sources_path = config_path.parent / "sources.yaml"
        if sources_path.is_file():
            sources = load_sources_yaml(sources_path)

    return AppConfig(objectstore=objectstore, summoner=summoner, sources=sources)
