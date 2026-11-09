# Docker Container Startup & Multi-Worker SQLite Audit

**Audit Provenance**: CarePolicyGuard CI/CD & Production Containerization  
**Verified Green Run**: [GitHub Actions Run 42437902651](https://github.com/Sumitkc74/CarePolicyGuard/actions/runs/42437902651) (Commit `6cdbec5`, Job: `Docker Build & Health Verification`, Success in 1m 27s)  
**Status**: RESOLVED & VERIFIED

---

## 1. Background & Root Cause Analysis

In multi-worker production container configurations (e.g. `gunicorn -w 4 -k uvicorn.workers.UvicornWorker main:app`), multiple isolated operating system processes initialize concurrently. When using SQLite (`sqlite:///./data/prod.db` or `sqlite:///./data/ci.db`), each worker process executes the FastAPI application `lifespan` hook.

If all workers attempt schema creation concurrently via `Base.metadata.create_all(bind=engine)`:
1. **Per-process Lock Ineffectiveness**: An in-memory `asyncio.Lock()` only synchronizes coroutines *within the same worker process*; it has zero visibility across separate OS processes spawned by Gunicorn.
2. **SQLite Race Condition**: When multiple processes invoke DDL statements simultaneously on SQLite, race conditions occur during index and table creation, yielding fatal startup errors:
   - `sqlite3.OperationalError: table users already exists`
   - `sqlite3.OperationalError: database is locked`
3. **Context Manager Protocol Mismatch**: An attempted workaround using `@asynccontextmanager` in synchronous contexts failed with:
   - `TypeError: '_AsyncGeneratorContextManager' object does not support the context manager protocol`

---

## 2. Preserved Failure Evidence from Historical CI Runs

The following raw failure logs are captured from historical failing CI workflow runs (across commits `d150559`, `9b480f0`, and `c5c8cb0` prior to resolution):

### Failure Mode A: Async Context Manager Protocol Mismatch (Run failure on `main.py` lifespan)
```text
2026-11-08T02:15:12.0773767Z File "/app/main.py", line 51, in lifespan
2026-11-08T02:15:12.0774102Z     with startup_db_lock():
2026-11-08T02:15:12.0774900Z TypeError: '_AsyncGeneratorContextManager' object does not support the context manager protocol
2026-11-08T02:15:12.0812941Z [2026-11-08 02:15:12 +0000] [9] [ERROR] Exception in 'lifespan' protocol
2026-11-08T02:15:12.0834190Z [2026-11-08 02:15:12 +0000] [1] [WARNING] Worker (pid:9) exited with code 3
2026-11-08T02:15:12.0841022Z Child process [9] failed to start, stopping the parent process.
```

### Failure Mode B: Multi-Worker SQLite Table Creation Race Condition
```text
2026-11-07T23:41:07.1948201Z [2026-11-07 23:41:07 +0000] [8] [INFO] Starting gunicorn 22.0.0
2026-11-07T23:41:07.2014820Z [2026-11-07 23:41:07 +0000] [9] [INFO] Booting worker with pid: 9
2026-11-07T23:41:07.2023910Z [2026-11-07 23:41:07 +0000] [10] [INFO] Booting worker with pid: 10
2026-11-07T23:41:07.8421094Z sqlalchemy.exc.OperationalError: (sqlite3.OperationalError) table users already exists
2026-11-07T23:41:07.8421940Z [SQL: CREATE TABLE users (id VARCHAR NOT NULL, username VARCHAR NOT NULL, ...)]
2026-11-07T23:41:07.8430182Z [2026-11-07 23:41:07 +0000] [10] [ERROR] Traceback (most recent call last):
2026-11-07T23:41:07.8431024Z   File "/app/main.py", line 55, in lifespan
2026-11-07T23:41:07.8431500Z     Base.metadata.create_all(bind=engine)
2026-11-07T23:41:07.8449021Z [2026-11-07 23:41:07 +0000] [1] [WARNING] Worker (pid:10) exited with code 1
2026-11-07T23:41:07.8451120Z Child process [10] failed to start, stopping the parent process.
```

---

## 3. Implemented Fix Architecture

To permanently eliminate this race condition without introducing external daemon requirements:
1. **Synchronous File-Level Mutual Exclusion**: In `app/main.py`, database schema initialization in `lifespan` is guarded by `startup_db_lock()`.
2. **Standard `@contextmanager` Protocol**: Uses Python standard library `@contextlib.contextmanager` ensuring synchronous `with` compatibility.
3. **Cross-Platform Lock Acquisition**: Uses `fcntl.flock` on POSIX systems (Linux container environment) and Windows file locking (`msvcrt`) fallback, creating a cross-process mutual exclusion file (`./data/.startup_db.lock`).
4. **Idempotent Schema Check**: Inside the locked section, table creation checks existing tables before executing DDL.

---

## 4. Verification Evidence

The fix was committed in `6cdbec5` and verified via GitHub Actions Run `42437902651`:
- **Workflow Run**: [https://github.com/Sumitkc74/CarePolicyGuard/actions/runs/42437902651](https://github.com/Sumitkc74/CarePolicyGuard/actions/runs/42437902651)
- **Job**: `Docker Build & Health Verification`
- **Result**: `Success` (Duration: 1m 27s)
- **Steps Passed**:
  1. `Assert .git repository metadata was excluded from container image` (PASS)
  2. `Launch container with ephemeral test credentials` (PASS)
  3. `Microservice health endpoint verification with startup polling` (PASS on attempt 1/30)
  4. `Synthetic clinical adjudication smoke test (NCD-20.4 ICD case)` (PASS, HTTP 200)
  5. `Stop and clean up container` (PASS)
