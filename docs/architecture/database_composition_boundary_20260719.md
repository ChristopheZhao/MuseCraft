# Database Composition Boundary

## Decision

Database deployment selection belongs to one infrastructure composition owner. API, Celery, maintenance commands, Alembic, and the uv launcher consume its typed configuration or preflight result; Agents, MAS control-plane services, algorithms, queues, and launchers do not parse database URLs or select drivers.

## Profiles

| Profile | Default | Accepted backend | Contract |
| --- | --- | --- | --- |
| `local` | yes | PostgreSQL | Uses a documented localhost URL when `DATABASE_URL` is absent; an explicit PostgreSQL URL may override it. |
| `production` | no | PostgreSQL | Requires an explicit URL and rejects localhost plus known example/development credentials. |
| `test` | no | SQLite or PostgreSQL | Must be selected explicitly by test infrastructure; SQLite is not a release provider claim. |

MySQL is not a registered release adapter. Historical MySQL migrations and data require reviewed reconciliation and cannot enter the release baseline through a driver fallback, silent stamp, or launcher exception.

## Ownership

The infrastructure composition owner must provide:

- strict profile and URL normalization with typed reason codes;
- registered sync, async, and Alembic driver URLs;
- sync/async engines and session factories;
- a typed connection preflight result with sanitized diagnostics;
- the migration capability decision consumed by Alembic and startup entrypoints.

Allowed consumers:

- `app/core/database.py` may expose application session dependencies by delegating construction to the composition owner;
- Alembic may request the migration URL and capability but may not adapt drivers itself;
- uv and maintenance launchers may render typed preflight results but may not import SQLAlchemy engine constructors or branch on a backend;
- Docker/Compose may inject deployment environment values, but application behavior still resolves through the same composition owner.

## Failure Contract

Configuration failures raise a typed contract error before engine creation or migrations. Connection preflight returns an explicit typed diagnostic. Unknown backend, invalid URL, missing production URL, production localhost, unsafe production credentials, unsupported migration capability, and connection failure remain distinguishable. No error path may downgrade to another backend or local credentials.

Diagnostics may expose profile, backend, reason code, and exception type. They must not expose URL passwords or full connection strings.

## Negative Boundaries

- Agents, MAS control planes, queue transports, API endpoints, and launchers do not call `create_engine`, `create_async_engine`, `make_url`, or driver-name replacement logic.
- `DATABASE_HOST`, `DATABASE_PORT`, `DATABASE_NAME`, `DATABASE_USER`, and `DATABASE_PASSWORD` are deployment inputs for Compose only; they are not a second application configuration source beside `DATABASE_URL`.
- SQLite migration smoke is test evidence only and cannot close PostgreSQL transaction or release support claims.
- A successful connection does not imply schema compatibility; Alembic remains the schema owner.

## Transitional Debt Ratchet

At freeze time, provider/profile/driver policy is duplicated in exactly:

- `app/core/config.py`
- `app/core/database.py`
- `alembic/env.py`
- `scripts/start_dev.py`
- `scripts/start_dev_uv.py`

The executable architecture test must match this set exactly and reach an empty set before Gate E closes.
