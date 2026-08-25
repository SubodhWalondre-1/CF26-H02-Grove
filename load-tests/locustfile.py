from locust import HttpUser, task, between, events
import random
import json

class MedioraUser(HttpUser):
    """
    Simulates a mixed clinical workload:
    - Single resource bookings (most common)
    - Care bundle bookings (less frequent, higher cost)
    - Status checks and read-only queries (highest frequency)
    """
    wait_time = between(0.5, 2.0)
    host = "http://localhost:8000"

    # Populated on login
    token: str = ""
    patient_id: str = "PT-0001"
    resource_ids: list = []

    def on_start(self):
        """Login and fetch resource list before running tasks."""
        # Cycle through demo users to distribute roles
        credentials = [
            ("dr.mehta", "mediora123"),
            ("dr.kapoor", "mediora123"),
            ("nurse.priya", "mediora123"),
            ("admin.ops", "mediora123"),
            ("admin.coord", "password"),
            ("dr.mehta", "password"),
            ("nurse.priya", "password"),
        ]
        username, password = random.choice(credentials)

        resp = self.client.post(
            "/api/v1/auth/login",
            json={"username": username, "password": password}
        )
        if resp.status_code == 200:
            self.token = resp.json().get("access_token", "")
        else:
            # Fallback to alternate default password
            resp = self.client.post(
                "/api/v1/auth/login",
                json={"username": username, "password": "password" if password == "mediora123" else "mediora123"}
            )
            if resp.status_code == 200:
                self.token = resp.json().get("access_token", "")
            else:
                self.token = ""

        # Pre-fetch resource IDs
        resources_resp = self.client.get(
            "/api/v1/resources?page_size=50",
            headers=self._auth()
        )
        if resources_resp.status_code == 200:
            body = resources_resp.json()
            items = body if isinstance(body, list) else body.get("items", [])
            self.resource_ids = [r["resource_id"] for r in items if r.get("status") == "available"]
            if not self.resource_ids:
                self.resource_ids = [r["resource_id"] for r in items]

    def _auth(self):
        return {"Authorization": f"Bearer {self.token}"} if self.token else {}

    @task(5)
    def list_transactions(self):
        """Read-heavy — 5x weight."""
        self.client.get(
            "/api/v1/transactions?page_size=25",
            headers=self._auth(),
            name="/api/v1/transactions [LIST]"
        )

    @task(3)
    def list_resources(self):
        """Resource grid check."""
        self.client.get(
            "/api/v1/resources",
            headers=self._auth(),
            name="/api/v1/resources [LIST]"
        )

    @task(2)
    def list_conflicts(self):
        """Conflict monitor check."""
        self.client.get(
            "/api/v1/conflicts?status=open",
            headers=self._auth(),
            name="/api/v1/conflicts [LIST]"
        )

    @task(4)
    def book_single_resource(self):
        """Core TX creation — single resource."""
        if not self.resource_ids:
            return
        resource_id = random.choice(self.resource_ids)
        resp = self.client.post(
            "/api/v1/transactions",
            json={
                "request_type": "single_resource",
                "patient_id": self.patient_id,
                "resource_id": resource_id,
            },
            headers=self._auth(),
            name="/api/v1/transactions [SINGLE]"
        )
        if resp.status_code == 201:
            tx_id = resp.json().get("tx_id")
            if tx_id:
                # Immediately check status
                self.client.get(
                    f"/api/v1/transactions/{tx_id}",
                    headers=self._auth(),
                    name="/api/v1/transactions/{tx_id} [GET]"
                )

    @task(1)
    def book_care_bundle(self):
        """Less frequent, atomically complex."""
        if len(self.resource_ids) < 2:
            return
        bundle_ids = random.sample(self.resource_ids, min(3, len(self.resource_ids)))
        self.client.post(
            "/api/v1/transactions",
            json={
                "request_type": "care_bundle",
                "patient_id": self.patient_id,
                "resource_ids": bundle_ids,
            },
            headers=self._auth(),
            name="/api/v1/transactions [BUNDLE]"
        )

    @task(2)
    def audit_logs(self):
        """Audit page load."""
        self.client.get(
            "/api/v1/audit/events?page_size=50",
            headers=self._auth(),
            name="/api/v1/audit/events [LIST]"
        )
