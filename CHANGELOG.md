# Changelog

All notable changes to MuseCraft are documented here. The project follows Keep a Changelog structure; versioning will use Semantic Versioning once the first public release is tagged.

## Unreleased

### Added

- Tracked PostgreSQL release migration baseline and migration contract tests.
- Locked backend dependency graph and generated requirements compatibility export.
- Reproducible backend/frontend release checks.
- Public contribution, security and conduct policies.

### Changed

- MAS control-plane decisions and boundary reports now fail closed with typed diagnostics.
- Media completion uses scene-output acceptance facts.
- Docker Compose runs migrations before starting runtime services.
- Documentation now describes one PostgreSQL-first environment contract.
- Frontend runtime and lint tooling now use patched Next.js 15.5.20 with a zero-vulnerability npm lockfile.

### Removed

- Nonexistent `hashlib3` dependency.
- Production frontend logging of full task request payloads.
