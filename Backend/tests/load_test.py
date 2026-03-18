#!/usr/bin/env python3
"""
Load Test Script for Agent Goldfinger Backend.

Simulates concurrent users hitting the API with a realistic mix of endpoints.
Uses ramp-up stages to identify performance cliffs.

Usage:
    python tests/load_test.py --users 10 --duration 30
    python tests/load_test.py --users 50 --duration 60 --base-url http://localhost:8000
"""
import argparse
import asyncio
import random
import statistics
import sys
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional

try:
    import httpx
except ImportError:
    print("httpx is required. Install with: pip install httpx")
    sys.exit(1)


# ============================================================================
# Configuration
# ============================================================================

# Test SKUs — adjust to match your database
TEST_SKUS = [
    "ST61533",
    "ST61543",
    "ST61563",
    "ST61544",
]

# Endpoint weights (must sum to 1.0)
ENDPOINTS = [
    ("GET /auth/me", "/api/v1/auth/me", 0.30),
    ("GET /items/sku/{sku}", "/api/v1/items/sku/{sku}", 0.20),
    ("GET /items/sku/{sku}/bom", "/api/v1/items/sku/{sku}/bom", 0.20),
    ("GET /inventory/{sku}", "/api/v1/inventory/{sku}", 0.20),
    ("GET /production/feasibility/{sku}", "/api/v1/production/feasibility/{sku}", 0.10),
]

# Default test user credentials
DEFAULT_EMAIL = "admin@eaglebeverage.com"
DEFAULT_PASSWORD = "admin1234"


# ============================================================================
# Data Classes
# ============================================================================

@dataclass
class RequestResult:
    endpoint: str
    status_code: int
    latency_ms: float
    error: Optional[str] = None


@dataclass
class StageResult:
    stage_name: str
    num_users: int
    duration_s: float
    results: List[RequestResult] = field(default_factory=list)

    @property
    def total_requests(self) -> int:
        return len(self.results)

    @property
    def errors(self) -> int:
        return sum(1 for r in self.results if r.error or r.status_code >= 400)

    @property
    def error_rate(self) -> float:
        return (self.errors / self.total_requests * 100) if self.total_requests else 0

    @property
    def rps(self) -> float:
        return self.total_requests / self.duration_s if self.duration_s else 0

    def latencies(self) -> List[float]:
        return sorted([r.latency_ms for r in self.results if r.error is None and r.status_code < 400])

    def percentile(self, p: float) -> float:
        lats = self.latencies()
        if not lats:
            return 0
        k = (len(lats) - 1) * (p / 100)
        f = int(k)
        c = f + 1 if f + 1 < len(lats) else f
        return lats[f] + (k - f) * (lats[c] - lats[f])

    def per_endpoint_stats(self) -> Dict[str, Dict]:
        by_ep: Dict[str, List[RequestResult]] = {}
        for r in self.results:
            by_ep.setdefault(r.endpoint, []).append(r)

        stats = {}
        for ep, results in sorted(by_ep.items()):
            lats = sorted([r.latency_ms for r in results if r.error is None and r.status_code < 400])
            errs = sum(1 for r in results if r.error or r.status_code >= 400)
            stats[ep] = {
                "count": len(results),
                "errors": errs,
                "p50": lats[len(lats) // 2] if lats else 0,
                "p95": lats[int(len(lats) * 0.95)] if lats else 0,
                "max": max(lats) if lats else 0,
            }
        return stats


# ============================================================================
# Core Logic
# ============================================================================

async def authenticate(client: httpx.AsyncClient, base_url: str, email: str, password: str) -> Optional[str]:
    """Authenticate and return JWT token."""
    try:
        resp = await client.post(
            f"{base_url}/api/v1/auth/login",
            data={"username": email, "password": password},
        )
        if resp.status_code == 200:
            data = resp.json()
            return data.get("access_token")
        else:
            print(f"  Auth failed for {email}: {resp.status_code} {resp.text[:100]}")
            return None
    except Exception as e:
        print(f"  Auth error for {email}: {e}")
        return None


async def simulate_user(
    user_id: int,
    client: httpx.AsyncClient,
    base_url: str,
    token: str,
    duration_s: float,
    results: List[RequestResult],
):
    """Simulate a single user making random API calls."""
    headers = {"Authorization": f"Bearer {token}"}
    end_time = time.time() + duration_s

    while time.time() < end_time:
        # Pick random endpoint based on weights
        rand = random.random()
        cumulative = 0
        chosen = ENDPOINTS[0]
        for ep in ENDPOINTS:
            cumulative += ep[2]
            if rand <= cumulative:
                chosen = ep
                break

        ep_name, ep_path, _ = chosen
        sku = random.choice(TEST_SKUS)
        url = f"{base_url}{ep_path.format(sku=sku)}"

        start = time.time()
        try:
            resp = await client.get(url, headers=headers)
            latency = (time.time() - start) * 1000
            results.append(RequestResult(
                endpoint=ep_name,
                status_code=resp.status_code,
                latency_ms=round(latency, 1),
            ))
        except Exception as e:
            latency = (time.time() - start) * 1000
            results.append(RequestResult(
                endpoint=ep_name,
                status_code=0,
                latency_ms=round(latency, 1),
                error=str(e)[:80],
            ))

        # Random delay between requests (50-500ms)
        await asyncio.sleep(random.uniform(0.05, 0.5))


async def run_stage(
    stage_name: str,
    num_users: int,
    duration_s: float,
    base_url: str,
    token: str,
) -> StageResult:
    """Run a single load test stage."""
    print(f"\n{'='*60}")
    print(f"  Stage: {stage_name} ({num_users} users, {duration_s:.0f}s)")
    print(f"{'='*60}")

    results: List[RequestResult] = []

    async with httpx.AsyncClient(
        timeout=httpx.Timeout(60.0, connect=10.0),
        limits=httpx.Limits(max_connections=100, max_keepalive_connections=50),
    ) as client:
        tasks = [
            simulate_user(i, client, base_url, token, duration_s, results)
            for i in range(num_users)
        ]
        await asyncio.gather(*tasks)

    stage = StageResult(
        stage_name=stage_name,
        num_users=num_users,
        duration_s=duration_s,
        results=results,
    )

    # Print stage summary
    print(f"  Requests: {stage.total_requests} | RPS: {stage.rps:.1f} | "
          f"Errors: {stage.errors} ({stage.error_rate:.1f}%)")
    lats = stage.latencies()
    if lats:
        print(f"  Latency: p50={stage.percentile(50):.0f}ms  p95={stage.percentile(95):.0f}ms  "
              f"p99={stage.percentile(99):.0f}ms  max={max(lats):.0f}ms")

    # Per-endpoint breakdown
    for ep, s in stage.per_endpoint_stats().items():
        print(f"    {ep}: {s['count']} reqs, {s['errors']} errs, "
              f"p50={s['p50']:.0f}ms, p95={s['p95']:.0f}ms, max={s['max']:.0f}ms")

    return stage


def print_summary(stages: List[StageResult]):
    """Print final summary table comparing all stages."""
    print(f"\n{'='*80}")
    print("  LOAD TEST SUMMARY")
    print(f"{'='*80}")

    header = f"{'Stage':<15} {'Users':>5} {'Reqs':>6} {'RPS':>6} {'Err%':>6} {'p50':>7} {'p95':>7} {'p99':>7} {'Max':>7}"
    print(header)
    print("-" * len(header))

    for s in stages:
        print(f"{s.stage_name:<15} {s.num_users:>5} {s.total_requests:>6} "
              f"{s.rps:>6.1f} {s.error_rate:>5.1f}% "
              f"{s.percentile(50):>6.0f}ms {s.percentile(95):>6.0f}ms "
              f"{s.percentile(99):>6.0f}ms {(max(s.latencies()) if s.latencies() else 0):>6.0f}ms")

    print(f"{'='*80}\n")


async def main():
    parser = argparse.ArgumentParser(description="Load test for Agent Goldfinger API")
    parser.add_argument("--users", type=int, default=10, help="Max concurrent users (default: 10)")
    parser.add_argument("--duration", type=float, default=30, help="Duration per stage in seconds (default: 30)")
    parser.add_argument("--base-url", type=str, default="http://127.0.0.1:8000", help="Base URL")
    parser.add_argument("--email", type=str, default=DEFAULT_EMAIL, help="Login email")
    parser.add_argument("--password", type=str, default=DEFAULT_PASSWORD, help="Login password")
    args = parser.parse_args()

    print(f"Load Test Configuration:")
    print(f"  Base URL: {args.base_url}")
    print(f"  Max users: {args.users}")
    print(f"  Duration per stage: {args.duration}s")

    # Authenticate once
    print(f"\nAuthenticating as {args.email}...")
    async with httpx.AsyncClient(timeout=30) as client:
        token = await authenticate(client, args.base_url, args.email, args.password)

    if not token:
        print("Authentication failed. Exiting.")
        sys.exit(1)
    print("Authentication successful.")

    # Define ramp-up stages (capped at --users)
    stage_sizes = [s for s in [1, 5, 10, 20, 50] if s <= args.users]
    if args.users not in stage_sizes:
        stage_sizes.append(args.users)

    stages: List[StageResult] = []
    for num_users in stage_sizes:
        stage = await run_stage(
            stage_name=f"{num_users}-users",
            num_users=num_users,
            duration_s=args.duration,
            base_url=args.base_url,
            token=token,
        )
        stages.append(stage)

        # Brief pause between stages
        if num_users != stage_sizes[-1]:
            print("  Cooling down 3s...")
            await asyncio.sleep(3)

    print_summary(stages)


if __name__ == "__main__":
    asyncio.run(main())
