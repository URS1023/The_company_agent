from __future__ import annotations

import argparse
import asyncio
import getpass
import sys
import time

import httpx


async def run_smoke(base_url: str, username: str, password: str, timeout: int) -> int:
    async with httpx.AsyncClient(base_url=base_url.rstrip("/"), timeout=30) as client:
        health = await client.get("/api/v1/health/ready")
        print(f"health.ready={health.status_code}")
        login = await client.post(
            "/api/v1/auth/login", json={"username": username, "password": password}
        )
        if login.status_code != 200:
            print(f"auth.login={login.status_code}")
            return 2
        print("auth.login=200")

        bidding = await client.post(
            "/api/v1/demos/bidding/analyze",
            json={
                "project_name": "原生冒烟招投标项目",
                "requirements": [{"name": "营业执照", "search_terms": ["营业执照"]}],
                "knowledge_text": "公司营业执照和历史业绩",
            },
        )
        finance = await client.post(
            "/api/v1/demos/finance/analyze",
            json={"rows": [{"revenue": "100", "cost": "40"}], "budget": 50},
        )
        print(f"demo.bidding={bidding.status_code}")
        print(f"demo.finance={finance.status_code}")
        if bidding.status_code != 200 or finance.status_code != 200:
            return 3

        upload = await client.post(
            "/api/v1/files",
            files={"upload": ("native-smoke.txt", b"native smoke knowledge", "text/plain")},
        )
        print(f"files.upload={upload.status_code}")
        if upload.status_code != 201:
            return 4
        knowledge = await client.post(
            "/api/v1/knowledge-bases", json={"name": "Native Smoke KB", "visibility": "private"}
        )
        print(f"knowledge.create={knowledge.status_code}")
        if knowledge.status_code != 201:
            return 5
        document = await client.post(
            f"/api/v1/knowledge-bases/{knowledge.json()['id']}/documents",
            json={"file_id": upload.json()["id"]},
        )
        print(f"knowledge.document={document.status_code}")
        if document.status_code != 202:
            return 6

        conversation = await client.post("/api/v1/conversations", json={"title": "Native Smoke"})
        if conversation.status_code != 201:
            print(f"conversation.create={conversation.status_code}")
            return 7
        run_response = await client.post(
            f"/api/v1/runs/conversations/{conversation.json()['id']}",
            json={
                "content": "请用一句话确认原生 Worker 已执行。",
                "file_ids": [upload.json()["id"]],
                "knowledge_base_ids": [knowledge.json()["id"]],
            },
        )
        print(f"run.create={run_response.status_code}")
        if run_response.status_code != 202:
            return 8
        run_id = run_response.json()["id"]
        deadline = time.monotonic() + timeout
        final_status = "unknown"
        while time.monotonic() < deadline:
            current = await client.get(f"/api/v1/runs/{run_id}")
            if current.status_code != 200:
                print(f"run.get={current.status_code}")
                return 9
            final_status = current.json()["status"]
            if final_status in {"completed", "failed", "cancelled"}:
                break
            await asyncio.sleep(2)
        print(f"run.final_status={final_status}")
        steps = await client.get(f"/api/v1/runs/{run_id}/steps")
        calls = await client.get(f"/api/v1/runs/{run_id}/tool-calls")
        print(f"run.steps={steps.status_code}")
        print(f"run.tool_calls={calls.status_code}")
        if final_status != "completed":
            # Preserve the server's terminal state without printing model output.
            return 10

        artifact = await client.post(
            f"/api/v1/runs/{run_id}/render/document",
            json={
                "name": "native-smoke.docx",
                "spec": {"title": "Native Smoke", "sections": [{"paragraphs": ["OK"]}]},
            },
        )
        print(f"artifact.document={artifact.status_code}")
        if artifact.status_code != 201:
            return 11
        artifact_id = artifact.json()["id"]
        preview = await client.get(f"/api/v1/artifacts/{artifact_id}/preview")
        use_as_input = await client.post(f"/api/v1/artifacts/{artifact_id}/use-as-input")
        print(f"artifact.preview={preview.status_code}")
        print(f"artifact.use_as_input={use_as_input.status_code}")
        if preview.status_code != 200 or use_as_input.status_code != 200:
            return 12
        print("native.smoke=passed")
        return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run authenticated native Company Agent smoke tests."
    )
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--username", default="workspace-admin")
    parser.add_argument("--timeout", type=int, default=600)
    args = parser.parse_args()
    password = getpass.getpass("Workspace password: ")
    try:
        return asyncio.run(run_smoke(args.base_url, args.username, password, args.timeout))
    except (httpx.HTTPError, TimeoutError) as exc:
        print(f"native.smoke=failed:{type(exc).__name__}")
        return 20


if __name__ == "__main__":
    sys.exit(main())
