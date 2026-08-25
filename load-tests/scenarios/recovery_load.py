from locust import HttpUser, task, between
import random

PATIENT_ID = "PT-0001"
ALL_RESOURCES = ["RES-OT2", "RES-SURG-A", "RES-ANES-A", "RES-VENT3"]

class RecoveryLoadUser(HttpUser):
    """
    Creates transactions continuously, then immediately checks recovery endpoints.
    The goal is to stress the recovery engine's bookkeeping — not to simulate a crash
    (which requires docker kill), but to ensure incomplete TX tracking stays accurate.
    """
    wait_time = between(0.5, 1.5)
    host = "http://localhost:8000"
    token: str = ""

    def on_start(self):
        resp = self.client.post(
            "/api/v1/auth/login",
            json={"username": "admin.ops", "password": "mediora123"}
        )
        if resp.status_code == 200:
            self.token = resp.json().get("access_token", "")
        else:
            # Fallback admin credentials
            resp = self.client.post(
                "/api/v1/auth/login",
                json={"username": "admin.coord", "password": "password"}
            )
            if resp.status_code == 200:
                self.token = resp.json().get("access_token", "")
            else:
                resp = self.client.post(
                    "/api/v1/auth/login",
                    json={"username": "admin.ops", "password": "password"}
                )
                if resp.status_code == 200:
                    self.token = resp.json().get("access_token", "")

    def _auth(self):
        return {"Authorization": f"Bearer {self.token}"} if self.token else {}

    @task(4)
    def create_and_cancel_tx(self):
        """Create a TX then immediately cancel — exercises the compensation path."""
        resource_id = random.choice(ALL_RESOURCES)
        create_resp = self.client.post(
            "/api/v1/transactions",
            json={
                "request_type": "single_resource",
                "patient_id": PATIENT_ID,
                "resource_id": resource_id,
            },
            headers=self._auth(),
            name="RECOVERY_CREATE"
        )
        if create_resp.status_code == 201:
            tx_id = create_resp.json().get("tx_id")
            if tx_id:
                self.client.post(
                    f"/api/v1/transactions/{tx_id}/cancel",
                    json={"reason": "recovery load test"},
                    headers=self._auth(),
                    name="RECOVERY_CANCEL"
                )

    @task(2)
    def poll_incomplete_transactions(self):
        """Admin monitoring — verifies recovery engine cleans up incomplete TXs."""
        self.client.get(
            "/api/v1/recovery/incomplete-transactions",
            headers=self._auth(),
            name="RECOVERY_INCOMPLETE"
        )

    @task(1)
    def poll_recovery_runs(self):
        """Check recovery run history."""
        self.client.get(
            "/api/v1/recovery/runs",
            headers=self._auth(),
            name="RECOVERY_RUNS"
        )

    @task(1)
    def manual_resolve(self):
        """Attempt manual recovery resolution on the first incomplete TX."""
        incomplete_resp = self.client.get(
            "/api/v1/recovery/incomplete-transactions",
            headers=self._auth(),
            name="RECOVERY_INCOMPLETE [resolve-check]"
        )
        if incomplete_resp.status_code == 200:
            body = incomplete_resp.json()
            items = body if isinstance(body, list) else body.get("items", [])
            if items:
                tx_id = items[0]["tx_id"]
                self.client.post(
                    f"/api/v1/recovery/{tx_id}/resolve",
                    headers=self._auth(),
                    name="RECOVERY_RESOLVE"
                )
