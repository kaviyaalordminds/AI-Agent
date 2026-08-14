# Storage

Generated assets (images, videos, audio, documents, websites, per-project
files) live here on disk, not in PostgreSQL — the database stores only
metadata and a path/URL reference (see `backend/app/models`, extended in
later phases with a `File`/`Asset` model).

This directory is `LocalStorageProvider`'s root (see
`backend/app/integrations/storage/`) — the default, real implementation
of the `StorageProvider` abstraction every generation module writes
through. Its layout mirrors the categories in the platform spec, further
namespaced by user id:

```
storage/
├── documents/{user_id}/…   real generated .md/.docx/.pdf files (Phase 7)
├── images/{user_id}/…      populated once Image generation ships
├── videos/{user_id}/…      populated once Video generation ships
├── audio/{user_id}/…       populated once Audio generation ships
├── websites/{user_id}/…    populated once Website generation ships
└── projects/
```

`documents/` is populated as of Phase 7 (Document Generation) — every
file in it was written by a real user request through the Documents
Studio, never seeded or faked. Postgres never stores these bytes, only a
provider reference (`Document.storage_ref`); the download endpoint reads
through `StorageProvider`, never the raw filesystem path. The other
categories exist now so a future `S3Provider`/`GCSProvider` swap-in (or
just continuing to use `LocalStorageProvider` in production) never
requires touching call sites — same pattern as `EmailProvider`/
`ClaudeProvider`/`ObsidianProvider`.
