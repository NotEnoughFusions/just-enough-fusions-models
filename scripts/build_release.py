"""Builds dist/index.json and one dist/<id>.zip per visible model, for the "models" GitHub release."""
import hashlib
import json
import os
import shutil
import sys
import zipfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from seats import add_seats  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODELS = os.path.join(ROOT, "models")
DIST = os.path.join(ROOT, "dist")


def with_seats(data):
    """Models submitted before seats were added get them here, so riders stay on (unchanged if it has seats)."""
    try:
        geo = json.loads(data.decode("utf-8"))
    except ValueError:
        return data
    if add_seats(geo) is None:
        return data
    return json.dumps(geo, separators=(",", ":")).encode("utf-8")


def zip_model(model_id, folder):
    path = os.path.join(DIST, f"{model_id}.zip")
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        assets = os.path.join(folder, "assets")
        for dirpath, _, filenames in sorted(os.walk(assets)):
            for name in sorted(filenames):
                full = os.path.join(dirpath, name)
                arcname = os.path.relpath(full, folder).replace(os.sep, "/")
                info = zipfile.ZipInfo(arcname, date_time=(2020, 1, 1, 0, 0, 0))
                info.compress_type = zipfile.ZIP_DEFLATED
                with open(full, "rb") as f:
                    data = f.read()
                if name.endswith(".geo.json"):
                    data = with_seats(data)
                archive.writestr(info, data)
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def main():
    shutil.rmtree(DIST, ignore_errors=True)
    os.makedirs(DIST)
    entries = []
    for model_id in sorted(os.listdir(MODELS)):
        folder = os.path.join(MODELS, model_id)
        meta_path = os.path.join(folder, "meta.json")
        if not os.path.isfile(meta_path):
            continue
        with open(meta_path, encoding="utf-8") as f:
            meta = json.load(f)
        entry = {
            "id": meta["id"],
            "head": meta["head"],
            "body": meta["body"],
            "creator": meta.get("creator", "?"),
            "status": meta.get("status", "pending"),
        }
        if meta.get("kind", "pair") != "pair":
            entry["kind"] = meta["kind"]
        if meta.get("core"):
            entry["core"] = meta["core"]
        issue = meta.get("issue")
        if isinstance(issue, int) and issue > 0:
            entry["issue"] = issue        # the mod sorts "newest" by this
        if meta.get("created"):
            entry["created"] = meta["created"]
        if entry["status"] in ("approved", "pending"):
            entry["sha256"] = zip_model(model_id, folder)

        entries.append(entry)
    with open(os.path.join(DIST, "index.json"), "w", encoding="utf-8") as f:
        json.dump({"version": 1, "models": entries}, f, indent=2)
    print(f"{len(entries)} models in index")


if __name__ == "__main__":
    main()
