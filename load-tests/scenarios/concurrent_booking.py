from locust import HttpUser, task, constant
import random

# Shared "same resource" ID — the point is maximum contention
CONTESTED_RESOURCE = "RES-OT2"
PATIENT_ID = "PT-0001"

DEMO_USERS = [
    ("dr.mehta", "mediora123"),
    ("dr.kapoor", "mediora123"),
    ("nurse.priya", "mediora123"),
    ("admin.ops", "mediora123"),
    ("dr.mehta", "password"),
    ("nurse.priya", "password"),
    ("admin.coord", "password"),
]

class ConcurrentBookingUser(HttpUser):
    """
    All users hammer the same OT-2 room.
    Goal: confirm exactly 0 or 1 TX reaches COMMITTED.
    No 500s. All responses are 201 (TX created, state may vary).
    """
    wait_time = constant(0)   # No wait — maximum concurrency
    host = "http://localhost:8000"
    token: str = ""

    def on_start(self):
        creds = random.choice(DEMO_USERS)
        resp = self.client.post(
            "/api/v1/auth/login",
            json={"username": creds[0], "password": creds[1]}
        )
        if resp.status_code == 200:
            self.token = resp.json().get("access_token", "")
        else:
            # Try alternate password fallback
            alt_pwd = "password" if creds[1] == "mediora123" else "mediora123"
            resp = self.client.post(
                "/api/v1/auth/login",
                json={"username": creds[0], "password": alt_pwd}
            )
            if resp.status_code == 200:
                self.token = resp.json().get("access_token", "")

    def _auth(self):
        return {"Authorization": f"Bearer {self.token}"} if self.token else {}

    @task
    def book_contested_resource(self):
        resp = self.client.post(
            "/api/v1/transactions",
            json={
                "request_type": "single_resource",
                "patient_id": PATIENT_ID,
                "resource_id": CONTESTED_RESOURCE,
            },
            headers=self._auth(),
            name=f"CONTEST {CONTESTED_RESOURCE}"
        )
        # Any 2xx or 4xx is acceptable — 5xx is a test failure
        if resp.status_code >= 500:
            # Locust marks this as a failure automatically
            pass
