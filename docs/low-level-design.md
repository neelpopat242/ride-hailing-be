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

Six tables: `users`, `drivers`, `rides`, `ride_candidates`, `trips`, `payments`. All use UUID primary keys with FK constraints for referential integrity. Schema is defined in `app/models/`.

---

## 3. Database Indexes

No indexes are added in the current implementation beyond primary keys and unique constraints. At the current scale, sequential scans are fast enough. As query volume grows, the following indexes would be the first candidates:

| Priority | Table | Index | Query it would speed up |
|----------|-------|-------|------------------------|
| 1 | `drivers` | `status` | `find_available_candidates` — filters on `status = 'available'` every ride creation |
| 2 | `rides` | `rider_id` | active ride guard — checked on every new ride request |
| 3 | `ride_candidates` | `(ride_id, status)` composite | `get_current_offer`, `get_next_pending` — queried on every dispatch, accept, decline |
| 4 | `users`, `drivers` | `email` (UNIQUE already creates implicit index in PostgreSQL) | auth lookup on onboard |

These are documented for future. When query latency becomes measurable, they can be added with zero code change — just `CREATE INDEX` migrations.

---

## 4. Caching

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

## 5. Concurrency & Transactions

Every request runs inside a single `BEGIN / COMMIT / ROLLBACK` via `get_session()` context manager. Multi-table writes (accept ride, end trip) are atomic — no partial state can persist.

The dispatch design prevents concurrent accept conflicts by construction: only one driver holds the active offer at a time. The FSM rejects any transition that doesn't match the current state.

**Future improvements:**
- `SELECT FOR UPDATE` on the ride row during accept — adds an explicit DB-level lock as a safety net
- Optimistic locking via a `version` column — better for high contention at scale

---

## 6. Design Patterns

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

