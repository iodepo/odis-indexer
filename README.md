# ODIS indexer tools/flow

**Start here for a fast end-to-end run:** [QUICKSTART.md](./QUICKSTART.md)

## Pipeline

```
Sitemap / pages
      │
      ▼
  summoner  ──JSON-LD──►  S3  summoned/<source>/<sha1>.json
                              │
              ┌───────────────┴───────────────┐
              ▼                               ▼
           scribe                          indexer
              │                               │
              ▼                               ▼
     Oxigraph graphs                 Elasticsearch index
     urn:odis:<source>              odis-<source>
     urn:odis:prov:<source>                   │
                                              ▼
                                    ui/  (browser search)
```

| Package | Role |
|---------|------|
| `summoner` | Sitemap → extract JSON-LD → S3 |
| `scribe` | S3 JSON-LD → N-Quads in named graph → Oxigraph |
| `indexer` | S3 JSON-LD → Elasticsearch (search facade + full JSON-LD) |
| `visualizer/` | Visualizes the Oxigraph graph |
| `visualizer/ui/` | Static HTML/JS search UI over Elasticsearch |

## Requirements

- Python ≥ 3.11
- Docker (compose files under `build/` for ES, Oxigraph, Browserless; S3 usually LocalStack/MinIO)
- S3-compatible store (LocalStack, MinIO, AWS, …) — default config: `localhost:4566`, bucket `iode`
- Oxigraph for `scribe` / `visualizer` — default `http://localhost:7878` (`build/docker-compose.oxigraph.yaml`)
- Elasticsearch 8 for `indexer` / Search UI — default `http://localhost:9400` (`build/docker-compose.es.yaml`)

## Install

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Config (`config.yaml`)

| Node | Purpose |
|------|---------|
| `objectstore` | S3 endpoint (`ssl: false` → HTTP, `true` → HTTPS) |
| `triplestore` | Oxigraph (`type: oxigraph`, `endpoint`) |
| `search` | Elasticsearch (`type: elasticsearch`, `endpoint`, `index_prefix`) |
| `summoner` | `threads`, `delay`, `user_agent`, **Browserless** `headless` URL + token/timeouts |
| `sources[]` | Sitemap sources; `active: true`; set `headless: true` to use Browserless for that source |

### Identity layout

| Store | Key |
|-------|-----|
| S3 | `summoned/<source>/<sha1(page_url)>.json` |
| S3 metadata | `source-url` = harvest page; `source-name` = source |
| Oxigraph (data) | Named graph `urn:odis:<source>` |
| Oxigraph (prov) | Named graph `urn:odis:prov:<source>` |
| Elasticsearch | Index `odis-<source>` (or `{index_prefix}-<source>`) |

### Provenance (how stages connect)

| Link | Status |
|------|--------|
| Harvest page URL → S3 | **Yes** — object metadata + SHA1 key |
| S3 → Elasticsearch | **Yes** — `s3_key`, plus `source_url` from metadata |
| S3 / ES → Oxigraph (source) | **Yes** — shared `urn:odis:<source>` |
| Entity `@id` across ES / graph | **When present** in JSON-LD |
| Harvest URL in Oxigraph | **Yes** — PROV-O in `urn:odis:prov:<source>` (`prov:hadPrimarySource`, `prov:value` = s3 key) |

UI links prefer Schema.org **`url`**, then harvest **`source_url`**, then `@id` if it is `http(s)`.

---

## Visualizer

Generates an interactive HTML graph visualization from Oxigraph data.

```bash
python visualizer/visualize.py --source medin
# Generates visualizer/oxigraph_graph.html
```

| Flag | Meaning |
|------|---------|
| `--source` / `-s` | **Required.** Source name (graph `urn:odis:<source>`) |
| `--config` / `-c` | Path to YAML |

The output file can be opened directly in a browser. It uses local dependencies in `visualizer/lib/`.

---

## Running the indexer (Gateway & Manager)

Execute summoner, scribe, and indexer in sequence for one or all sources.

### Parallel Execution (Manager)

Run the entire pipeline for all sources in parallel. Concurrency is limited by `max_parallel_processes` in `config.yaml`.

```bash
# Process all active sources in parallel
python manager.py --limit 5
```

This command should be run from the crontab once a day.

Enter this in crontab, adjust the path to your path.
```crontab
0 2 * * * cd /data/odis-indexer && ./.venv/bin/python manager.py > /data/odis-indexer/logs/manager.log 2>&1
```

### Sequential Execution (Gateway)

```bash
# Process a single source
python gateway.py --source medin

# Process ALL active sources sequentially
python gateway.py --source all
```

| Flag | Meaning |
|------|---------|
| `--config` / `-c` | Path to YAML |
| `--source` / `-s` | Source name OR `all` |
| `--limit N` | Cap processing per source |
| `--dry-run` | No writes to S3, Oxigraph, or ES |
| `--rude` | Skip robots.txt (summoner) |
| `-v` | Debug logging |

---

## Summoner

Sitemap walk + JSON-LD extraction → S3.

- **Default:** static HTTP fetch (fast; works for medin).
- **`headless: true` on a source:** uses **Browserless** (`POST /chromium/content`) for rendered HTML, then the same extractor.
- **Hybrid (default):** even for headless sources, try static first; fall back to Browserless only if no JSON-LD.

### Browserless (Docker)

```bash
docker compose -f build/docker-compose.browserless.yaml up -d
# TOKEN defaults to odis-local-token (must match summoner.headless_token)
curl -s -o /dev/null -w "%{http_code}\n" \
  "http://localhost:3000/active?token=odis-local-token"
```

| Config key | Meaning |
|------------|---------|
| `summoner.headless` | Browserless base URL, e.g. `http://localhost:3000` |
| `summoner.headless_token` | API token (`BROWSERLESS_TOKEN` env also works) |
| `summoner.headless_concurrent` | Client-side max concurrent browser renders |
| `summoner.headless_hybrid` | Static first, then Browserless if needed |
| `sources[].headless` | Opt-in Browserless for that source |

**Not a Cloudflare bypass.** Open-source Browserless does not solve bot walls (e.g. CIOOS HTML 403). 
Headless only helps when JS actually injects JSON-LD into the DOM.

```bash
python -m summoner --config config.yaml
python -m summoner --config config.yaml --source medin --limit 5
python -m summoner --config config.yaml --source medin --limit 5 --dry-run -v
```

| Flag | Meaning |
|------|---------|
| `--config` / `-c` | Path to YAML |
| `--source` / `-s` | Single source `name` or `all` |
| `--limit N` | Cap page URLs per source |
| `--dry-run` | Extract only; do not write S3 |
| `--rude` | Skip robots.txt |
| `-v` | Debug logging |

---

## Scribe

Load summoned JSON-LD into Oxigraph as quads. 
**Replaces** both the data and provenance named graphs on each run (`CLEAR` then bulk N-Quads).

| Graph | Contents |
|-------|----------|
| `urn:odis:<source>` | Triples from JSON-LD body |
| `urn:odis:prov:<source>` | PROV-O harvest/load links (page URL, s3 key, optional `@id`) |

Per summoned object, provenance includes roughly:

- object entity `urn:odis:object:<source>:<sha>` with `prov:value` = S3 key
- `prov:hadPrimarySource` → harvest page URL (from S3 `source-url` metadata)
- `prov:wasDerivedFrom` → JSON-LD `@id` when present
- `rdfs:seeAlso` → data graph `urn:odis:<source>`
- load `prov:Activity` + agent `urn:odis:agent:scribe`

```bash
python -m scribe --config config.yaml --source medin
python -m scribe --config config.yaml --source medin --limit 10 --dry-run -v
```

| Flag | Meaning |
|------|---------|
| `--source` / `-s` | **Required.** S3 prefix under `summoned/` |
| `--limit N` | Cap objects loaded |
| `--dry-run` | Convert only; do not touch Oxigraph |
| `-v` | Debug logging |

Example SPARQL — harvest URL → S3 key → entity:

```sparql
PREFIX prov: <http://www.w3.org/ns/prov#>

SELECT ?harvest ?s3key ?entity WHERE {
  GRAPH <urn:odis:prov:medin> {
    ?obj a prov:Entity ;
         prov:value ?s3key ;
         prov:hadPrimarySource ?harvest .
    OPTIONAL { ?obj prov:wasDerivedFrom ?entity }
  }
}
```

Verify with SPARQL:

```bash
curl -s -X POST http://localhost:7878/query \
  -H 'Accept: application/sparql-results+json' \
  -H 'Content-Type: application/sparql-query' \
  --data 'SELECT (COUNT(*) AS ?c) WHERE { GRAPH <urn:odis:medin> { ?s ?p ?o } }'
```

---

## Indexer

Load summoned JSON-LD into Elasticsearch for text search. **Per source**, replace index on each run.

Documents include a **search facade** (`name`, `description`, `keywords`, `type`, `url`, `source_url`, …) plus full JSON-LD under `jsonld` (stored, not deeply mapped).

### Elasticsearch (Docker)

```bash
docker compose -f build/docker-compose.es.yaml up -d
curl -s http://localhost:9400
```

Security is off and CORS is on for local demos only (see compose file).

### Run

```bash
python -m indexer --config config.yaml --source medin
python -m indexer --config config.yaml --source medin --limit 5 --dry-run -v
```

| Flag | Meaning |
|------|---------|
| `--source` / `-s` | **Required.** S3 prefix under `summoned/` |
| `--limit N` | Cap S3 objects |
| `--dry-run` | Build docs only; no ES writes |
| `-v` | Debug logging |

### Search examples

```bash
curl -s 'http://localhost:9400/odis/_count'
curl -s 'http://localhost:9400/odis/_search' \
  -H 'Content-Type: application/json' \
  -d '{"query":{"multi_match":{"query":"coastal","fields":["name","description","keywords"]}},"_source":["name","url","source_url"]}'
```

---

## Search UI

Static page under `visualizer/ui/` (no build step). Requires Elasticsearch with CORS (enabled in `build/docker-compose.es.yaml`).

The UI has been updated with:
- **Dark Mode Support:** Toggle between light and dark themes.
- **Improved Result Cards:** Better display of metadata and provenance.
- **JSON-LD Inspection:** Expandable sections to view the raw harvested JSON-LD.
- **Direct Deep-linking:** Support for `?q=searchterm` in the URL.

```bash
# after indexer has loaded a source
cd visualizer/ui
python -m http.server 8080
# open http://localhost:8080
```

See [visualizer/ui/README.md](./visualizer/ui/README.md) for UI-specific notes and provenance detail.

---

## Tests

```bash
pytest -q
```

## Notes

- Be polite when summoning: default delay is 250 ms and robots.txt is honored unless `--rude`.
- Multiple `application/ld+json` blocks on one page are stored as a JSON array (one ES document per element when indexing).
- Scribe and indexer reloads are idempotent per source (clear graph / replace index).
- Demo sources differ: **medin** works well for static harvest; some sitemaps (e.g. **cioos**) may be blocked by bot protection.
