# Storage

Generated assets (images, videos, audio, documents, websites, per-project
files) live here on disk, not in PostgreSQL — the database stores only
metadata and a path/URL reference (see `backend/app/models`, extended in
later phases with a `File`/`Asset` model).

This directory is the default `StorageProvider` implementation's root. Its
layout mirrors the categories in the platform spec:

```
storage/
├── images/
├── videos/
├── audio/
├── documents/
├── websites/
└── projects/
```

Nothing is written here yet — the Creative Studio phases are what
populate it. The directory (and this abstraction point) exists now so the
storage architecture doesn't have to be retrofitted later.
