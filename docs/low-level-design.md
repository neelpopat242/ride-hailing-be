# Low Level Design — GoComet Ride Hailing

---

## 1. API Schema

### Auth
| Method | Endpoint | Body | Response |
|---|---|---|---|
| POST | `/v1/auth/rider` | `{email}` | `{token, id, role}` |
| POST | `/v1/auth/driver` | `{email}` | `{token, id, role}` |

Email exists → return JWT. Email new → create account → return JWT. No separate sign-up/login.

### Rides
| Method | Endpoint | Auth | Body | Response |
|---|---|---|---|---|
| POST | `/v1/rides` | rider | `{pickup_lat, pickup_lng, dest_lat, dest_lng, payment_method}` | `{ride_id, trip_id, status, driver_id, offer_expires_at}` |
| GET | `/v1/rides/{id}` | rider, driver | — | `{ride_id, status, driver_id, offer_expires_at, ...}` |
| GET | `/v1/rides/{id}/location` | rider | — | `{driver_id, lat, lng, updated_at}` |

### Drivers
| Method | Endpoint | Auth | Body | Response |
|---|---|---|---|---|
| POST | `/v1/drivers/location` | driver | `{lat, lng}` | `{driver_id, lat, lng, updated_at}` |
| POST | `/v1/drivers/accept` | driver | `{ride_id}` | `{ride_id, driver_id, status}` |
| POST | `/v1/drivers/decline` | driver | `{ride_id}` | `{ride_id, status}` |

### Trips & Payments
| Method | Endpoint | Auth | Body | Response |
|---|---|---|---|---|
| POST | `/v1/trips/{id}/start` | driver | — | `{trip_id, ride_id, status}` |
| POST | `/v1/trips/{id}/end` | driver | `{distance_km}` | `{trip_id, ride_id, fare_amount, currency, status}` |
| POST | `/v1/payments` | rider | `{ride_id}` | `{payment_id, ride_id, amount, status, psp_reference}` |

**Auth header:** `Authorization: Bearer <token>`
**Error format:** `{"error": {"code": "SNAKE_CASE_CODE", "message": "Human readable"}}`

---

## 2. Database Schema

### users
```
id            UUID  PK
email         TEXT  UNIQUE  INDEX
name          TEXT
created_at    TIMESTAMP
```

### drivers
```
id                   UUID  PK
email                TEXT  UNIQUE  INDEX
status               TEXT  INDEX    -- available | assigned | on_trip | offline
lat                  FLOAT  nullable
lng                  FLOAT  nullable
location_updated_at  TIMESTAMP  nullable
created_at           TIMESTAMP
updated_at           TIMESTAMP
```

### rides
```
id                  UUID  PK
rider_id            UUID  FK → users       INDEX
assigned_driver_id  UUID  FK → drivers     INDEX  nullable
pickup_lat/lng      FLOAT
dest_lat/lng        FLOAT
payment_method      TEXT
status              TEXT  INDEX    -- requested | assigned | accepted | in_progress | completed | cancelled | failed
offer_expires_at    TIMESTAMP  nullable
created_at          TIMESTAMP
updated_at          TIMESTAMP
```

### ride_candidates
```
id          UUID  PK
ride_id     UUID  FK → rides
driver_id   UUID  FK → drivers
priority    INT              -- 1 = closest
status      TEXT             -- pending | offered | accepted | declined | expired
created_at  TIMESTAMP
updated_at  TIMESTAMP

INDEX: (ride_id, status)   -- composite, covers get_current_offer + get_next_pending
```

### trips
```
id               UUID  PK
ride_id          UUID  FK → rides  UNIQUE  INDEX
started_at       TIMESTAMP  nullable
ended_at         TIMESTAMP  nullable
distance_km      FLOAT  nullable
fare_amount      FLOAT  nullable
surge_multiplier FLOAT  default 1.0
currency         TEXT   default "INR"
created_at       TIMESTAMP
updated_at       TIMESTAMP
```

### payments
```
id             UUID  PK
ride_id        UUID  FK → rides  INDEX
amount         FLOAT
currency       TEXT   default "INR"
status         TEXT   -- initiated | success | failed
psp_reference  TEXT   nullable
created_at     TIMESTAMP
updated_at     TIMESTAMP
```

---

## 3. State Machines

### Ride FSM
```
requested   → assigned, failed
assigned    → accepted, assigned (re-dispatch), failed
accepted    → in_progress, completed, cancelled
in_progress → completed, cancelled
completed, cancelled, failed  →  (terminal — no further transitions)
```

### Driver FSM
```
available → assigned, offline
assigned  → on_trip, available
on_trip   → available
offline   → available
```

Illegal transitions raise `APIException(409, INVALID_STATE_TRANSITION)` before any DB write.

---

## 4. Dispatch Flow (Low Level)

```
create_ride()
  1. find_available_candidates()  →  SELECT * FROM drivers WHERE status = 'available' AND lat IS NOT NULL
  2. pick_nearest_drivers()       →  Haversine sort, take top 5
  3. ride_repo.create()           →  INSERT INTO rides (status = 'requested')
  4. candidate_repo.bulk_create() →  INSERT INTO ride_candidates (priority 1..5, status = 'pending')
  5. dispatch_next()
       → get_next_pending()       →  SELECT ... WHERE ride_id = ? AND status = 'pending' ORDER BY priority LIMIT 1
       → update candidate         →  status = 'offered'
       → update driver            →  status = 'assigned'
       → update ride              →  status = 'assigned', assigned_driver_id = ?, offer_expires_at = now + 10s
```

---

## 5. Database Indexes

### Current (implemented)
| Table | Index | Query served |
|---|---|---|
| `drivers` | `status` | `find_available_candidates` on every ride creation |
| `drivers` | `email` | auth lookup on onboard |
| `rides` | `status` | polling, timeout checks |
| `rides` | `rider_id` | active ride guard on creation |
| `rides` | `assigned_driver_id` | accept/decline lookups |
| `ride_candidates` | `(ride_id, status)` composite | `get_current_offer`, `get_next_pending` |
| `users` | `email` | auth lookup on onboard |
| `trips` | `ride_id` (UNIQUE) | trip lookup by ride for payment |

### Future (if needed)
| Table | Index | When to add |
|---|---|---|
| `drivers` | `region` | when region-based pre-filtering is introduced |
| `payments` | `ride_id` | if payment lookups become a latency bottleneck |
| `ride_candidates` | `driver_id` | if querying offer history per driver is required |

---

## 6. Caching

### Current Scope
| Cache key | TTL | Written by | Invalidated by |
|---|---|---|---|
| `ride:<ride_id>` | 5s | `GET /rides/{id}` on DB miss | accept, decline, dispatch_next, trip start, trip end |
| `driver:<id>:location` | 10s | every `POST /drivers/location` | overwritten on next update |

**Strategy:** write-on-read for ride status (populate on first miss), write-on-update for location (always overwrite). TTL is the safety net in case an invalidation is missed.

### Future Scope
| What | Why | When to add |
|---|---|---|
| Available driver snapshot | avoid repeated global scan on burst ride creation | when `find_available_candidates` latency is measurable |
| Completed ride response | terminal state never changes — cache permanently | when old ride read traffic is significant |
| Cache stampede prevention | simultaneous cache misses flood Postgres | use Redis `SET NX` lock, let only one request populate the cache |

---

## 7. Concurrency & Transactions

### Problem: Two Drivers Accepting the Same Ride
Without a lock, two drivers can both read `status = assigned`, both pass the FSM check, and both commit — double booking.

### Solution: SELECT FOR UPDATE
```python
ride = session.query(Ride).filter_by(id=ride_id).with_for_update().first()
```
Row-level exclusive lock. Second transaction blocks until first commits. By then, `status = accepted` — FSM rejects the second accept with 409.

`accept_ride` writes to two tables in the same transaction:
- `ride_candidates` — mark accepted candidate, bulk expire others
- `rides` — transition status to accepted

Both are covered by the single row lock.

`decline_ride` does not need this lock — only the currently assigned driver can decline, so there is no competing writer.

### Atomic Writes
Every request runs inside a single `BEGIN / COMMIT / ROLLBACK`. No partial state can persist.

Key multi-table atomic operations:
| Operation | Tables touched |
|---|---|
| Accept ride | `rides` + `ride_candidates` (accepted + bulk expire) + `drivers` (on_trip) |
| Dispatch next | `rides` + `drivers` (status) + `ride_candidates` (offered) |
| Start trip | `rides` (in_progress) + `trips` (started_at) |
| End trip | `trips` (fare) + `rides` (completed) + `drivers` (available) |

### Future: Optimistic Locking
Add `version` integer column to `rides`. Each UPDATE increments it. Concurrent writers conflict on version mismatch and retry. More scalable than `SELECT FOR UPDATE` under very high contention but requires retry logic in the service layer.

---

## 8. Design Patterns

### Current
| Pattern | Implementation |
|---|---|
| Repository | DB access isolated per table — `RideRepository`, `DriverRepository`, `UserRepository`, etc. |
| Service layer | Business logic decoupled from HTTP — `RideService`, `DriverService`, `DispatchService` |
| FSM | Explicit transition maps, raises `APIException(409)` on illegal moves |
| Dependency Injection | Session injected into services via `__init__` — no global state |
| ViewSet + `@route` decorator | DRF-style routing — `register()` collects `@route` methods and wires them onto a Flask blueprint |

### Future
| Pattern | Use case | Trigger to implement |
|---|---|---|
| Observer | Ride event notifications (push, WebSocket, email) | When frontend live updates are required |
| Strategy | Pluggable fare calculation — standard, surge, flat-rate | When ≥ 2 pricing models are defined |
| Circuit Breaker | Protect against PSP / external API outages | When real PSP integration replaces the mock |

---

## 9. Asynchronous Communication

### Current
All operations are synchronous and inline. Offer timeout is checked lazily on the next client call. No background workers.

### Future
| Mechanism | Purpose |
|---|---|
| Celery / RQ worker | `dispatch_next()` as a background task — removes inline dispatch from request path |
| Celery countdown | Auto-fire `dispatch_next()` after 10s — eliminates lazy timeout check entirely |
| Redis pub/sub | Driver location broadcast to rider (if polling replaced with push in a future version) |
| Event bus | Emit `ride.assigned`, `ride.accepted`, `ride.completed` events for observer consumers |

---

## 10. Error Handling

### Current Implementation
| Layer | Mechanism | What it catches |
|---|---|---|
| Pydantic schemas | `extra="forbid"`, field validators | Missing fields, extra fields, type mismatches, lat/lng bounds |
| FSM | `RideStateMachine.transition()`, `DriverStateMachine.transition()` | Illegal state transitions → 409 |
| Service layer | Explicit `APIException` raises | Business rule violations (active ride guard, no drivers, payment not ready) |
| Global handlers | `register_error_handlers()` in Flask app | `APIException` → structured JSON, `ValueError` → 400, `SQLAlchemyError` → 500, catch-all → 500 |

### Error Codes (standardized)
```
AUTH:       UNAUTHORIZED, TOKEN_EXPIRED, INVALID_TOKEN, FORBIDDEN
RIDE:       RIDE_NOT_FOUND, RIDE_ALREADY_ACTIVE, NO_DRIVERS_AVAILABLE
DISPATCH:   INVALID_ASSIGNMENT_STATE, INVALID_STATE_TRANSITION
TRIP:       TRIP_NOT_FOUND, INVALID_TRIP_STATE
PAYMENT:    PAYMENT_NOT_READY
DRIVER:     DRIVER_NOT_FOUND, LOCATION_UPDATE_NOT_ALLOWED, LOCATION_UNAVAILABLE
GENERAL:    VALIDATION_ERROR, INVALID_ID, DATABASE_ERROR, INTERNAL_SERVER_ERROR
```

### What Can Be Improved

**1. Generic `ValueError` catch is too broad**
The global `ValueError` handler assumes all ValueErrors are UUID parse failures. A Pydantic coercion error or a math domain error would also return "INVALID_ID". Fix: catch only in UUID parse points, not globally.

**2. No request logging**
Failed requests produce no server-side log beyond Flask's access log. When a 500 occurs, the traceback is swallowed by the catch-all handler. Fix: log the exception with `app.logger.exception()` before returning the error response.

**3. No structured error codes for DB constraint violations**
A duplicate email on auth returns a generic `DATABASE_ERROR` (500) instead of a user-friendly `EMAIL_ALREADY_EXISTS` (409). Fix: catch `IntegrityError` separately and map known constraint names to user-facing codes.

**4. No retry guidance in error responses**
When `NO_DRIVERS_AVAILABLE` is returned, the client doesn't know if it should retry in 5s or 60s. Fix: include a `retry_after` field in applicable error responses.

**5. `PAYMENT_NOT_READY` is too vague**
The same error is returned when: ride doesn't exist, trip doesn't exist, or fare hasn't been calculated. The client can't distinguish these. Fix: return distinct codes for each case.

**6. No idempotency on payment**
If the client retries a payment after a network timeout, a duplicate payment record is created. Fix: use `ride_id` as a natural idempotency key — check for existing success payment before creating a new one.

**7. Silent Redis failures**
If Redis is down, `get_ride()` / `set_ride()` throw an unhandled `ConnectionError` which becomes a 500. Fix: wrap cache calls in try/except — on failure, skip cache and hit DB directly. Cache should degrade gracefully, never fail hard.
