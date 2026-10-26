# Load test results

Date: 26 Oct 2026. Tools: `scripts/loadtest.py`, `scripts/loadtest_seed.py`, `scripts/loadtest_mock.py`, and `autocannon` for raw throughput. **Everything ran against a local copy of the API and a local PostgreSQL database. Nothing was sent to the live site, and the script refuses any address that is not this computer.**

## What was measured, and how

- The API ran as it does in production: one process, `uvicorn`, the real database pool (5 connections plus 5 spare) and the real limits for the abuse run. For the capacity runs the sign-in, sign-up and scan limits were raised so they would not hide the speed of the code.
- The server was pinned to one CPU core; the load generator used the other. PostgreSQL ran on the same computer, so the numbers have no network delay to the database. The real database (Neon) adds delay to every query, so real signed-in requests will be slower than shown here.
- The free plan on Render is **0.1 CPU and 512 MB of memory** ([Render's compute plans](https://render.com/docs/compute-plans.md)). To see what that means, the server was also limited to a tenth of a core (a Linux CPU quota) and the key tests were repeated.
- The first load generator (Python) used up its own core before the server was busy (the server used 26% of its core), so its throughput numbers were thrown away. `autocannon` was used instead and the server then ran at 92 to 97% of its core, so those numbers show the server's real limit.
- Test data: 24 throw-away users with one verified local site and one finished scan each, scanning a tiny local web page. No internet site was scanned.

## Result 1: speed of ordinary requests (one full core)

| Request              | Connections         | Per second                | p50 ms            | p97.5 ms            | Errors |
| -------------------- | ------------------- | ------------------------- | ----------------- | ------------------- | ------ |
| Health check         | 10 / 50 / 100 / 200 | 1318 / 1306 / 1196 / 1098 | 7 / 34 / 80 / 172 | 11 / 53 / 101 / 281 | 0      |
| Signed in: who am I  | 10 / 50             | 206 / 238                 | 47 / 191          | 69 / 300            | 0      |
| Signed in: overview  | 10 / 50             | 136 / 125                 | 69 / 383          | 110 / 545           | 0      |
| Signed in: scan list | 10 / 50             | 138 / 141                 | 70 / 338          | 97 / 443            | 0      |
| Signed in: site list | 10 / 50             | 195 / 200                 | 49 / 242          | 71 / 318            | 0      |

Latency rises in a straight line with the number of waiting people (a queue), and no request failed up to 200 connections.

## Result 2: at the size of the free plan (0.1 CPU)

| Request                              | Connections | Per second     | p50 ms       |
| ------------------------------------ | ----------- | -------------- | ------------ |
| Health check                         | 1 / 10 / 50 | 74 / 107 / 106 | 1 / 99 / 495 |
| Signed in: who am I                  | 1 / 10      | 14 / 18        | 94 / 500     |
| Signed in: overview                  | 1 / 10      | 8 / 10         | 102 / 981    |
| Sign in with a password (one person) | 1           | about 0.5      | 2100 to 2200 |
| One scan, start to finish            | 1           | n/a            | 1900 to 2100 |
| **First PDF report of a scan**       | 1           | n/a            | **18 000**   |

A PDF report is built once per scan and then kept, so only the first request pays. The button already shows "Preparing PDF…" while it waits.

## Result 3: slow jobs (one full core)

| Job                   | At once    | Time                                                                |
| --------------------- | ---------- | ------------------------------------------------------------------- |
| First PDF build       | 1 / 4      | 1.9 s / 1.9 to 3.0 s each (built one at a time, as designed)        |
| Scan, start to finish | 1 / 5 / 13 | 0.4 s / 0.8 s / 2.1 s (p50; at most 3 run at a time, the rest wait) |
| Password sign-in      | 1 / 4 / 16 | 0.21 s / 0.8 s / 3.3 s (p50)                                        |

While 8 people signed in at once, a visitor loading a page still saw 34 ms (p50) and 73 ms (p95): password checks do not freeze the rest of the site.

## Result 4: abuse, with the real limits on

| Attack                                         | What happened                                                                                                         |
| ---------------------------------------------- | --------------------------------------------------------------------------------------------------------------------- |
| 40 wrong passwords for one account             | 5 answered 401, the next 35 were refused with 429                                                                     |
| 30 sign-ups from one address                   | 10 created, 20 refused with 429                                                                                       |
| 15 scan requests from one account for one site | 3 accepted, 12 refused with 429                                                                                       |
| 500 connections at once on a signed-in page    | 818 requests answered, no error and no 5xx; slow (p50 5 s, longest 13 s) but the site was healthy straight afterwards |

After each attack the readiness check passed. No request in any test returned a server error.

## Memory

| Moment                                | Server memory                             |
| ------------------------------------- | ----------------------------------------- |
| Idle after start                      | about 100 MB                              |
| After thousands of signed-in requests | about 111 MB                              |
| After the first PDF reports and scans | about 233 MB (the PDF library loads once) |
| After 19 more PDF builds              | 233 to 246 MB, flat (no leak seen)        |

The free plan allows 512 MB, so there is about 250 MB of room at the measured peak.

## What this means

1. **Controlled pilot: fine.** At the free plan's size a signed-in request costs about 40 to 100 ms, so the site serves roughly 8 to 18 of them a second. A dashboard visit is a few requests, so a few visitors a second is the ceiling, which is far above a handful of pilot users.
2. **Public launch: not yet.** A paid instance with more CPU is the first step; at one full core the same code serves about 15 times more. Rate limits and the running-scan list still live in one process, so they must be shared before a second instance is added (unchanged from the earlier audits).
3. **Two things users will feel on the free plan:** sign-in takes about two seconds, and the first PDF of a scan takes up to about 18 seconds. Neither is an error; both are cost of CPU. Cheaper options if it matters later: pre-build the PDF when a scan finishes, or lower the password hashing cost (a security trade-off, not recommended).
4. **The limits work as designed under pressure**, and an overloaded server queues rather than fails.

## Limits of this test

Synthetic traffic on one computer, no network delay to the database, a local scan target, one process. It shows relative cost and that nothing breaks; it does not predict the exact numbers on Render and Neon. It does not test several instances, a database that is paused or slow, or real internet latency. Re-run it after any change that touches the request path:

```
cd backend
SECURESCOPE_DATABASE_URL=<local test database> python -m app.database.migrate
python ../scripts/loadtest_mock.py &
SECURESCOPE_DATABASE_URL=<local test database> python ../scripts/loadtest_seed.py --users 24 --out /tmp/lt-users.json
# start the API on port 8100 (relaxed limits for capacity and heavy; defaults for abuse), then:
python ../scripts/loadtest.py --scenario capacity --users-file /tmp/lt-users.json --pid <server pid>
python ../scripts/loadtest.py --scenario heavy --users-file /tmp/lt-users.json
python ../scripts/loadtest.py --scenario abuse --users-file /tmp/lt-users.json
```

The relaxed limits are the environment variables `SECURESCOPE_LOGIN_ATTEMPTS_PER_IP_PER_15MIN`, `SECURESCOPE_LOGIN_ATTEMPTS_PER_EMAIL_PER_15MIN`, `SECURESCOPE_REGISTRATIONS_PER_IP_PER_HOUR`, `SECURESCOPE_SCANS_PER_CLIENT_PER_HOUR` and `SECURESCOPE_SCANS_PER_TARGET_PER_HOUR`, plus `SECURESCOPE_ALLOW_PRIVATE_TARGETS=true` (local only; the app refuses it with secure cookies).

## Statuses

- Local development: READY.
- Controlled external pilot (free plan): READY. Measured, no failures, limits hold.
- Public commercial launch: NOT READY (paid instance and shared limits first).
