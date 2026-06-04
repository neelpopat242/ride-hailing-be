# High Level Design — GoComet Ride Hailing

---

## 1. Functional Requirements

**What does the system do?**

- A rider can request a ride by providing pickup and drop coordinates.
- The system finds the nearest available driver and dispatches an offer with a 10-second acceptance window.
- If the driver declines or times out, the offer moves to the next nearest candidate (up to 5 total).
- The driver accepts, starts the trip, completes it, and fare is calculated based on distance.
- Rider pays after trip completion.
- Rider can track the driver's live location while the ride is active.

**Actors:**
- **Rider** — requests rides, polls status, pays
- **Driver** — receives offers, accepts/declines, sends location updates, starts/ends trip
- **System** — dispatches, manages state, calculates fare

---

## 2. Non-Functional Requirements

| Requirement | Target |
|---|---|
| Availability | High — ride creation and dispatch must not have a single point of failure |
| Consistency | Strong — a ride must never be double-booked |
| Latency | Driver-rider match < 1s p95; location poll served from cache |
| Scalability | Stateless API — horizontal scaling behind a load balancer |
| Fault tolerance | DB transaction rollback on failure; cache TTL as safety net |
| Observability | New Relic APM for request latency, DB query timing, slow query traces. Alerts on p95 breach, elevated 5xx rate, DB saturation |
| Security | JWT on all protected routes; `extra="forbid"` on all Pydantic schemas; rate limiting on ride creation and payment endpoints (pending) |

---

## 3. Capacity Estimation (back of envelope)

- 10,000 active riders, 5,000 active drivers
- Peak: ~500 ride requests/min → ~8 req/s
- Location updates: drivers update every 5s → 5,000 / 5 = 1,000 writes/s to Redis
- Ride status polls: riders poll every 5s → 10,000 / 5 = 2,000 reads/s (mostly cache hits)
- Storage: ride + candidate rows — negligible at this scale

---

## 4. System Architecture

```
┌──────────────┐     ┌──────────────┐
│  Rider App   │     │  Driver App  │
└──────┬───────┘     └──────┬───────┘
       │                    │
       └──────────┬──────────┘
                  ▼
          ┌───────────────┐
          │  Flask API    │  (stateless, horizontally scalable)
          └───────┬───────┘
           ┌──────┴──────┐
           ▼             ▼
      PostgreSQL        Redis
  (source of truth)   (cache)
```

**Why PostgreSQL?**
All ride, driver, payment and trip data is transactional. Strong consistency and FK constraints are required. PostgreSQL gives ACID guarantees and row-level locking (`SELECT FOR UPDATE`) for concurrent accept handling.

**Why Redis?**
Two uses: ride status cache (5s TTL, reduces Postgres read load) and driver location cache (10s TTL, overwritten on every location update). Both are high-frequency, low-stakes reads that tolerate slight staleness.

---

## 5. Core Component Design

| Component | Responsibility |
|---|---|
| ViewSet + `@route` | HTTP routing, JWT auth, request validation — DRF-style for Flask |
| Service layer | Business logic, orchestrates repos and state machine |
| Repository | All DB access isolated per table |
| DispatchService | Offer dispatch and timeout logic, decoupled from ride and driver services |
| FSM | `RideStateMachine`, `DriverStateMachine` — illegal transitions raise 409 before any DB write |
| JWTAuth | Single token — `user_id` + `role` claims, validated per request |
| Cache utils | `get_ride`, `set_ride`, `invalidate_ride`, `get_location`, `set_location` |

---

## 6. Key Design Decisions

**Single JWT for riders and drivers**
One token system with `role` claim. Route-level auth checks the role. No separate auth service needed at this scale.

**Lazy timeout advancement**
Offer expiry is not checked by a background job — it is advanced on the next client interaction (GET ride, accept, decline). Simple and sufficient for current scale. Replaced by async worker in future.

**Polling over streaming**
Rider polls `GET /rides/{id}/location` every 5 seconds instead of an SSE stream. Simpler infrastructure, easier to scale, and the 5s update interval matches driver's location push frequency.

**Email-only onboarding**
No password, no OTP. Email is the unique identifier — if it exists, return a JWT; if not, create the account and return a JWT. Removes auth complexity while keeping the system usable.

---

## 7. Ride Lifecycle

```
REQUESTED → ASSIGNED → ACCEPTED → IN_PROGRESS → COMPLETED
                │                                    ↑
                ├── (decline/timeout) → re-ASSIGNED ─┘
                └── (all 5 fail) → FAILED
```

- **REQUESTED → ASSIGNED**: System dispatches offer to nearest driver (10s window)
- **ASSIGNED → ACCEPTED**: Driver accepts, all other candidates marked EXPIRED
- **ACCEPTED → IN_PROGRESS**: Driver starts trip (rider in car)
- **IN_PROGRESS → COMPLETED**: Driver ends trip, fare calculated, driver freed

---

## 8. Problems in Current Approach

### 8.1 Synchronous Dispatch — Single Point of Latency
**Problem:** The entire dispatch flow (find candidates, sort by Haversine, create candidates, assign first) runs inside the ride creation request. If the DB is slow or there are many available drivers, the rider waits.
**Impact:** p95 ride creation latency increases linearly with driver count.

### 8.2 Lazy Timeout — Silent Staleness
**Problem:** Offer expiry is only checked when someone interacts with the ride (GET, accept, decline). If no one polls a ride for 2 minutes, a timed-out offer just sits there — the next driver never gets notified.
**Impact:** Driver sees stale "offer waiting" in their app. The rider sees "assigned" but nothing happens.

### 8.3 Global Driver Scan — O(n) on Every Ride
**Problem:** `find_available_candidates()` fetches all available drivers with location, then sorts in Python by Haversine. No spatial index, no region filter.
**Impact:** At 50,000 drivers this becomes a full table scan + in-memory sort per ride request.

### 8.4 No Real Payment Processing
**Problem:** Payment creates a success record with a fake PSP reference. No real gateway call, no retry, no failure handling.
**Impact:** Fine for assignment scope, but production needs circuit breaker around PSP calls and async retry on failure.

### 8.5 Polling Overhead
**Problem:** Every active rider polls ride status every 5 seconds. At 10,000 riders, that's 2,000 req/s even when nothing has changed.
**Impact:** Wasted compute. Most polls return the same cached response.

### 8.6 No Surge Pricing
**Problem:** Fare is always `base + per_km * distance`. No demand-supply multiplier.
**Impact:** In high-demand periods, there's no incentive for more drivers to come online.

### 8.7 No Rate Limiting
**Problem:** Any authenticated user can hit any endpoint at any rate.
**Impact:** A single bad client can exhaust server resources.

---

## 9. Improvements — Prioritized

### 9.1 Async Dispatch with Celery/RQ (highest priority)
Replace synchronous dispatch with a background task. `create_ride` enqueues a `dispatch_offer` task and returns immediately. The worker handles the 10s countdown and auto-advances to the next candidate on timeout. `DispatchService` is already isolated — wrapping it as a task requires zero logic change.

**Solves:** 8.1 (latency), 8.2 (lazy timeout)

### 9.2 Region-Based Driver Filtering
Add an indexed `region` column on `Driver`. Filter by region first, then rank by Haversine distance. Turns O(n drivers) into O(drivers in region). Region can be a geohash prefix or a city/zone enum.

**Solves:** 8.3 (global scan)

### 9.3 WebSocket / SSE for Live Updates
Replace polling with a persistent connection. When ride state changes or driver location updates, push the event immediately. Use Redis pub/sub as the transport between API servers.

**Solves:** 8.5 (polling overhead)

### 9.4 Observer Pattern — Event-Driven Side Effects
`EventBus.emit("ride.assigned", ride)` in service layer. Observers handle push notifications, WebSocket updates, email receipts independently. Services have zero knowledge of delivery channels.

**Solves:** Decouples business logic from notification/delivery concerns.

### 9.5 Strategy Pattern — Dynamic Pricing
`FareStrategy` interface with pluggable implementations (`StandardFareStrategy`, `SurgeFareStrategy`). Inject based on current demand-supply ratio. Implement when ≥ 2 pricing models are defined.

**Solves:** 8.6 (surge pricing)

### 9.6 Rate Limiting
Redis-backed sliding window rate limiter on ride creation (5/min per rider) and payment endpoints. Can use Flask-Limiter or a custom middleware.

**Solves:** 8.7 (no rate limiting)

### 9.7 Circuit Breaker — PSP Resilience
Wrap PSP HTTP calls in a circuit breaker (`pybreaker`). On consecutive failures, open the circuit and return a fast error instead of cascading timeouts. Implement when real PSP integration is added.

**Solves:** 8.4 (payment resilience)

---

## 10. Implementation Phases

### Phase 1 — Core (complete)
- Postgres models, repositories, session management
- All required APIs with Pydantic validation
- FSM-enforced state transitions (including `start_trip` → IN_PROGRESS)
- Dispatch with 10s timeout and candidate queue
- Redis caching for ride status and driver location
- Email-based onboarding for riders and drivers
- Haversine-based nearest driver selection

### Phase 2 — Reliability and Observability (next)
- Async dispatch queue (Celery/RQ) — remove lazy timeout
- Observer pattern + WebSocket notifications
- New Relic APM instrumentation
- Rate limiting on ride creation and payment endpoints

### Phase 3 — Scale and Hardening
- Region-based driver filtering — remove global scan
- Surge pricing via Strategy pattern
- Circuit breaker around real PSP integration
- Load testing and index tuning

