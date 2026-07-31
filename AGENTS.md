# AGENTS.md — patch_prioritization_orchestration

This repository is managed by the KinHelm Studio agent.

## Application Overview

**Patch Prioritization & Orchestration** is a Flask web application that ranks
patches by exploitability, asset criticality, exposure, and operational impact,
then generates rollout plans using AI-powered analysis.

## Architecture

- **Framework:** Flask 3.1 with Gunicorn
- **Database:** SQLite via Flask-SQLAlchemy
- **Auth:** Flask-Login with password hashing (Werkzeug)
- **RBAC:** Role-based access control (admin, analyst, operator, viewer)
- **Multi-tenancy:** Tenant isolation via foreign-key filtering on all queries
- **AI Integration:** Kindo AI agent via REST API (POST https://api.kindo.ai/v1/agents/runs)

## File Structure

```
├── app/
│   ├── __init__.py          # App factory, config, DB init, seed
│   ├── models.py            # SQLAlchemy models (Tenant, User, Role, Asset, Patch, RolloutPlan, etc.)
│   ├── routes/
│   │   ├── auth.py          # Login, register, logout
│   │   ├── main.py          # Dashboard, getting-started, settings
│   │   ├── patches.py       # Patch CRUD, AI analyze, AI enrich
│   │   ├── assets.py        # Asset CRUD
│   │   ├── rollout.py       # Rollout plan CRUD, AI generation, step tracking
│   │   ├── api.py           # JSON stats, audit log API
│   │   └── admin.py         # User management, audit, tenants
│   ├── services/
│   │   ├── kindo_agent.py   # Kindo AI agent client (analyze, enrich, generate)
│   │   └── rbac.py          # Role decorators, tenant filtering, audit logging
│   ├── templates/           # Jinja2 templates
│   └── static/              # CSS, JS
├── agent/
│   └── agent-config.yaml    # Kindo agent system prompt
├── wsgi.py                  # WSGI entry point
├── gunicorn.conf.py         # Gunicorn config
├── Dockerfile               # Container build
├── requirements.txt         # Python dependencies
└── .env.example             # Environment variable reference
```

## Key Environment Variables

| Variable | Required | Description |
|---|---|---|
| `SECRET_KEY` | Yes | Flask session secret |
| `KINDO_API_TOKEN` | For AI features | Kindo API bearer token |
| `KINDO_AGENT_ID` | For AI features | Kindo enrichment agent ID |
| `DATABASE_URL` | No | SQLAlchemy DB URI (default: SQLite) |
| `PORT` | No | Server port (default: 5000) |

## Default Credentials

- **Username:** admin
- **Password:** admin
- Change immediately after first login.

## RBAC Roles

| Role | Permissions |
|---|---|
| admin | Full access: user management, approvals, all CRUD |
| analyst | Create/edit patches, run AI analysis, create rollout plans |
| operator | Execute rollout plans, update step statuses, manage assets |
| viewer | Read-only access to all data |
