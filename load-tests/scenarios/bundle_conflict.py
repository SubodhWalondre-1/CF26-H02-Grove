from locust import HttpUser, task, between
import random

PATIENT_ID = "PT-0001"

# Two overlapping bundles — both need OT-2 and Surgeon, creating guaranteed bundle-vs-bundle conflict
BUNDLE_A_RESOURCES = ["RES-OT2", "RES-SURG-A", "RES-ANES-A"]
BUNDLE_B_RESOURCES = ["RES-OT2", "RES-SURG-A", "RES-VENT3"]

class BundleConflictUser(HttpUser):
    """
    Half the users request Bundle A, half request Bundle B.
    Both overlap on OT-2 + Surgeon — guaranteed conflict on every request.
    Goal: no partial locks, no 500s, conflicts appear in /conflicts list.
    """
    wait_time = between(0.1, 0.5)
    host = "http://localhost:8000"
    token: str = ""
    bundle_choice: list = []

    def on_start(self):
        resp = self.client.post(
            "/api/v1/auth/login",
            json={"username": "dr.mehta", "password": "mediora123"}
        )
        if resp.status_code == 200:
            self.token = resp.json().get("access_token", "")
        else:
            # Fallback password
            resp = self.client.post(
                "/api/v1/auth/login",
                json={"username": "dr.mehta", "password": "password"}
            )
            if resp.status_code == 200:
                self.token = resp.json().get("access_token", "")

        # Alternate between bundle types
        self.bundle_choice = random.choice([BUNDLE_A_RESOURCES, BUNDLE_B_RESOURCES])

    def _auth(self):
        return {"Authorization": f"Bearer {self.token}"} if self.token else {}

    @task(3)
    def request_bundle(self):
        self.client.post(
            "/api/v1/transactions",
            json={
                "request_type": "care_bundle",
                "patient_id": PATIENT_ID,
                "resource_ids": self.bundle_choice,
            },
            headers=self._auth(),
            name="BUNDLE_CONFLICT"
        )

    @task(1)
    def check_conflicts(self):
        self.client.get(
            "/api/v1/conflicts?status=open",
            headers=self._auth(),
            name="CHECK_CONFLICTS"
        )

    @task(1)
    def check_resources(self):
        self.client.get(
            "/api/v1/resources",
            headers=self._auth(),
            name="CHECK_RESOURCES"
        )
