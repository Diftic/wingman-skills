# SC Log Donate Worker Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the Cloudflare Worker backend that receives log donations from the `sc_log_reader` skill, mints presigned R2 PUT URLs, and tracks uploads in D1.

**Architecture:** A standalone TypeScript Worker deployed via Wrangler. Three HTTP endpoints. Authentication via static shared-secret header. Files bypass the Worker - clients PUT directly to R2 using presigned S3-compatible URLs minted with `aws4fetch`. D1 stores upload manifests and a hash index for deduplication.

**Tech Stack:** Cloudflare Workers (TypeScript), Wrangler, R2, D1, `aws4fetch` for S3 signing, `vitest` + `@cloudflare/vitest-pool-workers` for tests.

**Repo location:** new repo at `D:\PycharmProjects\sc-log-donate\` (outside `wingman-ai`). Adjust path if you prefer a different location.

---

## Spec reference

This plan implements Section 4 ("Worker + R2 component"), Section 5 ("Deduplication", server-side half), and the Worker-side portions of Sections 6, 7, 8 from:

`skills/sc_log_reader/specs/2026-05-14-sc-log-donation-tool-design.md`

---

## File structure

```
sc-log-donate/
├── package.json
├── tsconfig.json
├── wrangler.toml
├── vitest.config.ts
├── .gitignore
├── .dev.vars                          (gitignored - local secrets)
├── README.md
├── TESTER.md
├── migrations/
│   └── 0001_initial.sql
├── src/
│   ├── worker.ts                      (entrypoint + routing)
│   ├── types.ts                       (request/response shapes)
│   ├── auth.ts                        (X-Donor-Token check)
│   ├── db.ts                          (D1 helpers)
│   ├── r2_presign.ts                  (mint S3-style presigned PUT URLs)
│   └── handlers/
│       ├── healthz.ts
│       ├── upload_begin.ts
│       └── upload_complete.ts
├── scripts/
│   └── reconcile.ts                   (one-off script for incomplete uploads)
├── tests/
│   ├── healthz.test.ts
│   ├── auth.test.ts
│   ├── upload_begin.test.ts
│   ├── upload_complete.test.ts
│   └── helpers.ts                     (test fixtures and env setup)
└── .github/
    └── workflows/
        └── deploy.yml                 (CI deploy to CF)
```

**File responsibilities:**

| File | Responsibility |
|---|---|
| `src/worker.ts` | Route requests to handlers. ~30 lines. No business logic. |
| `src/types.ts` | All request/response interfaces. Single source of truth for shapes. |
| `src/auth.ts` | One function: `checkToken(request, env) -> boolean`. |
| `src/db.ts` | D1 query helpers. Methods: `insertUpload`, `markComplete`, `lookupHashes`, `insertHashes`. |
| `src/r2_presign.ts` | One function: `mintPutUrl(env, key) -> string`. Wraps `aws4fetch`. |
| `src/handlers/healthz.ts` | Returns 200 `ok`. |
| `src/handlers/upload_begin.ts` | Validates body, looks up hashes, mints URLs, inserts D1 row. |
| `src/handlers/upload_complete.ts` | Marks D1 row complete, inserts new hashes, writes `manifest.json` to R2. |

---

## Task 0: Bootstrap repo

**Files:**
- Create: `D:\PycharmProjects\sc-log-donate\package.json`
- Create: `D:\PycharmProjects\sc-log-donate\tsconfig.json`
- Create: `D:\PycharmProjects\sc-log-donate\wrangler.toml`
- Create: `D:\PycharmProjects\sc-log-donate\vitest.config.ts`
- Create: `D:\PycharmProjects\sc-log-donate\.gitignore`
- Create: `D:\PycharmProjects\sc-log-donate\.dev.vars` (gitignored)
- Create: `D:\PycharmProjects\sc-log-donate\src\worker.ts` (stub)

- [ ] **Step 1: Create the repo directory and initialize git**

```powershell
New-Item -ItemType Directory -Path D:\PycharmProjects\sc-log-donate
Set-Location D:\PycharmProjects\sc-log-donate
git init
```

Expected: empty git repo on `main` branch.

- [ ] **Step 2: Write `package.json`**

```json
{
  "name": "sc-log-donate",
  "version": "0.1.0",
  "private": true,
  "type": "module",
  "scripts": {
    "dev": "wrangler dev",
    "deploy": "wrangler deploy",
    "test": "vitest run",
    "test:watch": "vitest",
    "typecheck": "tsc --noEmit",
    "migrate:local": "wrangler d1 migrations apply sc-log-donate-meta --local",
    "migrate:remote": "wrangler d1 migrations apply sc-log-donate-meta --remote"
  },
  "devDependencies": {
    "@cloudflare/vitest-pool-workers": "^0.5.0",
    "@cloudflare/workers-types": "^4.20240909.0",
    "typescript": "^5.6.0",
    "vitest": "^2.0.0",
    "wrangler": "^3.78.0"
  },
  "dependencies": {
    "aws4fetch": "^1.0.20"
  }
}
```

- [ ] **Step 3: Write `tsconfig.json`**

```json
{
  "compilerOptions": {
    "target": "ES2022",
    "module": "ES2022",
    "moduleResolution": "Bundler",
    "lib": ["ES2022"],
    "types": ["@cloudflare/workers-types"],
    "strict": true,
    "noEmit": true,
    "skipLibCheck": true,
    "esModuleInterop": true,
    "isolatedModules": true,
    "resolveJsonModule": true
  },
  "include": ["src/**/*.ts", "tests/**/*.ts", "scripts/**/*.ts"]
}
```

- [ ] **Step 4: Write `wrangler.toml`** (D1, R2, and rate-limit rule come in later tasks)

```toml
name = "sc-log-donate"
main = "src/worker.ts"
compatibility_date = "2024-09-09"
compatibility_flags = ["nodejs_compat"]

# R2 binding added in Task 5
# D1 binding added in Task 2
# Secrets set via `wrangler secret put` - listed in README
```

- [ ] **Step 5: Write `vitest.config.ts`**

```typescript
import { defineWorkersConfig } from "@cloudflare/vitest-pool-workers/config";

export default defineWorkersConfig({
  test: {
    poolOptions: {
      workers: {
        wrangler: { configPath: "./wrangler.toml" },
      },
    },
  },
});
```

- [ ] **Step 6: Write `.gitignore`**

```
node_modules/
.wrangler/
.dev.vars
*.log
dist/
.DS_Store
```

- [ ] **Step 7: Write `.dev.vars` for local secrets (NOT committed)**

```
DONOR_TOKEN=local-dev-token-do-not-ship
R2_ACCESS_KEY_ID=local-only
R2_SECRET_ACCESS_KEY=local-only
R2_ACCOUNT_ID=local-only
```

- [ ] **Step 8: Write stub `src/worker.ts`**

```typescript
export default {
  async fetch(_request: Request, _env: unknown): Promise<Response> {
    return new Response("not implemented", { status: 501 });
  },
};
```

- [ ] **Step 9: Install dependencies**

```powershell
npm install
```

Expected: `node_modules/` populated, `package-lock.json` created.

- [ ] **Step 10: Verify typecheck passes**

```powershell
npm run typecheck
```

Expected: no output, exit code 0.

- [ ] **Step 11: Commit**

```powershell
git add .gitignore package.json package-lock.json tsconfig.json wrangler.toml vitest.config.ts src/worker.ts
git commit -m "chore: bootstrap sc-log-donate worker repo"
```

---

## Task 1: D1 schema + migration

**Files:**
- Create: `migrations/0001_initial.sql`
- Modify: `wrangler.toml` (add D1 binding)

- [ ] **Step 1: Write `migrations/0001_initial.sql`**

```sql
-- Migration 0001: initial schema for sc-log-donate

CREATE TABLE IF NOT EXISTS uploads (
  upload_id        TEXT PRIMARY KEY,
  created_at       TEXT NOT NULL,
  client_ip        TEXT NOT NULL,
  skill_version    TEXT,
  wingman_version  TEXT,
  total_bytes      INTEGER NOT NULL DEFAULT 0,
  file_count       INTEGER NOT NULL DEFAULT 0,
  manifest_json    TEXT NOT NULL,
  complete         INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_uploads_created_at
  ON uploads (created_at);

CREATE INDEX IF NOT EXISTS idx_uploads_complete
  ON uploads (complete);

CREATE TABLE IF NOT EXISTS file_hashes (
  content_hash   TEXT PRIMARY KEY,
  upload_id      TEXT NOT NULL,
  r2_key         TEXT NOT NULL,
  first_seen_at  TEXT NOT NULL,
  FOREIGN KEY (upload_id) REFERENCES uploads(upload_id)
);

CREATE INDEX IF NOT EXISTS idx_file_hashes_upload_id
  ON file_hashes (upload_id);
```

- [ ] **Step 2: Create the local D1 database via Wrangler**

```powershell
npx wrangler d1 create sc-log-donate-meta
```

Expected: output prints a `database_id`. Copy it.

- [ ] **Step 3: Add D1 binding to `wrangler.toml`** (replace the comment placeholder)

```toml
name = "sc-log-donate"
main = "src/worker.ts"
compatibility_date = "2024-09-09"
compatibility_flags = ["nodejs_compat"]

[[d1_databases]]
binding = "DB"
database_name = "sc-log-donate-meta"
database_id = "<paste the database_id from step 2 here>"
migrations_dir = "migrations"
```

- [ ] **Step 4: Apply the migration locally**

```powershell
npm run migrate:local
```

Expected: output reports migration `0001_initial.sql` applied. No errors.

- [ ] **Step 5: Verify the schema with a query**

```powershell
npx wrangler d1 execute sc-log-donate-meta --local --command "SELECT name FROM sqlite_master WHERE type='table';"
```

Expected: lists `uploads`, `file_hashes`, and some `sqlite_*` system tables.

- [ ] **Step 6: Commit**

```powershell
git add migrations/0001_initial.sql wrangler.toml
git commit -m "feat: add D1 schema with uploads and file_hashes tables"
```

---

## Task 2: Type definitions

**Files:**
- Create: `src/types.ts`

- [ ] **Step 1: Write `src/types.ts`**

```typescript
export type InstallType = "Live" | "PTU" | "HOTFIX";

export interface UploadBeginFile {
  original_name: string;
  renamed: string;          // {handle_or_unknown}_{original_name}
  install: InstallType;
  game_version: string;
  size_bytes: number;
  sha256: string;           // 64-char lowercase hex
}

export interface UploadBeginRequest {
  client_version: string;
  wingman_version: string;
  files: UploadBeginFile[];
}

export type UploadBeginFileResult =
  | { sha256: string; put_url: string; key: string }
  | { sha256: string; already_uploaded: true; key: string };

export interface UploadBeginResponse {
  upload_id: string;
  files: UploadBeginFileResult[];
}

export interface UploadCompleteRequest {
  upload_id: string;
}

export interface UploadCompleteResponse {
  upload_id: string;
  complete: true;
}

export interface ErrorResponse {
  error: string;
}

export interface Env {
  DB: D1Database;
  BUCKET: R2Bucket;
  DONOR_TOKEN: string;
  R2_ACCESS_KEY_ID: string;
  R2_SECRET_ACCESS_KEY: string;
  R2_ACCOUNT_ID: string;
  R2_BUCKET_NAME: string;
}
```

- [ ] **Step 2: Verify typecheck**

```powershell
npm run typecheck
```

Expected: no errors.

- [ ] **Step 3: Commit**

```powershell
git add src/types.ts
git commit -m "feat: add request and response type definitions"
```

---

## Task 3: Health check endpoint (TDD)

**Files:**
- Create: `tests/helpers.ts`
- Create: `tests/healthz.test.ts`
- Create: `src/handlers/healthz.ts`
- Modify: `src/worker.ts`

- [ ] **Step 1: Write `tests/helpers.ts`**

```typescript
import { SELF } from "cloudflare:test";

export async function fetchWorker(
  path: string,
  init?: RequestInit
): Promise<Response> {
  return SELF.fetch(`https://example.com${path}`, init);
}
```

- [ ] **Step 2: Write the failing test `tests/healthz.test.ts`**

```typescript
import { describe, expect, it } from "vitest";
import { fetchWorker } from "./helpers";

describe("GET /healthz", () => {
  it("returns 200 ok", async () => {
    const res = await fetchWorker("/healthz");
    expect(res.status).toBe(200);
    expect(await res.text()).toBe("ok");
  });
});
```

- [ ] **Step 3: Run the test to verify it fails**

```powershell
npm test
```

Expected: test fails - the worker returns 501 for every path.

- [ ] **Step 4: Write `src/handlers/healthz.ts`**

```typescript
export function handleHealthz(): Response {
  return new Response("ok", { status: 200 });
}
```

- [ ] **Step 5: Update `src/worker.ts` to route `/healthz`**

```typescript
import { handleHealthz } from "./handlers/healthz";
import type { Env } from "./types";

export default {
  async fetch(request: Request, _env: Env): Promise<Response> {
    const url = new URL(request.url);

    if (request.method === "GET" && url.pathname === "/healthz") {
      return handleHealthz();
    }

    return new Response("not found", { status: 404 });
  },
};
```

- [ ] **Step 6: Run the test to verify it passes**

```powershell
npm test
```

Expected: 1 passed.

- [ ] **Step 7: Commit**

```powershell
git add tests/helpers.ts tests/healthz.test.ts src/handlers/healthz.ts src/worker.ts
git commit -m "feat: add healthz endpoint with passing test"
```

---

## Task 4: Auth middleware (TDD)

**Files:**
- Create: `tests/auth.test.ts`
- Create: `src/auth.ts`
- Modify: `src/worker.ts`

- [ ] **Step 1: Write the failing test `tests/auth.test.ts`**

```typescript
import { describe, expect, it } from "vitest";
import { fetchWorker } from "./helpers";

describe("auth on protected endpoints", () => {
  it("returns 401 when X-Donor-Token is missing on POST /upload/begin", async () => {
    const res = await fetchWorker("/upload/begin", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: "{}",
    });
    expect(res.status).toBe(401);
  });

  it("returns 401 when X-Donor-Token is wrong on POST /upload/begin", async () => {
    const res = await fetchWorker("/upload/begin", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Donor-Token": "wrong-token",
      },
      body: "{}",
    });
    expect(res.status).toBe(401);
  });

  it("does NOT enforce auth on GET /healthz", async () => {
    const res = await fetchWorker("/healthz");
    expect(res.status).toBe(200);
  });
});
```

- [ ] **Step 2: Run tests to verify the auth tests fail**

```powershell
npm test
```

Expected: 2 of 3 fail (`401 when missing` and `401 when wrong`), `healthz` passes.

- [ ] **Step 3: Write `src/auth.ts`**

```typescript
import type { Env } from "./types";

export function checkToken(request: Request, env: Env): boolean {
  const token = request.headers.get("X-Donor-Token");
  return token !== null && token === env.DONOR_TOKEN;
}
```

- [ ] **Step 4: Update `src/worker.ts` to enforce auth on `/upload/*`**

```typescript
import { handleHealthz } from "./handlers/healthz";
import { checkToken } from "./auth";
import type { Env } from "./types";

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);

    if (request.method === "GET" && url.pathname === "/healthz") {
      return handleHealthz();
    }

    if (url.pathname.startsWith("/upload/")) {
      if (!checkToken(request, env)) {
        return new Response("unauthorized", { status: 401 });
      }
      // Handlers added in later tasks
      return new Response("not implemented", { status: 501 });
    }

    return new Response("not found", { status: 404 });
  },
};
```

- [ ] **Step 5: Run tests to verify all pass**

```powershell
npm test
```

Expected: 3 passed (3 auth + 1 healthz already passing).

- [ ] **Step 6: Commit**

```powershell
git add tests/auth.test.ts src/auth.ts src/worker.ts
git commit -m "feat: add X-Donor-Token auth on protected endpoints"
```

---

## Task 5: R2 presigned URL minting

**Files:**
- Create: `src/r2_presign.ts`
- Modify: `wrangler.toml` (add R2 binding)

- [ ] **Step 1: Create the R2 bucket via Wrangler**

```powershell
npx wrangler r2 bucket create sc-log-donations
```

Expected: bucket created.

- [ ] **Step 2: Add R2 binding to `wrangler.toml`**

Append to `wrangler.toml`:

```toml
[[r2_buckets]]
binding = "BUCKET"
bucket_name = "sc-log-donations"
```

- [ ] **Step 3: Write `src/r2_presign.ts`**

```typescript
import { AwsClient } from "aws4fetch";
import type { Env } from "./types";

const EXPIRY_SECONDS = 600; // 10 minutes - uploader must PUT within this window

export async function mintPutUrl(env: Env, key: string): Promise<string> {
  const aws = new AwsClient({
    accessKeyId: env.R2_ACCESS_KEY_ID,
    secretAccessKey: env.R2_SECRET_ACCESS_KEY,
    service: "s3",
    region: "auto",
  });

  const endpoint = `https://${env.R2_ACCOUNT_ID}.r2.cloudflarestorage.com/${env.R2_BUCKET_NAME}/${key}`;
  const signed = await aws.sign(
    new Request(endpoint, { method: "PUT" }),
    { aws: { signQuery: true }, headers: { "X-Amz-Expires": String(EXPIRY_SECONDS) } }
  );
  return signed.url;
}
```

- [ ] **Step 4: Verify typecheck**

```powershell
npm run typecheck
```

Expected: no errors.

- [ ] **Step 5: Commit**

```powershell
git add wrangler.toml src/r2_presign.ts
git commit -m "feat: add R2 presigned PUT URL minting via aws4fetch"
```

---

## Task 6: D1 helpers

**Files:**
- Create: `src/db.ts`

- [ ] **Step 1: Write `src/db.ts`**

```typescript
import type { Env, UploadBeginFile } from "./types";

export interface UploadRow {
  upload_id: string;
  created_at: string;
  client_ip: string;
  skill_version: string | null;
  wingman_version: string | null;
  total_bytes: number;
  file_count: number;
  manifest_json: string;
  complete: number;
}

export interface FileHashRow {
  content_hash: string;
  upload_id: string;
  r2_key: string;
  first_seen_at: string;
}

export async function insertUpload(
  env: Env,
  row: Omit<UploadRow, "complete">
): Promise<void> {
  await env.DB.prepare(
    `INSERT INTO uploads
       (upload_id, created_at, client_ip, skill_version, wingman_version,
        total_bytes, file_count, manifest_json, complete)
     VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0)`
  )
    .bind(
      row.upload_id,
      row.created_at,
      row.client_ip,
      row.skill_version,
      row.wingman_version,
      row.total_bytes,
      row.file_count,
      row.manifest_json
    )
    .run();
}

export async function markUploadComplete(
  env: Env,
  uploadId: string
): Promise<boolean> {
  const result = await env.DB.prepare(
    `UPDATE uploads SET complete = 1 WHERE upload_id = ? AND complete = 0`
  )
    .bind(uploadId)
    .run();
  return (result.meta.changes ?? 0) > 0;
}

export async function getUpload(
  env: Env,
  uploadId: string
): Promise<UploadRow | null> {
  return await env.DB.prepare(`SELECT * FROM uploads WHERE upload_id = ?`)
    .bind(uploadId)
    .first<UploadRow>();
}

export async function lookupExistingHashes(
  env: Env,
  hashes: string[]
): Promise<Map<string, FileHashRow>> {
  if (hashes.length === 0) return new Map();
  const placeholders = hashes.map(() => "?").join(",");
  const rows = await env.DB.prepare(
    `SELECT * FROM file_hashes WHERE content_hash IN (${placeholders})`
  )
    .bind(...hashes)
    .all<FileHashRow>();
  const map = new Map<string, FileHashRow>();
  for (const row of rows.results ?? []) {
    map.set(row.content_hash, row);
  }
  return map;
}

export async function insertFileHashes(
  env: Env,
  rows: FileHashRow[]
): Promise<void> {
  if (rows.length === 0) return;
  const stmts = rows.map((r) =>
    env.DB.prepare(
      `INSERT OR IGNORE INTO file_hashes
         (content_hash, upload_id, r2_key, first_seen_at)
       VALUES (?, ?, ?, ?)`
    ).bind(r.content_hash, r.upload_id, r.r2_key, r.first_seen_at)
  );
  await env.DB.batch(stmts);
}

export function buildR2Key(
  uploadId: string,
  install: UploadBeginFile["install"],
  renamed: string,
  createdAt: string
): string {
  const date = createdAt.slice(0, 10); // YYYY-MM-DD
  return `${date}/${uploadId}/${install}/${renamed}`;
}
```

- [ ] **Step 2: Verify typecheck**

```powershell
npm run typecheck
```

Expected: no errors.

- [ ] **Step 3: Commit**

```powershell
git add src/db.ts
git commit -m "feat: add D1 helpers for uploads and file_hashes"
```

---

## Task 7: /upload/begin happy path (TDD)

**Files:**
- Create: `tests/upload_begin.test.ts`
- Create: `src/handlers/upload_begin.ts`
- Modify: `src/worker.ts`

- [ ] **Step 1: Update `tests/helpers.ts` to include a valid-token helper and a sample request body**

Add to `tests/helpers.ts`:

```typescript
export const VALID_TOKEN = "local-dev-token-do-not-ship";

export function sampleBeginBody(overrides: Partial<{
  client_version: string;
  files: Array<{
    original_name: string;
    renamed: string;
    install: "Live" | "PTU" | "HOTFIX";
    game_version: string;
    size_bytes: number;
    sha256: string;
  }>;
}> = {}) {
  return {
    client_version: "sc_log_reader v4.7.2",
    wingman_version: "1.2.3",
    files: [
      {
        original_name: "Game_2026_05_14_14_30_22.log",
        renamed: "Mallachi_Game_2026_05_14_14_30_22.log",
        install: "Live" as const,
        game_version: "4.7.2-LIVE-12345",
        size_bytes: 5_242_880,
        sha256: "a".repeat(64),
      },
    ],
    ...overrides,
  };
}

export function authHeaders(): Record<string, string> {
  return {
    "Content-Type": "application/json",
    "X-Donor-Token": VALID_TOKEN,
  };
}
```

- [ ] **Step 2: Write the failing test `tests/upload_begin.test.ts`**

```typescript
import { describe, expect, it } from "vitest";
import { authHeaders, fetchWorker, sampleBeginBody } from "./helpers";

describe("POST /upload/begin", () => {
  it("returns upload_id and signed URL for a new file", async () => {
    const body = sampleBeginBody();
    const res = await fetchWorker("/upload/begin", {
      method: "POST",
      headers: authHeaders(),
      body: JSON.stringify(body),
    });
    expect(res.status).toBe(200);
    const json = await res.json() as {
      upload_id: string;
      files: Array<{ sha256: string; put_url?: string; key: string }>;
    };
    expect(json.upload_id).toMatch(/^[0-9a-f-]{36}$/);
    expect(json.files).toHaveLength(1);
    expect(json.files[0].sha256).toBe(body.files[0].sha256);
    expect(json.files[0].put_url).toMatch(/^https:\/\//);
    expect(json.files[0].key).toContain(body.files[0].renamed);
  });

  it("returns 400 for invalid JSON body", async () => {
    const res = await fetchWorker("/upload/begin", {
      method: "POST",
      headers: authHeaders(),
      body: "not json",
    });
    expect(res.status).toBe(400);
  });

  it("returns 400 when files array is empty", async () => {
    const body = sampleBeginBody({ files: [] });
    const res = await fetchWorker("/upload/begin", {
      method: "POST",
      headers: authHeaders(),
      body: JSON.stringify(body),
    });
    expect(res.status).toBe(400);
  });
});
```

- [ ] **Step 3: Run tests to verify they fail**

```powershell
npm test
```

Expected: 3 new failures (`/upload/begin` returns 501).

- [ ] **Step 4: Write `src/handlers/upload_begin.ts`**

```typescript
import { buildR2Key, insertUpload, lookupExistingHashes } from "../db";
import { mintPutUrl } from "../r2_presign";
import type {
  Env,
  UploadBeginRequest,
  UploadBeginResponse,
  UploadBeginFileResult,
} from "../types";

const SHA256_RE = /^[0-9a-f]{64}$/;

function isValid(body: unknown): body is UploadBeginRequest {
  if (typeof body !== "object" || body === null) return false;
  const b = body as Partial<UploadBeginRequest>;
  if (typeof b.client_version !== "string") return false;
  if (typeof b.wingman_version !== "string") return false;
  if (!Array.isArray(b.files) || b.files.length === 0) return false;
  for (const f of b.files) {
    if (typeof f.original_name !== "string") return false;
    if (typeof f.renamed !== "string") return false;
    if (!["Live", "PTU", "HOTFIX"].includes(f.install)) return false;
    if (typeof f.game_version !== "string") return false;
    if (typeof f.size_bytes !== "number" || f.size_bytes < 0) return false;
    if (typeof f.sha256 !== "string" || !SHA256_RE.test(f.sha256)) return false;
  }
  return true;
}

export async function handleUploadBegin(
  request: Request,
  env: Env
): Promise<Response> {
  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return json({ error: "invalid json" }, 400);
  }
  if (!isValid(body)) {
    return json({ error: "invalid request body" }, 400);
  }

  const uploadId = crypto.randomUUID();
  const createdAt = new Date().toISOString();
  const clientIp = request.headers.get("CF-Connecting-IP") ?? "unknown";
  const totalBytes = body.files.reduce((s, f) => s + f.size_bytes, 0);

  const existing = await lookupExistingHashes(
    env,
    body.files.map((f) => f.sha256)
  );

  const fileResults: UploadBeginFileResult[] = [];
  for (const f of body.files) {
    const known = existing.get(f.sha256);
    if (known) {
      fileResults.push({
        sha256: f.sha256,
        already_uploaded: true,
        key: known.r2_key,
      });
      continue;
    }
    const key = buildR2Key(uploadId, f.install, f.renamed, createdAt);
    const put_url = await mintPutUrl(env, key);
    fileResults.push({ sha256: f.sha256, put_url, key });
  }

  await insertUpload(env, {
    upload_id: uploadId,
    created_at: createdAt,
    client_ip: clientIp,
    skill_version: body.client_version,
    wingman_version: body.wingman_version,
    total_bytes: totalBytes,
    file_count: body.files.length,
    manifest_json: JSON.stringify(body),
  });

  const resp: UploadBeginResponse = { upload_id: uploadId, files: fileResults };
  return json(resp, 200);
}

function json(payload: unknown, status: number): Response {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}
```

- [ ] **Step 5: Wire the handler in `src/worker.ts`**

```typescript
import { handleHealthz } from "./handlers/healthz";
import { handleUploadBegin } from "./handlers/upload_begin";
import { checkToken } from "./auth";
import type { Env } from "./types";

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);

    if (request.method === "GET" && url.pathname === "/healthz") {
      return handleHealthz();
    }

    if (url.pathname.startsWith("/upload/")) {
      if (!checkToken(request, env)) {
        return new Response("unauthorized", { status: 401 });
      }
      if (request.method === "POST" && url.pathname === "/upload/begin") {
        return handleUploadBegin(request, env);
      }
      return new Response("not implemented", { status: 501 });
    }

    return new Response("not found", { status: 404 });
  },
};
```

- [ ] **Step 6: Run tests to verify they pass**

```powershell
npm test
```

Expected: all tests pass (healthz + auth + 3 begin tests).

- [ ] **Step 7: Commit**

```powershell
git add tests/helpers.ts tests/upload_begin.test.ts src/handlers/upload_begin.ts src/worker.ts
git commit -m "feat: add /upload/begin endpoint with validation and presign"
```

---

## Task 8: /upload/begin deduplication (TDD)

**Files:**
- Modify: `tests/upload_begin.test.ts`

This task adds a test for the dedup branch. The handler already covers it (lookup in Task 7), so this is mostly verification.

- [ ] **Step 1: Add the dedup test to `tests/upload_begin.test.ts`**

Append inside the `describe` block:

```typescript
import { env } from "cloudflare:test";

it("marks already_uploaded for hashes already in file_hashes", async () => {
  // Seed file_hashes with a known content_hash
  const seededHash = "b".repeat(64);
  const seededUploadId = "00000000-0000-0000-0000-000000000001";
  const seededKey = "2026-05-01/old-upload/Live/Mallachi_old.log";

  await env.DB.prepare(
    `INSERT INTO uploads
       (upload_id, created_at, client_ip, total_bytes, file_count,
        manifest_json, complete)
     VALUES (?, ?, ?, ?, ?, ?, 1)`
  )
    .bind(seededUploadId, "2026-05-01T00:00:00Z", "127.0.0.1", 0, 0, "{}")
    .run();

  await env.DB.prepare(
    `INSERT INTO file_hashes (content_hash, upload_id, r2_key, first_seen_at)
     VALUES (?, ?, ?, ?)`
  )
    .bind(seededHash, seededUploadId, seededKey, "2026-05-01T00:00:00Z")
    .run();

  // Submit a begin request that includes the seeded hash
  const body = sampleBeginBody({
    files: [
      {
        original_name: "old.log",
        renamed: "Mallachi_old.log",
        install: "Live" as const,
        game_version: "4.7.2-LIVE",
        size_bytes: 1000,
        sha256: seededHash,
      },
    ],
  });
  const res = await fetchWorker("/upload/begin", {
    method: "POST",
    headers: authHeaders(),
    body: JSON.stringify(body),
  });

  expect(res.status).toBe(200);
  const json = await res.json() as {
    upload_id: string;
    files: Array<{
      sha256: string;
      already_uploaded?: boolean;
      put_url?: string;
      key: string;
    }>;
  };
  expect(json.files[0].already_uploaded).toBe(true);
  expect(json.files[0].put_url).toBeUndefined();
  expect(json.files[0].key).toBe(seededKey);
});
```

Also add the import for `env`:

```typescript
import { env } from "cloudflare:test";
```

- [ ] **Step 2: Run tests to verify the new one passes**

```powershell
npm test
```

Expected: all tests pass (dedup branch is already implemented).

- [ ] **Step 3: Commit**

```powershell
git add tests/upload_begin.test.ts
git commit -m "test: add coverage for /upload/begin dedup branch"
```

---

## Task 9: /upload/complete happy path (TDD)

**Files:**
- Create: `tests/upload_complete.test.ts`
- Create: `src/handlers/upload_complete.ts`
- Modify: `src/worker.ts`

- [ ] **Step 1: Write the failing test `tests/upload_complete.test.ts`**

```typescript
import { env } from "cloudflare:test";
import { describe, expect, it } from "vitest";
import { authHeaders, fetchWorker, sampleBeginBody } from "./helpers";

describe("POST /upload/complete", () => {
  it("marks the upload complete and inserts file_hashes", async () => {
    // Run /upload/begin first to create the row
    const beginBody = sampleBeginBody({
      files: [
        {
          original_name: "x.log",
          renamed: "Mallachi_x.log",
          install: "Live" as const,
          game_version: "4.7.2-LIVE",
          size_bytes: 100,
          sha256: "c".repeat(64),
        },
      ],
    });
    const beginRes = await fetchWorker("/upload/begin", {
      method: "POST",
      headers: authHeaders(),
      body: JSON.stringify(beginBody),
    });
    const beginJson = await beginRes.json() as { upload_id: string };
    const uploadId = beginJson.upload_id;

    // Now /upload/complete
    const res = await fetchWorker("/upload/complete", {
      method: "POST",
      headers: authHeaders(),
      body: JSON.stringify({ upload_id: uploadId }),
    });
    expect(res.status).toBe(200);
    const json = await res.json() as { upload_id: string; complete: true };
    expect(json.upload_id).toBe(uploadId);
    expect(json.complete).toBe(true);

    // Verify D1 state
    const row = await env.DB.prepare(
      `SELECT complete FROM uploads WHERE upload_id = ?`
    ).bind(uploadId).first<{ complete: number }>();
    expect(row?.complete).toBe(1);

    const hashRow = await env.DB.prepare(
      `SELECT content_hash FROM file_hashes WHERE upload_id = ?`
    ).bind(uploadId).first<{ content_hash: string }>();
    expect(hashRow?.content_hash).toBe("c".repeat(64));
  });

  it("returns 404 for unknown upload_id", async () => {
    const res = await fetchWorker("/upload/complete", {
      method: "POST",
      headers: authHeaders(),
      body: JSON.stringify({
        upload_id: "00000000-0000-0000-0000-000000000099",
      }),
    });
    expect(res.status).toBe(404);
  });

  it("returns 400 when upload_id is missing", async () => {
    const res = await fetchWorker("/upload/complete", {
      method: "POST",
      headers: authHeaders(),
      body: JSON.stringify({}),
    });
    expect(res.status).toBe(400);
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

```powershell
npm test
```

Expected: 3 new failures (handler not implemented).

- [ ] **Step 3: Write `src/handlers/upload_complete.ts`**

```typescript
import {
  buildR2Key,
  getUpload,
  insertFileHashes,
  markUploadComplete,
} from "../db";
import type {
  Env,
  UploadBeginRequest,
  UploadCompleteRequest,
  UploadCompleteResponse,
} from "../types";

export async function handleUploadComplete(
  request: Request,
  env: Env
): Promise<Response> {
  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return json({ error: "invalid json" }, 400);
  }
  if (
    typeof body !== "object" ||
    body === null ||
    typeof (body as UploadCompleteRequest).upload_id !== "string"
  ) {
    return json({ error: "missing upload_id" }, 400);
  }
  const uploadId = (body as UploadCompleteRequest).upload_id;

  const row = await getUpload(env, uploadId);
  if (!row) {
    return json({ error: "upload not found" }, 404);
  }

  // Parse the stored manifest to figure out which keys/hashes to record
  const manifest = JSON.parse(row.manifest_json) as UploadBeginRequest;
  const createdAt = row.created_at;
  const newHashes = manifest.files.map((f) => ({
    content_hash: f.sha256,
    upload_id: uploadId,
    r2_key: buildR2Key(uploadId, f.install, f.renamed, createdAt),
    first_seen_at: new Date().toISOString(),
  }));

  await insertFileHashes(env, newHashes);
  await markUploadComplete(env, uploadId);

  // Write manifest.json into R2 for archival browsing
  const manifestKey = `${createdAt.slice(0, 10)}/${uploadId}/manifest.json`;
  await env.BUCKET.put(manifestKey, row.manifest_json, {
    httpMetadata: { contentType: "application/json" },
  });

  const resp: UploadCompleteResponse = { upload_id: uploadId, complete: true };
  return json(resp, 200);
}

function json(payload: unknown, status: number): Response {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}
```

- [ ] **Step 4: Wire the handler in `src/worker.ts`**

```typescript
import { handleHealthz } from "./handlers/healthz";
import { handleUploadBegin } from "./handlers/upload_begin";
import { handleUploadComplete } from "./handlers/upload_complete";
import { checkToken } from "./auth";
import type { Env } from "./types";

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);

    if (request.method === "GET" && url.pathname === "/healthz") {
      return handleHealthz();
    }

    if (url.pathname.startsWith("/upload/")) {
      if (!checkToken(request, env)) {
        return new Response("unauthorized", { status: 401 });
      }
      if (request.method === "POST" && url.pathname === "/upload/begin") {
        return handleUploadBegin(request, env);
      }
      if (request.method === "POST" && url.pathname === "/upload/complete") {
        return handleUploadComplete(request, env);
      }
      return new Response("not allowed", { status: 405 });
    }

    return new Response("not found", { status: 404 });
  },
};
```

- [ ] **Step 5: Run tests to verify they pass**

```powershell
npm test
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

```powershell
git add tests/upload_complete.test.ts src/handlers/upload_complete.ts src/worker.ts
git commit -m "feat: add /upload/complete with R2 manifest write and D1 finalize"
```

---

## Task 10: R2 manifest.json verification test

**Files:**
- Modify: `tests/upload_complete.test.ts`

- [ ] **Step 1: Add a test that verifies `manifest.json` lands in R2**

Append inside the `describe` block of `tests/upload_complete.test.ts`:

```typescript
it("writes manifest.json into the R2 bucket", async () => {
  const beginBody = sampleBeginBody({
    files: [
      {
        original_name: "y.log",
        renamed: "Mallachi_y.log",
        install: "PTU" as const,
        game_version: "4.7.2-PTU",
        size_bytes: 200,
        sha256: "d".repeat(64),
      },
    ],
  });
  const beginRes = await fetchWorker("/upload/begin", {
    method: "POST",
    headers: authHeaders(),
    body: JSON.stringify(beginBody),
  });
  const { upload_id } = await beginRes.json() as { upload_id: string };

  await fetchWorker("/upload/complete", {
    method: "POST",
    headers: authHeaders(),
    body: JSON.stringify({ upload_id }),
  });

  const row = await env.DB.prepare(
    `SELECT created_at FROM uploads WHERE upload_id = ?`
  ).bind(upload_id).first<{ created_at: string }>();
  const date = row!.created_at.slice(0, 10);

  const obj = await env.BUCKET.get(`${date}/${upload_id}/manifest.json`);
  expect(obj).not.toBeNull();
  const text = await obj!.text();
  const parsed = JSON.parse(text);
  expect(parsed.files[0].sha256).toBe("d".repeat(64));
});
```

- [ ] **Step 2: Run tests**

```powershell
npm test
```

Expected: all tests pass (R2 binding works in vitest-pool-workers locally).

- [ ] **Step 3: Commit**

```powershell
git add tests/upload_complete.test.ts
git commit -m "test: verify manifest.json is written to R2 on complete"
```

---

## Task 11: Reconciler script

**Files:**
- Create: `scripts/reconcile.ts`

The reconciler runs locally (via Wrangler `--remote` access), not as a Worker route. It sweeps incomplete uploads older than 1 hour.

- [ ] **Step 1: Write `scripts/reconcile.ts`**

```typescript
/**
 * Sweep incomplete uploads in D1.
 *
 * For each `uploads` row with complete=0 older than 1 hour:
 *   - HEAD each expected R2 key (derived from manifest_json)
 *   - if all present: mark complete=1 and backfill file_hashes
 *   - else: log to stderr for manual review
 *
 * Run with: npx wrangler d1 execute --remote sc-log-donate-meta ... -- or via
 * `tsx scripts/reconcile.ts` after configuring R2/D1 credentials via env vars.
 *
 * For v1 this is intentionally a manual script - not a scheduled Worker.
 */
import type { UploadBeginRequest } from "../src/types";

interface IncompleteRow {
  upload_id: string;
  created_at: string;
  manifest_json: string;
}

function envOrDie(name: string): string {
  const v = process.env[name];
  if (!v) {
    console.error(`Missing env var: ${name}`);
    process.exit(1);
  }
  return v;
}

async function callD1(sql: string, params: unknown[] = []): Promise<unknown> {
  const accountId = envOrDie("CF_ACCOUNT_ID");
  const dbId = envOrDie("CF_D1_DATABASE_ID");
  const apiToken = envOrDie("CF_API_TOKEN");
  const url = `https://api.cloudflare.com/client/v4/accounts/${accountId}/d1/database/${dbId}/query`;
  const res = await fetch(url, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${apiToken}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ sql, params }),
  });
  if (!res.ok) {
    throw new Error(`D1 query failed: ${res.status} ${await res.text()}`);
  }
  return (await res.json() as { result: { results: unknown[] }[] }).result[0].results;
}

async function r2Head(key: string): Promise<boolean> {
  const accountId = envOrDie("CF_ACCOUNT_ID");
  const bucket = envOrDie("R2_BUCKET_NAME");
  const apiToken = envOrDie("CF_API_TOKEN");
  const url = `https://api.cloudflare.com/client/v4/accounts/${accountId}/r2/buckets/${bucket}/objects/${encodeURIComponent(key)}`;
  const res = await fetch(url, {
    method: "HEAD",
    headers: { Authorization: `Bearer ${apiToken}` },
  });
  return res.ok;
}

async function main(): Promise<void> {
  const ONE_HOUR_AGO = new Date(Date.now() - 60 * 60 * 1000).toISOString();
  const rows = (await callD1(
    `SELECT upload_id, created_at, manifest_json
     FROM uploads WHERE complete = 0 AND created_at < ?`,
    [ONE_HOUR_AGO]
  )) as IncompleteRow[];

  console.log(`Found ${rows.length} incomplete upload(s) older than 1 hour.`);

  for (const row of rows) {
    const manifest = JSON.parse(row.manifest_json) as UploadBeginRequest;
    const date = row.created_at.slice(0, 10);
    let allPresent = true;
    for (const f of manifest.files) {
      const key = `${date}/${row.upload_id}/${f.install}/${f.renamed}`;
      if (!(await r2Head(key))) {
        console.error(
          `  upload ${row.upload_id} missing key: ${key}`
        );
        allPresent = false;
      }
    }
    if (allPresent) {
      await callD1(
        `UPDATE uploads SET complete = 1 WHERE upload_id = ?`,
        [row.upload_id]
      );
      // Backfill file_hashes
      const stmts = manifest.files.map((f) => {
        const key = `${date}/${row.upload_id}/${f.install}/${f.renamed}`;
        return callD1(
          `INSERT OR IGNORE INTO file_hashes
             (content_hash, upload_id, r2_key, first_seen_at)
           VALUES (?, ?, ?, ?)`,
          [f.sha256, row.upload_id, key, new Date().toISOString()]
        );
      });
      await Promise.all(stmts);
      console.log(`  upload ${row.upload_id} reconciled to complete`);
    } else {
      console.log(`  upload ${row.upload_id} left incomplete (manual review needed)`);
    }
  }
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
```

- [ ] **Step 2: Add a script entry to `package.json`**

Add to the `scripts` block:

```json
"reconcile": "tsx scripts/reconcile.ts"
```

And add `tsx` to devDependencies:

```powershell
npm install --save-dev tsx
```

- [ ] **Step 3: Verify typecheck**

```powershell
npm run typecheck
```

Expected: no errors.

- [ ] **Step 4: Commit**

```powershell
git add scripts/reconcile.ts package.json package-lock.json
git commit -m "feat: add reconcile script for incomplete uploads"
```

---

## Task 12: README runbooks

**Files:**
- Create: `README.md`

- [ ] **Step 1: Write `README.md`**

````markdown
# sc-log-donate

Cloudflare Worker that receives Star Citizen log donations from the
[`sc_log_reader`](../wingman-ai/skills/sc_log_reader) skill.

## Architecture

Three HTTP endpoints (TypeScript Worker):

- `GET /healthz` - uptime probe
- `POST /upload/begin` - receive manifest, return presigned R2 PUT URLs
- `POST /upload/complete` - mark upload complete in D1, write manifest.json to R2

Files are uploaded by the skill **directly to R2** using presigned URLs minted
by the Worker (via `aws4fetch`). Files do not pass through the Worker.

D1 stores upload metadata and a content-hash index for deduplication.

## Setup (one-time)

```powershell
npm install
```

Create R2 bucket and D1 database (only once per environment):

```powershell
npx wrangler r2 bucket create sc-log-donations
npx wrangler d1 create sc-log-donate-meta
```

Copy the `database_id` from the output into `wrangler.toml`.

Apply migrations:

```powershell
npm run migrate:remote
```

Configure secrets:

```powershell
npx wrangler secret put DONOR_TOKEN
npx wrangler secret put R2_ACCESS_KEY_ID
npx wrangler secret put R2_SECRET_ACCESS_KEY
npx wrangler secret put R2_ACCOUNT_ID
npx wrangler secret put R2_BUCKET_NAME
```

R2 access key/secret are generated in the Cloudflare dashboard:
**R2 → Manage R2 API Tokens → Create API token** with PUT permission on the
bucket.

## Local dev

```powershell
npm run dev
```

Reads secrets from `.dev.vars` (gitignored). Uses local D1 and a local R2
simulator via Wrangler.

## Tests

```powershell
npm test
```

Uses `@cloudflare/vitest-pool-workers` - runs tests in a real workerd runtime
with in-memory D1 and R2.

## Deploy

```powershell
npm run deploy
```

The CI workflow at `.github/workflows/deploy.yml` also deploys on push to main.

## Runbook: rotate DONOR_TOKEN

The donor token is a shared secret baked into the `sc_log_reader` skill at
build time. To rotate:

1. Generate a new token:
   ```powershell
   $token = -join ((1..32) | ForEach-Object { '{0:x}' -f (Get-Random -Maximum 16) })
   ```
2. Set it on the Worker:
   ```powershell
   echo $token | npx wrangler secret put DONOR_TOKEN
   ```
3. Update the build env var consumed by `sc_log_reader/update_release.py` and
   ship a new skill release.

Old skill versions will get 401 until they update.

## Runbook: reconcile incomplete uploads

If skill-side `/upload/complete` calls fail after R2 PUTs succeed,
`uploads.complete` stays 0. The reconciler sweeps these:

```powershell
$env:CF_ACCOUNT_ID="..."
$env:CF_D1_DATABASE_ID="..."
$env:CF_API_TOKEN="..."
$env:R2_BUCKET_NAME="sc-log-donations"
npm run reconcile
```

It finds rows with `complete=0` and `created_at < now-1h`, HEAD-checks all
expected R2 keys, and marks complete when all files are present. Run it
manually whenever you notice stuck uploads in the dashboard. Could be
scheduled as a Worker cron later if it becomes a regular need.

## Runbook: browse donated logs

R2 dashboard:
**CF dashboard → R2 → sc-log-donations → Browse**

Or via `rclone`:

```powershell
rclone copy r2:sc-log-donations/2026-05-14/ .\donations\2026-05-14\
```

(Requires `rclone.conf` with R2 S3 credentials.)
````

- [ ] **Step 2: Commit**

```powershell
git add README.md
git commit -m "docs: add README with setup, deploy, and operational runbooks"
```

---

## Task 13: TESTER.md manual smoke procedures

**Files:**
- Create: `TESTER.md`

- [ ] **Step 1: Write `TESTER.md`**

````markdown
# Manual smoke tests for sc-log-donate

These complement the vitest suite and validate behavior the unit tests can't
cover (real Cloudflare edge, real R2, real skill integration).

## Prerequisites

- `wrangler dev` running locally OR a staging deploy at a `*.workers.dev` URL
- A test SC log file (any file ≥ 1 KB will do for connectivity)
- `curl` available in PowerShell

## Smoke 1: healthz

```powershell
curl https://sc-log-donate.<your-subdomain>.workers.dev/healthz
```

Expected: `ok`, status 200.

## Smoke 2: end-to-end with curl

Replace `<TOKEN>` with the current `DONOR_TOKEN`.

```powershell
$body = @{
  client_version = "manual-test"
  wingman_version = "manual"
  files = @(@{
    original_name = "test.log"
    renamed = "Tester_test.log"
    install = "Live"
    game_version = "test"
    size_bytes = 100
    sha256 = ("e" * 64)
  })
} | ConvertTo-Json -Depth 5

$beginRes = curl -X POST "https://sc-log-donate.<your-subdomain>.workers.dev/upload/begin" `
  -H "X-Donor-Token: <TOKEN>" `
  -H "Content-Type: application/json" `
  -d $body
$beginJson = $beginRes | ConvertFrom-Json
$uploadId = $beginJson.upload_id
$putUrl = $beginJson.files[0].put_url

# PUT a small file to the presigned URL
"hello world" | Out-File -Encoding utf8 .\test.log
curl -X PUT $putUrl --upload-file .\test.log

# Complete the upload
curl -X POST "https://sc-log-donate.<your-subdomain>.workers.dev/upload/complete" `
  -H "X-Donor-Token: <TOKEN>" `
  -H "Content-Type: application/json" `
  -d "{`"upload_id`": `"$uploadId`"}"
```

Expected:
- `/upload/begin` returns 200 with `upload_id` and `put_url`
- PUT to `put_url` returns 200
- `/upload/complete` returns 200
- File visible in R2 dashboard under today's date / `$uploadId` / `Live/Tester_test.log`
- `manifest.json` visible alongside it
- D1 `uploads` row has `complete=1`

## Smoke 3: token rotation drill

1. Note current `DONOR_TOKEN` value
2. Run `Smoke 2` to confirm working
3. Rotate token (see README runbook)
4. Run `Smoke 2` again with OLD token: expect 401
5. Run `Smoke 2` with NEW token: expect 200
6. Restore original token if this was a drill

## Smoke 4: rate limit

(Only meaningful against a deployed Worker, not local dev.)

```powershell
for ($i = 1; $i -le 15; $i++) {
  $res = curl -s -o $null -w "%{http_code}`n" `
    -X POST "https://sc-log-donate.<your-subdomain>.workers.dev/upload/begin" `
    -H "X-Donor-Token: <TOKEN>" `
    -H "Content-Type: application/json" `
    -d "{}"
  Write-Host "Request ${i}: $res"
}
```

Expected: somewhere around request 11–12, status codes change from `400`
(invalid body, but auth passed) to `429` (rate limited).

## Smoke 5: skill integration

After deploying the `sc_log_reader` Donate Logs feature (see the skill plan):

1. Install the patched skill in Wingman AI
2. Open settings → "Help improve this skill" → "Donate logs"
3. Verify preview dialog shows real log counts
4. Click Upload
5. Verify R2 dashboard receives the files within ~30 seconds
6. Re-press the button: dialog says "all eligible logs already donated"

## Smoke 6: failure injection

1. Edit Windows hosts file to point the worker URL at 127.0.0.1
2. Press Donate logs in the skill
3. Verify dialog shows: "Couldn't reach donation server. Check internet."
4. Verify no rows added to D1 and no files added to R2
5. Restore hosts file
6. Re-press: succeeds normally
````

- [ ] **Step 2: Commit**

```powershell
git add TESTER.md
git commit -m "docs: add TESTER.md with manual smoke test procedures"
```

---

## Task 14: Cloudflare rate-limit rule

The rate limit is configured in the Cloudflare dashboard (Free plan) or via
the `[[unsafe.bindings]]` config (paid plan). For the free plan, document it
as a dashboard step in the README.

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Append rate-limit setup to `README.md`**

Add a new section after "Setup (one-time)":

```markdown
### Rate limit configuration

Cloudflare's free rate-limit rule is configured in the dashboard, not in
`wrangler.toml`:

1. CF dashboard → **Security → WAF → Rate limiting rules**
2. Create rule:
   - Name: `sc-log-donate begin throttle`
   - If incoming requests match: `URI Path equals /upload/begin`
   - Rate: `10 requests per 1 minute`
   - Action: `Block` for `1 minute`
   - Counting: `By IP`
3. Save and enable.

The Worker enforces no rate limiting itself - this is purely edge-level
protection. Adjust limit in the dashboard if abuse patterns emerge.
```

- [ ] **Step 2: Commit**

```powershell
git add README.md
git commit -m "docs: document Cloudflare rate-limit rule setup"
```

---

## Task 15: GitHub Actions deploy workflow

**Files:**
- Create: `.github/workflows/deploy.yml`

- [ ] **Step 1: Write `.github/workflows/deploy.yml`**

```yaml
name: Deploy to Cloudflare Workers

on:
  push:
    branches: [main]
  workflow_dispatch:

jobs:
  test-and-deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Setup Node
        uses: actions/setup-node@v4
        with:
          node-version: "20"
          cache: "npm"

      - name: Install dependencies
        run: npm ci

      - name: Typecheck
        run: npm run typecheck

      - name: Test
        run: npm test

      - name: Deploy
        uses: cloudflare/wrangler-action@v3
        with:
          apiToken: ${{ secrets.CLOUDFLARE_API_TOKEN }}
          accountId: ${{ secrets.CLOUDFLARE_ACCOUNT_ID }}
          command: deploy
```

- [ ] **Step 2: Commit**

```powershell
git add .github/workflows/deploy.yml
git commit -m "ci: add deploy workflow for Cloudflare Workers"
```

---

## Task 16: First remote deploy and verification

This task is operational, not code. Run it once after Task 15 is complete.

- [ ] **Step 1: Set repo secrets in GitHub**

In the GitHub repo settings → Secrets and variables → Actions → New repository secret:

- `CLOUDFLARE_API_TOKEN` (token with Worker, R2, D1 edit scopes)
- `CLOUDFLARE_ACCOUNT_ID`

- [ ] **Step 2: First-time secrets on Wrangler**

Locally (one time):

```powershell
npx wrangler secret put DONOR_TOKEN
# enter a strong random value, save it for the skill build later

npx wrangler secret put R2_ACCESS_KEY_ID
npx wrangler secret put R2_SECRET_ACCESS_KEY
npx wrangler secret put R2_ACCOUNT_ID
npx wrangler secret put R2_BUCKET_NAME    # "sc-log-donations"
```

- [ ] **Step 3: Apply migrations to the remote DB**

```powershell
npm run migrate:remote
```

Expected: migration 0001_initial.sql applied.

- [ ] **Step 4: Manual deploy to verify config**

```powershell
npm run deploy
```

Expected: Worker deploys; final output includes the `*.workers.dev` URL.

- [ ] **Step 5: Configure the rate-limit rule in the CF dashboard**

(Follow README "Rate limit configuration" steps.)

- [ ] **Step 6: Run Smoke 1 and Smoke 2 from `TESTER.md`** against the deployed URL.

- [ ] **Step 7: Push to main to verify CI deploy**

```powershell
git push origin main
```

Expected: GitHub Actions runs typecheck → tests → deploy. All green.

---

## Self-review checklist

### Spec coverage

| Spec section | Implemented in task |
|---|---|
| §4 - Worker + R2 component / endpoints | Tasks 3, 4, 7, 9 |
| §4 - Worker auth | Task 4 |
| §4 - Rate limiting | Tasks 14, 16 |
| §4 - R2 layout (date/upload_id/install/file) | Task 6 (`buildR2Key`) |
| §4 - D1 schema | Task 1 |
| §5 - Worker-side dedup (`file_hashes` lookup + insert) | Tasks 7, 8, 9 |
| §6 - Data flow happy path | Tasks 7, 9 |
| §7 - `/upload/complete` durability + reconciler | Task 11 |
| §8 - Privacy: no public download endpoint | Confirmed by absence of public route |
| §9 - Testing strategy | Tasks 3, 4, 7, 8, 9, 10 plus TESTER.md (Task 13) |
| §10 - Deliverables: Worker source, wrangler.toml, migrations, CI, README, TESTER | Tasks 0–16 |

No gaps.

### Placeholder scan

No "TBD", "TODO", or vague-step patterns found.

### Type consistency

- `Env` interface defined in `src/types.ts` (Task 2) and consistently used across `worker.ts`, `auth.ts`, `db.ts`, `r2_presign.ts`, both handlers, and tests
- `UploadBeginFile.install` typed as `"Live" | "PTU" | "HOTFIX"` everywhere
- `sha256` validated as 64-char lowercase hex in handler and produced as such in test fixtures
- `buildR2Key` signature consistent between `db.ts` and call sites in both handlers

No mismatches.
