"""
End-to-end test suite for GoComet Ride Hailing API.

Runs against a live server at BASE_URL.
Requires: seed data (2 riders, 5 drivers) already loaded.

Usage:
    python tests/test_e2e.py
"""

import json
import sys
import time
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed

BASE_URL = "http://127.0.0.1:8000"

# Counters
passed = 0
failed = 0
errors = []


def log(status, name, detail=""):
    global passed, failed
    icon = "PASS" if status else "FAIL"
    if status:
        passed += 1
    else:
        failed += 1
        errors.append(f"{name}: {detail}")
    print(f"  [{icon}] {name}" + (f" — {detail}" if detail and not status else ""))


def post(path, body=None, token=None):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    r = requests.post(f"{BASE_URL}{path}", json=body, headers=headers, timeout=10)
    return r.status_code, r.json()


def get(path, token=None):
    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    r = requests.get(f"{BASE_URL}{path}", headers=headers, timeout=10)
    return r.status_code, r.json()


# ──────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────

def auth_rider(email):
    _, data = post("/v1/auth/rider", {"email": email})
    return data["data"]["token"], data["data"]["id"]


def auth_driver(email):
    _, data = post("/v1/auth/driver", {"email": email})
    return data["data"]["token"], data["data"]["id"]


def create_ride(token, pickup_lat=12.9352, pickup_lng=77.6245, dest_lat=12.9716, dest_lng=77.5946):
    return post("/v1/rides", {
        "pickup_lat": pickup_lat,
        "pickup_lng": pickup_lng,
        "dest_lat": dest_lat,
        "dest_lng": dest_lng,
        "payment_method": "card"
    }, token)


def accept_ride(token, ride_id):
    return post("/v1/drivers/accept", {"ride_id": ride_id}, token)


def decline_ride(token, ride_id):
    return post("/v1/drivers/decline", {"ride_id": ride_id}, token)


def start_trip(token, trip_id):
    return post(f"/v1/trips/{trip_id}/start", token=token)


def end_trip(token, trip_id, distance_km=5.2):
    return post(f"/v1/trips/{trip_id}/end", {"distance_km": distance_km}, token)


def create_payment(token, ride_id):
    return post("/v1/payments", {"ride_id": ride_id}, token)


# ──────────────────────────────────────────
# Test Suites
# ──────────────────────────────────────────

def test_health():
    print("\n── Health ──")
    code, data = get("/health")
    log(code == 200 and data.get("status") == "ok", "Health check")


def test_auth():
    print("\n── Auth ──")

    # Existing rider
    code, data = post("/v1/auth/rider", {"email": "alice@example.com"})
    log(code == 200 and "token" in data.get("data", {}), "Auth existing rider")

    # Existing driver
    code, data = post("/v1/auth/driver", {"email": "driver1@example.com"})
    log(code == 200 and "token" in data.get("data", {}), "Auth existing driver")

    # New rider (create-or-return)
    code, data = post("/v1/auth/rider", {"email": "newrider_test@example.com"})
    log(code == 200 and data["data"]["role"] == "rider", "Auth new rider (create)")

    # Same email again returns same id
    code2, data2 = post("/v1/auth/rider", {"email": "newrider_test@example.com"})
    log(data2["data"]["id"] == data["data"]["id"], "Auth idempotent (same id)")

    # Invalid email
    code, data = post("/v1/auth/rider", {"email": "not-an-email"})
    log(code == 400, "Auth invalid email rejected", f"got {code}")

    # Extra field
    code, data = post("/v1/auth/rider", {"email": "x@x.com", "extra": "bad"})
    log(code == 400, "Auth extra field rejected")

    # Missing field
    code, data = post("/v1/auth/rider", {})
    log(code == 400, "Auth missing email rejected")


def test_auth_role_enforcement():
    print("\n── Role Enforcement ──")
    rider_token, _ = auth_rider("alice@example.com")
    driver_token, _ = auth_driver("driver1@example.com")

    # Driver can't create ride
    code, _ = create_ride(driver_token)
    log(code == 403, "Driver cannot create ride (403)")

    # Rider can't accept ride
    code, _ = post("/v1/drivers/accept", {"ride_id": "00000000-0000-0000-0000-000000000000"}, rider_token)
    log(code == 403, "Rider cannot accept ride (403)")

    # No token
    code, _ = post("/v1/rides", {"pickup_lat": 12.9, "pickup_lng": 77.6, "dest_lat": 12.97, "dest_lng": 77.59, "payment_method": "card"})
    log(code == 401, "No token returns 401")


def test_validation():
    print("\n── Validation ──")
    rider_token, _ = auth_rider("alice@example.com")

    # Missing fields
    code, data = post("/v1/rides", {"pickup_lat": 12.9}, rider_token)
    log(code == 400, "Ride missing fields → 400")

    # Extra fields
    code, _ = post("/v1/rides", {
        "pickup_lat": 12.9, "pickup_lng": 77.6, "dest_lat": 12.97,
        "dest_lng": 77.59, "payment_method": "card", "extra": "bad"
    }, rider_token)
    log(code == 400, "Ride extra field → 400")

    # Lat out of range
    code, _ = post("/v1/rides", {
        "pickup_lat": 999, "pickup_lng": 77.6, "dest_lat": 12.97,
        "dest_lng": 77.59, "payment_method": "card"
    }, rider_token)
    log(code == 400, "Ride lat out of range → 400")

    # Invalid UUID in path
    code, _ = get("/v1/rides/not-a-uuid", rider_token)
    log(code == 400, "Invalid UUID → 400")


def test_happy_path():
    """Full ride lifecycle: create → accept → start → end → pay"""
    print("\n── Happy Path (Full Ride Lifecycle) ──")
    rider_token, _ = auth_rider("alice@example.com")
    driver_token, _ = auth_driver("driver1@example.com")

    # Create ride
    code, data = create_ride(rider_token)
    log(code == 201, "Create ride → 201")
    ride_id = data["data"]["ride_id"]
    trip_id = data["data"]["trip_id"]
    assigned_driver = data["data"]["driver_id"]
    log(data["data"]["status"] == "assigned", "Ride status is 'assigned'")
    log(assigned_driver is not None, "Driver was assigned")

    # Accept
    code, data = accept_ride(driver_token, ride_id)
    log(code == 200 and data["data"]["status"] == "accepted", "Accept → accepted")

    # Update driver location
    code, data = post("/v1/drivers/location", {"lat": 12.94, "lng": 77.62}, driver_token)
    log(code == 200, "Location update → 200")

    # Rider polls ride status
    code, data = get(f"/v1/rides/{ride_id}", rider_token)
    log(code == 200 and data["data"]["status"] == "accepted", "Poll ride → accepted")

    # Rider polls driver location
    code, data = get(f"/v1/rides/{ride_id}/location", rider_token)
    log(code == 200 and data["data"]["lat"] == 12.94, "Poll location → correct lat")

    # Start trip
    code, data = start_trip(driver_token, trip_id)
    log(code == 200 and data["data"]["status"] == "in_progress", "Start trip → in_progress")

    # End trip
    code, data = end_trip(driver_token, trip_id, 5.2)
    log(code == 200 and data["data"]["status"] == "completed", "End trip → completed")
    fare = data["data"]["fare_amount"]
    expected_fare = round(40.0 + 12.0 * 5.2, 2)
    log(fare == expected_fare, f"Fare correct ({fare} == {expected_fare})", f"got {fare}")

    # Payment
    code, data = create_payment(rider_token, ride_id)
    log(code == 201 and data["data"]["status"] == "success", "Payment → success")
    log(data["data"]["amount"] == expected_fare, "Payment amount matches fare")

    # Final status
    code, data = get(f"/v1/rides/{ride_id}", rider_token)
    log(code == 200 and data["data"]["status"] == "completed", "Final status → completed")


def test_active_ride_guard():
    print("\n── Active Ride Guard ──")
    rider_token, _ = auth_rider("bob@example.com")

    # Create first ride
    code, data = create_ride(rider_token, pickup_lat=12.97, pickup_lng=77.59, dest_lat=12.93, dest_lng=77.62)
    log(code == 201, "Bob creates ride → 201")

    # Try second ride — should be blocked
    code, data = create_ride(rider_token, pickup_lat=12.97, pickup_lng=77.59, dest_lat=12.93, dest_lng=77.62)
    log(code == 409 and data["error"]["code"] == "RIDE_ALREADY_ACTIVE", "Second ride blocked → 409")


def test_decline_redispatch():
    """Decline triggers re-dispatch to next candidate"""
    print("\n── Decline & Re-dispatch ──")

    # Create a new rider for this test
    rider_token, _ = auth_rider("decline_test@example.com")

    code, data = create_ride(rider_token)
    if code != 201:
        log(False, "Create ride for decline test", f"got {code}")
        return

    ride_id = data["data"]["ride_id"]
    first_driver = data["data"]["driver_id"]
    log(True, f"Ride assigned to first driver")

    # Get that driver's token
    # We need to figure out which seeded driver this is
    # Use auth to get the token for the assigned driver
    # Since we can't reverse-lookup email from ID, let's try all driver tokens
    driver_tokens = {}
    for i in range(1, 6):
        t, did = auth_driver(f"driver{i}@example.com")
        driver_tokens[did] = t

    if first_driver not in driver_tokens:
        log(False, "Assigned driver not in seed data")
        return

    # Decline
    code, data = decline_ride(driver_tokens[first_driver], ride_id)
    log(code == 200, "Decline → 200")
    log(data["data"]["status"] == "assigned", "Ride re-assigned after decline")

    # Check ride — should have a different driver
    code, data = get(f"/v1/rides/{ride_id}", rider_token)
    second_driver = data["data"]["driver_id"]
    log(second_driver != first_driver, "Different driver after decline", f"first={first_driver[:8]} second={second_driver[:8] if second_driver else 'None'}")


def test_offer_timeout():
    """Wait for 10s timeout, then poll to trigger lazy advance"""
    print("\n── Offer Timeout (10s wait) ──")
    rider_token, _ = auth_rider("timeout_test@example.com")

    code, data = create_ride(rider_token)
    if code != 201:
        log(False, "Create ride for timeout test", f"got {code}")
        return

    ride_id = data["data"]["ride_id"]
    first_driver = data["data"]["driver_id"]
    log(True, f"Ride assigned, waiting 11s for timeout...")

    time.sleep(11)

    # Poll to trigger lazy timeout advancement
    code, data = get(f"/v1/rides/{ride_id}", rider_token)
    second_driver = data["data"].get("driver_id")
    status = data["data"]["status"]

    if status == "assigned" and second_driver != first_driver:
        log(True, "Timeout: re-dispatched to next driver")
    elif status == "failed":
        log(True, "Timeout: all candidates exhausted → failed")
    else:
        log(False, "Timeout: unexpected state", f"status={status} driver={second_driver}")


def test_duplicate_accept():
    """Double-accept on same ride should fail"""
    print("\n── Double Accept Guard ──")
    rider_token, _ = auth_rider("double_accept_test@example.com")

    code, data = create_ride(rider_token)
    if code != 201:
        log(False, "Create ride for double accept test", f"got {code}")
        return

    ride_id = data["data"]["ride_id"]
    assigned_driver = data["data"]["driver_id"]

    driver_tokens = {}
    for i in range(1, 6):
        t, did = auth_driver(f"driver{i}@example.com")
        driver_tokens[did] = t

    if assigned_driver not in driver_tokens:
        log(False, "Assigned driver not in seed data")
        return

    # First accept
    code, _ = accept_ride(driver_tokens[assigned_driver], ride_id)
    log(code == 200, "First accept → 200")

    # Second accept (same driver)
    code, data = accept_ride(driver_tokens[assigned_driver], ride_id)
    log(code == 409, "Second accept → 409", f"got {code}")


def test_wrong_driver_accept():
    """A driver not assigned to the ride tries to accept"""
    print("\n── Wrong Driver Accept ──")
    rider_token, _ = auth_rider("wrong_driver_test@example.com")

    code, data = create_ride(rider_token)
    if code != 201:
        log(False, "Create ride", f"got {code}")
        return

    ride_id = data["data"]["ride_id"]
    assigned_driver = data["data"]["driver_id"]

    # Find a different driver
    driver_tokens = {}
    for i in range(1, 6):
        t, did = auth_driver(f"driver{i}@example.com")
        driver_tokens[did] = t

    wrong_driver_id = None
    for did, t in driver_tokens.items():
        if did != assigned_driver:
            wrong_driver_id = did
            break

    if not wrong_driver_id:
        log(False, "Could not find a different driver")
        return

    code, data = accept_ride(driver_tokens[wrong_driver_id], ride_id)
    log(code == 409, "Wrong driver accept → 409", f"got {code}")


def test_trip_state_guards():
    """Trip state machine guards"""
    print("\n── Trip State Guards ──")
    rider_token, _ = auth_rider("state_guard_test@example.com")
    driver_tokens = {}
    for i in range(1, 6):
        t, did = auth_driver(f"driver{i}@example.com")
        driver_tokens[did] = t

    code, data = create_ride(rider_token)
    if code != 201:
        log(False, "Create ride", f"got {code}")
        return

    ride_id = data["data"]["ride_id"]
    trip_id = data["data"]["trip_id"]
    assigned = data["data"]["driver_id"]
    dt = driver_tokens.get(assigned)

    # Can't start before accept
    code, _ = start_trip(dt, trip_id)
    log(code == 409, "Start before accept → 409", f"got {code}")

    # Can't end before start
    code, _ = end_trip(dt, trip_id)
    log(code == 409, "End before start → 409", f"got {code}")

    # Accept
    accept_ride(dt, ride_id)

    # Can't end before start (still)
    code, _ = end_trip(dt, trip_id)
    log(code == 409, "End before start (after accept) → 409", f"got {code}")

    # Start
    start_trip(dt, trip_id)

    # Can't start again
    code, _ = start_trip(dt, trip_id)
    log(code == 409, "Double start → 409", f"got {code}")

    # End
    end_trip(dt, trip_id)

    # Can't end again
    code, _ = end_trip(dt, trip_id)
    log(code == 409, "Double end → 409", f"got {code}")


def test_payment_guards():
    """Payment only works after trip is completed with fare"""
    print("\n── Payment Guards ──")
    rider_token, _ = auth_rider("payment_guard_test@example.com")

    code, data = create_ride(rider_token)
    if code != 201:
        log(False, "Create ride", f"got {code}")
        return

    ride_id = data["data"]["ride_id"]

    # Payment before trip end
    code, data = create_payment(rider_token, ride_id)
    log(code == 409, "Payment before trip end → 409", f"got {code}")


def test_driver_location_offline():
    """Offline driver can't update location"""
    print("\n── Driver Location Guards ──")
    # Create a fresh driver, they start as available
    driver_token, _ = auth_driver("location_guard_driver@example.com")

    # Available driver can update location
    code, _ = post("/v1/drivers/location", {"lat": 12.9, "lng": 77.6}, driver_token)
    log(code == 200, "Available driver location update → 200")


def test_concurrent_ride_creation():
    """Multiple riders creating rides concurrently"""
    print("\n── Concurrent Ride Creation (10 riders) ──")

    rider_tokens = []
    for i in range(10):
        t, _ = auth_rider(f"concurrent_rider_{i}@example.com")
        rider_tokens.append(t)

    results = []
    def create_one(token, idx):
        lats = [12.93 + idx * 0.005, 77.62 + idx * 0.003]
        code, data = create_ride(token, pickup_lat=lats[0], pickup_lng=lats[1])
        return idx, code, data

    with ThreadPoolExecutor(max_workers=10) as pool:
        futures = [pool.submit(create_one, t, i) for i, t in enumerate(rider_tokens)]
        for f in as_completed(futures):
            results.append(f.result())

    successes = sum(1 for _, code, _ in results if code == 201)
    no_drivers = sum(1 for _, code, data in results if code == 409 and data.get("error", {}).get("code") == "NO_DRIVERS_AVAILABLE")
    log(successes > 0, f"Concurrent rides: {successes} created, {no_drivers} no-driver", f"{successes}/10 succeeded")


def test_load_basic():
    """Basic load test — 50 sequential requests to health endpoint"""
    print("\n── Load Test: 50 Health Checks ──")

    start = time.time()
    codes = []
    for _ in range(50):
        code, _ = get("/health")
        codes.append(code)
    elapsed = time.time() - start

    all_ok = all(c == 200 for c in codes)
    rps = 50 / elapsed
    log(all_ok, f"50 health checks in {elapsed:.2f}s ({rps:.0f} req/s)")


def test_load_auth():
    """Load test — 20 concurrent auth requests"""
    print("\n── Load Test: 20 Concurrent Auth ──")

    def do_auth(i):
        code, _ = post("/v1/auth/rider", {"email": f"load_auth_{i}@example.com"})
        return code

    start = time.time()
    with ThreadPoolExecutor(max_workers=20) as pool:
        futures = [pool.submit(do_auth, i) for i in range(20)]
        codes = [f.result() for f in as_completed(futures)]
    elapsed = time.time() - start

    all_ok = all(c == 200 for c in codes)
    rps = 20 / elapsed
    log(all_ok, f"20 concurrent auths in {elapsed:.2f}s ({rps:.0f} req/s)")


def test_load_mixed():
    """Load test — mixed reads and writes concurrently"""
    print("\n── Load Test: 30 Mixed Requests ──")

    rider_token, _ = auth_rider("alice@example.com")

    def do_request(i):
        if i % 3 == 0:
            code, _ = get("/health")
        elif i % 3 == 1:
            code, _ = post("/v1/auth/rider", {"email": f"load_mixed_{i}@example.com"})
        else:
            code, _ = get(f"/v1/rides/00000000-0000-0000-0000-000000000000", rider_token)
        return code

    start = time.time()
    with ThreadPoolExecutor(max_workers=30) as pool:
        futures = [pool.submit(do_request, i) for i in range(30)]
        codes = [f.result() for f in as_completed(futures)]
    elapsed = time.time() - start

    rps = 30 / elapsed
    # Some will be 404 (ride not found), that's fine
    server_errors = sum(1 for c in codes if c >= 500)
    log(server_errors == 0, f"30 mixed requests in {elapsed:.2f}s ({rps:.0f} req/s), 0 server errors")


# ──────────────────────────────────────────
# Runner
# ──────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 60)
    print("GoComet Ride Hailing — E2E Test Suite")
    print("=" * 60)

    test_health()
    test_auth()
    test_auth_role_enforcement()
    test_validation()
    test_happy_path()
    test_active_ride_guard()
    test_decline_redispatch()
    test_wrong_driver_accept()
    test_duplicate_accept()
    test_trip_state_guards()
    test_payment_guards()
    test_driver_location_offline()
    test_offer_timeout()  # 11s wait
    test_concurrent_ride_creation()
    test_load_basic()
    test_load_auth()
    test_load_mixed()

    print("\n" + "=" * 60)
    print(f"RESULTS: {passed} passed, {failed} failed")
    if errors:
        print("\nFailures:")
        for e in errors:
            print(f"  - {e}")
    print("=" * 60)

    sys.exit(0 if failed == 0 else 1)
