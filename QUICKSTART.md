# ODIS indexer QuickStart

Quickstart guide to get the full pipeline running: **summon → S3 → Oxigraph + Elasticsearch → search UI**.

Assumes Docker (or compatible compose), Python ≥ 3.11, and network access to a sitemap source (default demo: **medin**).

## get the source

you may want to install this in a separate partition on a server

```bash
cd /data
git clone git@github.com:iodepo/odis-indexer.git
cd odis-indexer
```

## Python env

```bash
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

## Services

You need three backends. 

All config for the dockers are to be found in config.yaml_example. 

```bash
cp config.yaml_example config.yaml
```

Adjust `config.yaml` if your hosts/ports differ.

| Service | Default                                                           | Purpose |
|---------|-------------------------------------------------------------------|---------|
| S3-compatible store | `http://localhost:4566` (HTTP, keys `test`/`test`, bucket `odis`) | JSON-LD objects |
| Oxigraph | `http://localhost:7878`                                           | Named-graph RDF |
| Elasticsearch 8 | `http://localhost:9400`                                           | Text search + UI |
| Browserless (optional) | `http://localhost:3000`                                           | JS-rendered HTML for headless sources |

Compose files live under **`build/`**. 

### Elasticsearch (included)

```bash
docker compose -f build/docker-compose.es.yaml up -d
curl -s http://localhost:9400   # expect cluster JSON
```

CORS is enabled for the browser UI.

### Oxigraph

```bash
docker compose -f build/docker-compose.oxigraph.yaml up -d
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:7878/  # expect 200
```

### Browserless (optional headless summoner)

Only needed when a source has `headless: true` (JSON-LD injected after JS).

```bash
docker compose -f build/docker-compose.browserless.yaml up -d
curl -s -o /dev/null -w "%{http_code}\n" \
  "http://localhost:3000/active?token=odis-local-token"   # expect 204 or 200
```

Match `summoner.headless` / `headless_token` in `config.yaml` to the compose service (`TOKEN=odis-local-token` by default).

### Object store (LocalStack / MinIO)

```bash
docker compose -f build/docker-compose.floci.yaml up -d
python - <<'PY'
from minio import Minio
c = Minio("localhost:4566", access_key="test", secret_key="test", secure=False)
print("buckets:", [b.name for b in c.list_buckets()])
PY
```

## create the sources file

make the sources file using info from https://catalogue.odis.org/

```bash
python make_sources.py
```
## Harvest JSON-LD (summoner)

```bash
# small real run (writes to S3)
python -m summoner --config config.yaml --source medin --limit 5

# dry-run only (no S3 write)
python -m summoner --config config.yaml --source medin --limit 5 --dry-run -v
```

Objects land at:

```text
s3://odis/summoned/medin/<sha1(page_url)>.json
```

Metadata on each object includes harvest page URL (`source-url`).

## Load graph (scribe → Oxigraph)

```bash
python -m scribe --config config.yaml --source medin
```

Named graphs:

- data: `urn:odis:medin`
- prov: `urn:odis:prov:medin` (harvest URL ↔ S3 key ↔ optional `@id`)

Check data:

```bash
curl -s -X POST http://localhost:7878/query \
  -H 'Accept: application/sparql-results+json' \
  -H 'Content-Type: application/sparql-query' \
  --data 'SELECT (COUNT(*) AS ?c) WHERE { GRAPH <urn:odis:medin> { ?s ?p ?o } }'
```

Check provenance:

```bash
curl -s -X POST http://localhost:7878/query \
  -H 'Accept: application/sparql-results+json' \
  -H 'Content-Type: application/sparql-query' \
  --data 'PREFIX prov: <http://www.w3.org/ns/prov#> SELECT ?harvest ?s3key WHERE { GRAPH <urn:odis:prov:medin> { ?o prov:hadPrimarySource ?harvest ; prov:value ?s3key } } LIMIT 5'
```

## Load search (indexer → Elasticsearch)

```bash
python -m indexer --config config.yaml --source medin
```

Index: `odis-medin`

Check:

```bash
curl -s 'http://localhost:9400/odis-medin/_count'
curl -s 'http://localhost:9400/odis-medin/_search' \
  -H 'Content-Type: application/json' \
  -d '{"query":{"multi_match":{"query":"topographic","fields":["name","description","keywords"]}},"_source":["name","url","source_url"]}'
```

## Search UI

```bash
cd ui
python -m http.server 8080
```

Open **http://localhost:8080** and search (e.g. `topographic` or `coastal`).

Edit `ui/config.js` if Elasticsearch is not at `http://localhost:9400`.

## One-shot cheat sheet

```bash
source .venv/bin/activate

docker compose -f build/docker-compose.es.yaml up -d
docker compose -f build/docker-compose.oxigraph.yaml up -d
docker compose -f build/docker-compose.floci.yaml up -d
docker compose -f build/docker-compose.browserless.yaml up -d

python -m summoner --config config.yaml --source medin --limit 5
python -m scribe   --config config.yaml --source medin
python -m indexer  --config config.yaml --source medin

cd ui && python -m http.server 8080
```

## Troubleshooting

| Symptom | What to check |
|---------|----------------|
| Summoner 403 on sitemap | Source blocks bots (e.g. Cloudflare). Try `medin`; `cioos` often fails. |
| Summoner finds pages, no JSON-LD | Page lacks `ld+json`, or needs `headless: true` + Browserless if JS-injected. |
| Headless 401 / connection refused | `docker compose -f build/docker-compose.browserless.yaml up -d`; match `headless_token` to compose `TOKEN`. |
| CIOOS / Cloudflare 403 | Open-source Browserless is not a bot bypass; use API path or allowlisting. |
| Scribe cannot connect | `docker compose -f build/docker-compose.oxigraph.yaml up -d`; `curl http://localhost:7878/` |
| Indexer connection refused | `docker compose -f build/docker-compose.es.yaml up -d` and wait until healthy |
| UI “Search failed” / CORS | Recreate ES with current compose (CORS uses `/.*/`). Serve UI via `http.server`, not `file://` |
| Empty ES after index | Confirm S3 has `summoned/<source>/` objects first |
| Wrong S3 endpoint | Match `objectstore` in `config.yaml` (port, ssl, keys, bucket) |

## What links what

| Field | Meaning |
|-------|---------|
| S3 key `summoned/{source}/{sha1}.json` | Deterministic from harvest page URL |
| S3 meta `source-url` | Harvest page summoner fetched |
| ES `source_url` | Same harvest URL (copied by indexer) |
| ES `url` | Schema.org resource/landing page from JSON-LD |
| ES / Oxigraph data graph | `urn:odis:{source}` |
| Oxigraph data triples | From JSON-LD body |
| Oxigraph prov graph | `urn:odis:prov:{source}` — `prov:hadPrimarySource` (harvest URL), `prov:value` (s3 key) |

More detail: [README.md](./README.md), [ui/README.md](./ui/README.md).
