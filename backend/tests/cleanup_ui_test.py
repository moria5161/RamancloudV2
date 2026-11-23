"""Remove only the exact disposable account recorded by the browser smoke test."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app


def cleanup(report_name="ai-ui-test-account.json"):
    if report_name not in {"ai-ui-test-account.json", "auth-ui-test-account.json", "assistant-ui-test-account.json", "history-warehouse-owner-test-account.json", "history-warehouse-member-test-account.json"}:
        raise ValueError("Unknown QA report")
    report = Path(__file__).resolve().parents[2] / "logs" / report_name
    data = json.loads(report.read_text(encoding="utf-8"))
    if not data["username"].startswith("qa_ai_") or not data["username"][6:].isdigit():
        raise ValueError("Not a disposable QA account")
    uid = data["user_id"]
    files = []
    with app.db_connect() as conn:
        user = conn.execute("SELECT username FROM users WHERE id = ?", (uid,)).fetchone()
        if not user:
            print("QA account already removed")
            return
        if user["username"] != data["username"]:
            raise ValueError("QA account identity mismatch")
        tasks = conn.execute("SELECT id,storage_path FROM ai_workflows WHERE user_id = ?", (uid,)).fetchall()
        for task in tasks:
            active = conn.execute("SELECT id FROM ai_plan_versions WHERE workflow_id = ? AND status IN ('queued','running','previewing')", (task["id"],)).fetchone()
            if active:
                raise ValueError("QA task is still running")
            conn.execute("DELETE FROM ai_plan_metadata WHERE version_id IN (SELECT id FROM ai_plan_versions WHERE workflow_id = ?)", (task["id"],))
            conn.execute("DELETE FROM ai_plan_versions WHERE workflow_id = ?", (task["id"],))
            files.append(task["storage_path"])
        conn.execute("DELETE FROM ai_batch_items WHERE batch_id IN (SELECT id FROM ai_workflow_batches WHERE user_id = ?)", (uid,))
        conn.execute("DELETE FROM ai_workflow_batches WHERE user_id = ?", (uid,))
        conn.execute("DELETE FROM ai_workflows WHERE user_id = ?", (uid,))
        runs = conn.execute("SELECT id FROM analysis_runs WHERE user_id = ?", (uid,)).fetchall()
        for run in runs:
            conn.execute("DELETE FROM analysis_versions WHERE run_id = ?", (run["id"],))
        conn.execute("DELETE FROM analysis_runs WHERE user_id = ?", (uid,))
        conn.execute("DELETE FROM assistant_conversations WHERE user_id = ?", (uid,))
        conn.execute("DELETE FROM sessions WHERE user_id = ?", (uid,))
        conn.execute("DELETE FROM users WHERE id = ?", (uid,))
    for storage_path in files:
        app.remove_stored_file(storage_path)
    print("Removed disposable QA account:", data["username"])


if __name__ == "__main__":
    cleanup(sys.argv[1] if len(sys.argv) > 1 else "ai-ui-test-account.json")
