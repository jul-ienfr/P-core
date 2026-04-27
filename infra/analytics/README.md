# Prediction Core Analytics Stack

Final cockpit stack:

- ClickHouse: analytical source of truth
- Grafana: dashboards and alerting

Start locally:

```bash
cd /home/jul/P-core/infra/analytics
docker compose up -d
```

Open Grafana:

- URL: http://127.0.0.1:3000
- Default local user: `admin`
- Default local password: `admin`

Never use these defaults outside local development.
