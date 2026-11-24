"""Checks a model submission (a GitHub issue made with the submit form) and adds it to models/.

Reads the issue from environment variables set by the workflow:
  ISSUE_NUMBER, ISSUE_AUTHOR, ISSUE_BODY, REPO_OWNER
Writes a message for the issue comment to result.md, and ok=true/false + model_id to $GITHUB_OUTPUT.

Only data is accepted (.json and .png). Nothing in a submission is ever run.
"""
import io
import json
import os
import re
import struct
import sys
import time
import urllib.parse
import urllib.request
import zipfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from seats import add_seats  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NS = "justenoughfusions_community"
MAX_ZIP = 4 * 1024 * 1024
MAX_JSON = 1024 * 1024
MAX_PNG = 512 * 1024
MAX_TEXTURE_SIDE = 512
MAX_CUBES = 3000
KINDS = {"Two Pokémon": "pair", "Triple fusion": "triple", "Omnieon": "omnieon"}
SPECIES_RE = re.compile(r"^(?:([a-z0-9_.-]+):)?([a-z0-9_./-]+)$")
ATTACHMENT_RE = re.compile(r"https://github\.com/(?:user-attachments/files|[^/\s]+/[^/\s]+/files)/\d+/[^\s)\]]+\.zip")
ANIMATION_NAMES = ["idle", "ground_idle", "walk", "ground_walk", "fly", "hover", "battle_idle", "sleep", "faint", "cry", "blink"]
# Quirks play now and then on top of a pose: quirk_<anything> while idle, battle_quirk_<anything> in battle.
QUIRK_PATTERN = re.compile(r"(battle_)?quirk_[a-z0-9_]+")
MAX_QUIRKS = 6


class SubmissionError(Exception):
    pass


def output(key, value):
    path = os.environ.get("GITHUB_OUTPUT")
    if path:
        with open(path, "a", encoding="utf-8") as f:
            f.write(f"{key}={value}\n")


def section(body, heading):
    """Text under a '### heading' in an issue-form body."""
    match = re.search(r"^###\s+" + re.escape(heading) + r"\s*$(.*?)(?=^###\s|\Z)", body, re.M | re.S)
    if not match:
        return ""
    text = match.group(1).strip()
    return "" if text == "_No response_" else text


def species_id(raw, field):
    raw = raw.strip().lower().replace(" ", "")
    if not raw:
        raise SubmissionError(f"Fill in **{field}**.")
    m = SPECIES_RE.match(raw)
    if not m:
        raise SubmissionError(f"**{field}** doesn't look like a species name: `{raw}`")
    namespace = m.group(1) or "cobblemon"
    return f"{namespace}:{m.group(2)}"


class _DropAuthOnRedirect(urllib.request.HTTPRedirectHandler):
    """Attachments redirect to a storage server, which must not receive our GitHub token."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        new = super().redirect_request(req, fp, code, msg, headers, newurl)
        if new is not None and urllib.parse.urlparse(newurl).hostname != "github.com":
            new.remove_header("Authorization")
        return new


def download(url):
    request = urllib.request.Request(url, headers={"User-Agent": "just-enough-fusions-models-bot"})
    token = os.environ.get("GITHUB_TOKEN")
    if token and url.startswith("https://github.com/"):
        request.add_header("Authorization", f"Bearer {token}")
    opener = urllib.request.build_opener(_DropAuthOnRedirect)
    with opener.open(request, timeout=60) as response:
        data = response.read(MAX_ZIP + 1)
    if len(data) > MAX_ZIP:
        raise SubmissionError("The zip is larger than 4 MB.")
    return data


def png_size(data):
    if data[:8] != b"\x89PNG\r\n\x1a\n" or data[12:16] != b"IHDR":
        raise SubmissionError("A .png file isn't a valid PNG image.")
    return struct.unpack(">II", data[16:24])


def find_bones(geo):
    geometries = geo.get("minecraft:geometry")
    if not isinstance(geometries, list) or not geometries:
        raise SubmissionError("The .geo.json has no `minecraft:geometry`. Export it from Blockbench as a Bedrock model.")
    bones = geometries[0].get("bones") or []
    if not bones:
        raise SubmissionError("The model has no bones.")
    cubes = sum(len(b.get("cubes") or []) for b in bones)
    if cubes > MAX_CUBES:
        raise SubmissionError(f"The model has {cubes} cubes; the limit is {MAX_CUBES}.")
    names = [b.get("name", "") for b in bones]
    roots = [b.get("name") for b in bones if not b.get("parent")]
    if not roots:
        raise SubmissionError("Couldn't find the model's root bone (a bone with no parent).")
    return names, roots[0]


def main():
    number = os.environ["ISSUE_NUMBER"]
    author = os.environ["ISSUE_AUTHOR"]
    body = os.environ.get("ISSUE_BODY", "")
    owner = os.environ.get("REPO_OWNER", "")

    # Older issues have no "Fusion type" field: those are two-Pokémon fusions.
    kind = KINDS.get(section(body, "Fusion type").strip(), "pair")
    core = None
    if kind == "omnieon":
        # Omnieon is an Eevee underneath: the model replaces Eevee's when the Eevee is Omnieon.
        head = body_species = "cobblemon:eevee"
    else:
        head = species_id(section(body, "Head species"), "Head species")
        body_species = species_id(section(body, "Body species"), "Body species")
        if kind == "triple":
            core = species_id(section(body, "Core species (triple fusions only)"), "Core species")
    credit = section(body, "Name to credit (optional)") or author
    credit = re.sub(r"[^\w .'-]", "", credit)[:32] or author

    files_text = section(body, "Model zip")
    urls = ATTACHMENT_RE.findall(files_text)
    if not urls:
        raise SubmissionError("I couldn't find a .zip attachment. Drag the .zip file into the **Model zip** box.")
    data = download(urls[0])

    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile:
        raise SubmissionError("The attachment isn't a valid .zip file.")

    geo_files, pngs, anims = [], [], []
    for info in archive.infolist():
        if info.is_dir():
            continue
        name = info.filename.lower()
        base = name.rsplit("/", 1)[-1]
        if base.startswith(".") or "__macosx" in name:
            continue
        if base.endswith(".geo.json"):
            geo_files.append(info)
        elif base.endswith(".animation.json"):
            anims.append(info)
        elif base.endswith(".png"):
            pngs.append(info)
    if len(geo_files) != 1:
        raise SubmissionError(f"The zip needs exactly one `.geo.json` file (found {len(geo_files)}).")
    textures = [p for p in pngs if not re.search(r"(glow|emissive)", p.filename.lower())]
    glows = [p for p in pngs if re.search(r"(glow|emissive)", p.filename.lower())]
    if len(textures) != 1:
        raise SubmissionError(f"The zip needs exactly one texture `.png` (found {len(textures)}), plus an optional `_glow.png`.")
    if len(anims) > 1 or len(glows) > 1:
        raise SubmissionError("Use at most one `.animation.json` and one `_glow.png`.")

    def read(info, limit):
        if info.file_size > limit:
            raise SubmissionError(f"`{info.filename}` is too large.")
        return archive.read(info)

    try:
        geo = json.loads(read(geo_files[0], MAX_JSON))
    except json.JSONDecodeError as e:
        raise SubmissionError(f"The .geo.json isn't valid JSON: {e}")
    bone_names, root_bone = find_bones(geo)
    seat_bone = add_seats(geo)    # Riders need seat_1 (and more for some Pokémon); add them if the model has none.

    texture = read(textures[0], MAX_PNG)
    tw, th = png_size(texture)
    if tw > MAX_TEXTURE_SIDE or th > MAX_TEXTURE_SIDE:
        raise SubmissionError(f"The texture is {tw}×{th}; the limit is {MAX_TEXTURE_SIDE}×{MAX_TEXTURE_SIDE}.")
    glow = None
    if glows:
        glow = read(glows[0], MAX_PNG)
        if png_size(glow) != (tw, th):
            raise SubmissionError("The glow texture must be the same size as the main texture.")

    if kind == "omnieon":
        name = "omnieon"
    else:
        name = f"{head.split(':')[1]}-{body_species.split(':')[1]}" + (f"-{core.split(':')[1]}" if core else "")
    suffix = f"-{number}"
    model_id = re.sub(r"[^a-z0-9_-]", "_", name)[:64 - len(suffix)] + suffix

    # Animations: rename every "animation.<anything>.<name>" to "animation.<model_id>.<name>".
    animation_json = None
    available = set()
    if anims:
        try:
            anim = json.loads(read(anims[0], MAX_JSON))
        except json.JSONDecodeError as e:
            raise SubmissionError(f"The .animation.json isn't valid JSON: {e}")
        renamed = {}
        for key, value in (anim.get("animations") or {}).items():
            short = key.rsplit(".", 1)[-1].lower()
            if re.fullmatch(r"[a-z0-9_]+", short):
                renamed[f"animation.{model_id}.{short}"] = value
                available.add(short)
        animation_json = {"format_version": anim.get("format_version", "1.8.0"), "animations": renamed}

    has_head = any(n.lower() == "head" for n in bone_names)
    head_bone = next((n for n in bone_names if n.lower() == "head"), None)

    def pose_animations(*names, look=True):
        out = []
        if has_head and look:
            out.append(f"q.look('{head_bone}')")
        for name in names:
            if name in available:
                out.append(f"q.bedrock('{model_id}', '{name}')")
                break
        return out

    standing_types = ["STAND", "NONE", "PORTRAIT", "PROFILE", "FLOAT", "HOVER"]
    walking_types = ["WALK", "SWIM", "FLY"]
    poses = {
        "standing": {"poseTypes": standing_types, "animations": pose_animations("idle", "ground_idle")},
        "walking": {"poseTypes": walking_types, "animations": pose_animations("walk", "ground_walk", "idle", "ground_idle")},
    }
    if "hover" in available:
        standing_types.remove("HOVER")
        poses["hovering"] = {"poseTypes": ["HOVER"], "animations": pose_animations("hover")}
    if "fly" in available:
        walking_types.remove("FLY")
        poses["flying"] = {"poseTypes": ["FLY"], "animations": pose_animations("fly")}
    poses["sleep"] = {"poseTypes": ["SLEEP"], "animations": pose_animations("sleep", "idle", "ground_idle", look=False)}
    poser = {
        "portraitScale": 1.0,
        "portraitTranslation": [0, -0.6, 0],
        "profileScale": 0.85,
        "profileTranslation": [0, 0.35, 0],
        "rootBone": root_bone,
        "animations": {},
        "poses": poses,
    }
    if "battle_idle" in available:
        poser["poses"]["battle-standing"] = {
            "poseTypes": ["STAND"],
            "isBattle": True,
            "animations": pose_animations("battle_idle"),
        }
    if "faint" in available:
        poser["animations"]["faint"] = f"q.bedrock_primary('{model_id}', 'faint', q.curve('one'))"
    if "cry" in available:
        poser["animations"]["cry"] = f"q.bedrock_stateful('{model_id}', 'cry')"
    quirks = sorted(n for n in available if QUIRK_PATTERN.fullmatch(n))[:MAX_QUIRKS]
    idle_quirks = [n for n in quirks if not n.startswith("battle_")]
    battle_quirks = [n for n in quirks if n.startswith("battle_")]
    for name, pose in poser["poses"].items():
        names = []
        if "blink" in available and name != "sleep":
            names.append("blink")
        if name == "standing":
            names += idle_quirks
        if name == "battle-standing":
            names += battle_quirks
        if names:
            pose["quirks"] = [f"q.bedrock_quirk('{model_id}', '{n}')" for n in names]
    unused = sorted(n for n in available if n not in ANIMATION_NAMES and n not in quirks)

    variation = {
        "aspects": [f"justenoughfusions.model/{model_id}"],
        "poser": f"{NS}:{model_id}",
        "model": f"{NS}:{model_id}.geo",
        "texture": f"{NS}:textures/fusions/{model_id}.png",
        "layers": [],
    }
    if glow is not None:
        variation["layers"].append({
            "name": "justenoughfusions_glow",
            "texture": f"{NS}:textures/fusions/{model_id}_glow.png",
            "emissive": True,
        })
    resolver = {"species": body_species, "order": 1000, "variations": [variation]}

    # Write everything under models/<id>/assets/... exactly as it will be shipped.
    base = os.path.join(ROOT, "models", model_id)
    assets = os.path.join(base, "assets", NS)

    def write(rel, content, binary=False):
        path = os.path.join(assets, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb" if binary else "w", encoding=None if binary else "utf-8") as f:
            if binary:
                f.write(content)
            else:
                json.dump(content, f, indent=2)

    write(f"bedrock/pokemon/models/{model_id}.geo.json", geo)
    write(f"bedrock/pokemon/posers/{model_id}.json", poser)
    write(f"bedrock/pokemon/resolvers/{model_id}.json", resolver)
    write(f"textures/fusions/{model_id}.png", texture, binary=True)
    if glow is not None:
        write(f"textures/fusions/{model_id}_glow.png", glow, binary=True)
    if animation_json is not None:
        write(f"bedrock/pokemon/animations/{model_id}.animation.json", animation_json)

    trusted = set()
    with open(os.path.join(ROOT, "trusted.txt"), encoding="utf-8") as f:
        for line in f:
            line = line.strip().lower()
            if line and not line.startswith("#"):
                trusted.add(line)
    status = "approved" if author.lower() in trusted or author.lower() == owner.lower() else "pending"

    meta = {
        "id": model_id,
        "head": head,
        "body": body_species,
        "kind": kind,
        **({"core": core} if core else {}),
        "creator": credit,
        "github": author,
        "issue": int(number),
        "status": status,
        "created": time.strftime("%Y-%m-%d"),
    }
    with open(os.path.join(base, "meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2)

    notes = []
    if not has_head:
        notes.append("- No bone called `head`, so it won't look around.")
    if seat_bone:
        notes.append(f"- No `seat_1` locator, so rider seats were added on top of the `{seat_bone}` bone. "
                     "To place them yourself, add locators named `seat_1`, `seat_2`... in Blockbench.")
    if not available:
        notes.append("- No animations, so it will stand still.")
    elif unused:
        notes.append("- These animations aren't used (check the names): " + ", ".join(f"`{n}`" for n in unused) + ".")
    when = "It's live now (you're a trusted creator)." if status == "approved" else \
        "It's waiting for a moderator. Players who turned on *show unreviewed models* can already see it."
    if kind == "omnieon":
        what = "Omnieon"
    elif kind == "triple":
        what = f"{head} head on {body_species} body with a {core} core"
    else:
        what = f"{head} head on {body_species} body"
    message = (f"✅ Thanks, your model **`{model_id}`** ({what}) has been added. {when}\n\n"
               f"Players will get it within a few minutes.")
    if notes:
        message += "\n\nNotes:\n" + "\n".join(notes)
    with open(os.path.join(ROOT, "result.md"), "w", encoding="utf-8") as f:
        f.write(message)
    output("ok", "true")
    output("model_id", model_id)


if __name__ == "__main__":
    try:
        main()
    except SubmissionError as e:
        with open(os.path.join(ROOT, "result.md"), "w", encoding="utf-8") as f:
            f.write(f"❌ Your submission needs a fix: {e}\n\nEdit this issue to fix it and it will be checked again.")
        output("ok", "false")
        sys.exit(0)
