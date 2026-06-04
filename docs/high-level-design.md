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

## 8. Future Improvements

### 8.1 Async Dispatch with Background Workers
Move dispatch logic to a Celery/RQ background task. Ride creation returns immediately while the worker handles driver matching and the 10s offer countdown. `DispatchService` is already isolated as a separate class — wrapping it as a task requires no logic change. This also eliminates the lazy timeout approach by letting the worker actively schedule re-dispatch on expiry.

### 8.2 Region-Based Driver Filtering
Add a `region` column on `Driver` and filter by region before ranking by distance. This reduces the candidate search from a global scan to a region-scoped query. Region can be derived from geohash prefix or predefined zones (airport, city-center, etc.).

### 8.3 WebSocket for Live Updates
Replace client polling with persistent WebSocket connections. When ride state changes or driver location updates, push the event immediately via Redis pub/sub. This reduces unnecessary requests and gives riders real-time tracking instead of 5s intervals.

### 8.4 Dynamic Pricing via Strategy Pattern
Introduce a `FareStrategy` interface with pluggable implementations (standard, surge, flat-rate). The active strategy is selected based on real-time supply-demand ratio per region. The current fare calculation module is already isolated, so swapping in a strategy requires minimal change.

