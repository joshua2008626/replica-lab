import asyncio
import sys
from pathlib import Path

# Ensure backend root is in Python sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx
from main import app


async def test_health_endpoint():
    print("Testing FastAPI app startup and GET /api/health...")
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        # Test root endpoint
        root_resp = await client.get("/")
        print(f"GET / -> Status {root_resp.status_code}")
        print("Root Response:", root_resp.json())
        assert root_resp.status_code == 200, "Root endpoint did not return 200"

        # Test health endpoint
        health_resp = await client.get("/api/health")
        print(f"GET /api/health -> Status {health_resp.status_code}")
        health_data = health_resp.json()
        print("Health Response:", health_data)

        assert health_resp.status_code == 200, "Health endpoint did not return 200"
        assert health_data["status"] == "healthy", "App status is not healthy"
        assert health_data["components"]["database"] == "connected", "Database is not connected"
        print("\nAll health assertions passed successfully!")


if __name__ == "__main__":
    try:
        asyncio.run(test_health_endpoint())
    except Exception as exc:
        print(f"\nVerification failed: {exc}", file=sys.stderr)
        sys.exit(1)
