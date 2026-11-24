"""Hides a model automatically once it has REPORT_LIMIT open reports. A moderator can /approve it again.

Reads MODEL_ID and OPEN_REPORTS (how many open report issues mention it) from the environment.
"""
import json
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPORT_LIMIT = int(os.environ.get("REPORT_LIMIT", "3"))


def output(key, value):
    path = os.environ.get("GITHUB_OUTPUT")
    if path:
        with open(path, "a", encoding="utf-8") as f:
            f.write(f"{key}={value}\n")


def main():
    model_id = os.environ.get("MODEL_ID", "").strip().lower()
    reports = int(os.environ.get("OPEN_REPORTS", "0"))
    meta_path = os.path.join(ROOT, "models", model_id, "meta.json")
    if not re.fullmatch(r"[a-z0-9_-]{1,64}", model_id) or not os.path.isfile(meta_path):
        output("changed", "false")
        return
    with open(meta_path, encoding="utf-8") as f:
        meta = json.load(f)
    if reports >= REPORT_LIMIT and meta.get("status") != "hidden":
        meta["status"] = "hidden"
        meta["hidden_reason"] = f"{reports} reports"
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(meta, f, indent=2)
        output("changed", "true")
    else:
        output("changed", "false")


if __name__ == "__main__":
    main()
