"""Moderator commands, posted as issue comments by the repo owner or collaborators:

  /approve [model_id]   make a model live (on a submission issue the id can be left out)
  /hide [model_id]      hide a model from everyone
  /delete [model_id]    remove a model completely
  /trust username       future models from this GitHub user go live without review

Reads COMMENT_BODY and ISSUE_NUMBER from the environment. Writes the reply to result.md and changed=true/false
to $GITHUB_OUTPUT.
"""
import json
import os
import re
import shutil

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODELS = os.path.join(ROOT, "models")
ID_RE = re.compile(r"^[a-z0-9_-]{1,64}$")


def output(key, value):
    path = os.environ.get("GITHUB_OUTPUT")
    if path:
        with open(path, "a", encoding="utf-8") as f:
            f.write(f"{key}={value}\n")


def find_by_issue(number):
    for model_id in os.listdir(MODELS):
        meta_path = os.path.join(MODELS, model_id, "meta.json")
        if os.path.isfile(meta_path):
            with open(meta_path, encoding="utf-8") as f:
                if json.load(f).get("issue") == number:
                    return model_id
    return None


def set_status(model_id, status):
    meta_path = os.path.join(MODELS, model_id, "meta.json")
    with open(meta_path, encoding="utf-8") as f:
        meta = json.load(f)
    meta["status"] = status
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2)


def main():
    comment = os.environ.get("COMMENT_BODY", "").strip()
    issue = int(os.environ.get("ISSUE_NUMBER", "0"))
    match = re.match(r"^/(approve|hide|delete|trust)\b\s*(\S*)", comment)
    if not match:
        output("changed", "false")
        return
    command, arg = match.group(1), match.group(2).strip().lower()
    replies = []

    if command == "trust":
        if not re.fullmatch(r"[a-z0-9-]{1,39}", arg):
            replies.append("Usage: `/trust github-username`")
        else:
            with open(os.path.join(ROOT, "trusted.txt"), "a", encoding="utf-8") as f:
                f.write(arg + "\n")
            replies.append(f"`{arg}` is now a trusted creator, so their next models go live without review.")
    else:
        model_id = arg or find_by_issue(issue)
        if not model_id or not ID_RE.match(model_id) or not os.path.isdir(os.path.join(MODELS, model_id)):
            replies.append(f"Couldn't find that model. Usage: `/{command} model_id`")
        elif command == "delete":
            shutil.rmtree(os.path.join(MODELS, model_id))
            replies.append(f"Deleted `{model_id}`.")
        else:
            set_status(model_id, "approved" if command == "approve" else "hidden")
            replies.append(f"{'Approved' if command == 'approve' else 'Hid'} `{model_id}`.")

    with open(os.path.join(ROOT, "result.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(replies))
    output("changed", "true")


if __name__ == "__main__":
    main()
