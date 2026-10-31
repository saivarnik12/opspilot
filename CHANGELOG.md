# Changelog

## 0.4.0
- Monitoring dashboard (served at /app): sign in/up, overview, charts, log explorer, incidents, API keys
- API: log text search, X-Total-Count header, /logs/timeseries
- Browser-level end-to-end test and CI job
- Dark/light themes, sidebar layout, mobile-first responsive design, API health indicator
- Fix: logs are now ordered by event time (late-arriving logs no longer appear as "latest")
- Index on (user_id, timestamp) for time-ordered queries

## 0.3.0
- Error-pattern detection, Claude-powered incident analysis with rule-engine fallback, incident lifecycle

## 0.2.0
- JWT authentication, user registration/login, API keys, per-user data isolation

## 0.1.0
- Log ingestion API (single and batch), filtering, stats, Docker, CI
