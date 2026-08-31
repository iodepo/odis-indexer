# ODIS indexer Docker compose files

Compose files for local demos. Run from the root directory so paths and project names stay consistent:

```bash
# Elasticsearch (search / UI)
docker compose -f build/docker-compose.es.yaml up -d

# Oxigraph (scribe / SPARQL)
docker compose -f build/docker-compose.oxigraph.yaml up -d

# Browserless (optional headless summoner)
docker compose -f build/docker-compose.browserless.yaml up -d

# Object store (LocalStack / MinIO)
docker compose -f build/docker-compose.floci.yaml up -d
```

| File | Service              | Port | Used by                          |
|------|----------------------|------|----------------------------------|
| `docker-compose.floci.yaml` | S3 store             | 4566 | `summoner`                       |
| `docker-compose.es.yaml` | Elasticsearch 8      | 9200 | `indexer`, `ui/`                 |
| `docker-compose.oxigraph.yaml` | Oxigraph             | 7878 | `scribe`                         |
| `docker-compose.browserless.yaml` | Browserless Chromium | 3000 | `summoner` when `headless: true` |
