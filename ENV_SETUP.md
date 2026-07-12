# Environment setup

MuseCraft has two local environment files, both at the repository root:

- `.env`: backend, worker, migration, provider and storage configuration.
- `.env.local`: browser-visible Next.js configuration.

Create them from the tracked templates:

```bash
cp .env.example .env
cp .env.local.example .env.local
```

## Backend

The public release path is PostgreSQL-first:

```dotenv
DATABASE_URL=postgresql://user:password@localhost:5432/short_video_maker
REDIS_URL=redis://localhost:6379/0
SECRET_KEY=replace-with-a-long-random-value
```

Configure only the provider credentials required by your selected tools. Explicit process/container variables override `.env`, which makes CI and deployment configuration authoritative.

## Frontend

```dotenv
NEXT_PUBLIC_API_URL=http://localhost:8000
NEXT_PUBLIC_WS_URL=ws://localhost:8000
```

Every `NEXT_PUBLIC_*` value is readable by browser users. Never place API keys or server credentials in `.env.local`.

## Docker Compose

`backend/docker-compose.yml` reads `../.env` for the API and workers, while overriding database/Redis hostnames for the container network. The migration service must complete before runtime services start.

## Safety checks

```bash
git status --short
git check-ignore -v .env .env.local
```

Do not distribute an archive of the whole working directory. Release only tracked Git content so ignored secrets, generated media and local business files are excluded.
