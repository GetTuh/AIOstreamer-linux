import argparse
import json
import re
import urllib.request

PACKAGES = {
    "certifi": "2026.1.4",
    "charset-normalizer": "3.4.4",
    "idna": "3.18",
    "jaraco.classes": "3.4.0",
    "jaraco.context": "6.1.2",
    "jaraco.functools": "4.6.0",
    "keyring": "25.7.0",
    "more-itertools": "11.2.0",
    "requests": "2.33.1",
    "typing-extensions": "4.16.0",
    "urllib3": "2.8.0",
    "websocket-client": "1.9.2",
    "yt-dlp": "2026.8.19",
}


def wheel_ok(filename, py, arch):
    match = re.match(r".+-([^-]+)-([^-]+)-([^-]+)\.whl$", filename)
    if not match:
        return 0
    pytag, abi, plat = match.groups()
    cp = "cp" + py.replace(".", "")
    if plat == "any" and pytag.startswith("py3"):
        return 4
    if not plat.startswith("manylinux") or not plat.endswith(arch):
        return 0
    if pytag == cp and abi == cp:
        return 3
    if abi == "abi3":
        minimum = int(pytag[3:] or 0) if pytag.startswith("cp3") else 99
        return 2 if minimum <= int(py.split(".")[1]) else 0
    return 0


def pick(name, version, py, arch):
    with urllib.request.urlopen("https://pypi.org/pypi/%s/%s/json" % (name, version)) as resp:
        data = json.load(resp)
    best = None
    for f in data["urls"]:
        if f["packagetype"] != "bdist_wheel":
            continue
        score = wheel_ok(f["filename"], py, arch)
        if score and (best is None or score > best[0]):
            best = (score, f)
    if best is None:
        raise SystemExit("no wheel for %s %s (python %s, %s)" % (name, version, py, arch))
    return best[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--python", default="3.13")
    parser.add_argument("--arch", default="x86_64")
    parser.add_argument("--output", default="python-deps.json")
    args = parser.parse_args()
    sources = []
    for name, version in sorted(PACKAGES.items()):
        f = pick(name, version, args.python, args.arch)
        sources.append({"type": "file", "url": f["url"], "sha256": f["digests"]["sha256"], "only-arches": [args.arch]} if "manylinux" in f["filename"] else {"type": "file", "url": f["url"], "sha256": f["digests"]["sha256"]})
    module = {
        "name": "python-deps",
        "buildsystem": "simple",
        "build-commands": [
            "pip3 install --verbose --exists-action=i --no-deps --no-index --find-links=\"file://${PWD}\" --prefix=${FLATPAK_DEST} --no-build-isolation " + " ".join(sorted(PACKAGES))
        ],
        "sources": sources,
    }
    with open(args.output, "w") as out:
        json.dump(module, out, indent=2)
        out.write("\n")


if __name__ == "__main__":
    main()
