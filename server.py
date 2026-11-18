"""
BitChord Hi-Res Lossless addon — Internet Archive edition.

Provides:
  GET /manifest.json
  GET /search?q=artist+title&quality=hires
  GET /stream/<identifier>?quality=hires

Only returns original .flac files found in Internet Archive metadata.
No transcoding, ripping, DRM circumvention, or false Hi-Res labels.
"""
from flask import Flask, jsonify, request
import requests
import re
import urllib.parse
from functools import lru_cache

app = Flask(__name__)
HTTP = requests.Session()
HTTP.headers.update({"User-Agent": "BitChord-HiRes-Addon/1.0 (self-hosted personal music source)"})

MANIFEST = {
    "id": "id.king.hireslossless.internetarchive",
    "name": "Hi-Res Lossless (Internet Archive)",
    "version": "1.0.0",
    "description": "Original FLAC files from Internet Archive. Hi-Res specifications are reported only when read from the FLAC header.",
    "resources": ["search", "stream"],
    "allowDownloads": 1,
    "checkValidLossless": 0,
    "settings": [{
        "key": "quality",
        "type": "select",
        "label": "Audio quality",
        "default": "hires",
        "options": [
            {"value": "hires", "label": "Hi-Res / best available FLAC"},
            {"value": "lossless", "label": "Lossless FLAC"}
        ]
    }]
}
IA_ADVANCED = "https://archive.org/advancedsearch.php"
IA_METADATA = "https://archive.org/metadata/{}"

def clean_text(value):
    if isinstance(value, list):
        value = value[0] if value else ""
    return str(value or "").strip()

def flac_info(url):
    """Read FLAC STREAMINFO from the first 42 bytes; return measured metadata."""
    try:
        r = HTTP.get(url, headers={"Range": "bytes=0-41"}, timeout=15, stream=True)
        if r.status_code not in (200, 206):
            return {}
        data = next(r.iter_content(64), b"")
        r.close()
        if len(data) < 42 or data[:4] != b"fLaC":
            return {}
        # First metadata block header (4 bytes), then 34-byte STREAMINFO.
        if (data[4] & 0x7f) != 0:
            return {}
        si = data[8:26]
        packed = int.from_bytes(si[10:18], "big")
        sample_rate = (packed >> 44) & 0xfffff
        channels = ((packed >> 41) & 0x7) + 1
        bit_depth = ((packed >> 36) & 0x1f) + 1
        total_samples = packed & ((1 << 36) - 1)
        return {
            "sampleRate": sample_rate,
            "bitDepth": bit_depth,
            "channels": channels,
            "duration": round(total_samples / sample_rate, 2) if sample_rate else None
        }
    except requests.RequestException:
        return {}

def metadata(identifier):
    r = HTTP.get(IA_METADATA.format(urllib.parse.quote(identifier, safe="")), timeout=20)
    r.raise_for_status()
    return r.json()

def pick_flac(identifier):
    data = metadata(identifier)
    files = data.get("files", [])
    candidates = []
    for f in files:
        name = clean_text(f.get("name"))
        if name.lower().endswith(".flac") and not f.get("source") == "metadata":
            candidates.append((name, f))
    if not candidates:
        return None
    # Prefer the largest original FLAC file, which is a useful quality heuristic,
    # but do not claim a specific bit depth until the FLAC header is inspected.
    candidates.sort(key=lambda item: int(item[1].get("size", 0) or 0), reverse=True)
    filename, file_info = candidates[0]
    encoded = urllib.parse.quote(filename, safe="/")
    url = f"https://archive.org/download/{urllib.parse.quote(identifier, safe='')}/{encoded}"
    return {"url": url, "filename": filename, "file": file_info}

@app.get("/")
def root():
    return jsonify({"service": MANIFEST["name"], "manifest": "/manifest.json"})

@app.get("/manifest.json")
def manifest():
    return jsonify(MANIFEST)

@app.get("/search")
def search():
    q = request.args.get("q", "").strip()
    if not q:
        return jsonify({"tracks": [], "total": 0})
    # Search IA's indexed audio collection for FLAC-bearing items.
    terms = re.findall(r"[A-Za-z0-9][A-Za-z0-9'_-]*", q)[:8]
    if not terms:
        return jsonify({"tracks": [], "total": 0})
    phrase = " AND ".join(f'all:{t}' for t in terms)
    query = f'mediatype:audio AND ({phrase})'
    params = {
        "q": query,
        "fl[]": ["identifier", "title", "creator", "year"],
        "rows": 30,
        "page": 1,
        "output": "json"
    }
    try:
        r = HTTP.get(IA_ADVANCED, params=params, timeout=25)
        r.raise_for_status()
        docs = r.json().get("response", {}).get("docs", [])
    except (requests.RequestException, ValueError):
        return jsonify({"tracks": [], "total": 0, "error": "Internet Archive search is temporarily unavailable"}), 502

    tracks = []
    for d in docs:
        identifier = clean_text(d.get("identifier"))
        if not identifier:
            continue
        try:
            chosen = pick_flac(identifier)
            if not chosen:
                continue
            title = clean_text(d.get("title")) or identifier
            artist = clean_text(d.get("creator")) or "Unknown artist"
            tracks.append({
                "id": identifier,
                "title": title,
                "artist": artist,
                "album": "",
                "duration": None,
                "format": "flac",
                "audioQuality": "LOSSLESS",
                "streamURL": None
            })
        except requests.RequestException:
            continue
        if len(tracks) >= 12:
            break
    return jsonify({"tracks": tracks, "total": len(tracks)})

@app.get("/stream/<path:identifier>")
def stream(identifier):
    try:
        chosen = pick_flac(identifier)
        if not chosen:
            return jsonify({"error": "No original FLAC file found for this item"}), 404
        info = flac_info(chosen["url"])
        result = {
            "url": chosen["url"],
            "format": "flac",
            "quality": "FLAC lossless",
            "codec": "flac",
            "container": "flac",
            "manifest": "none",
            "encrypted": False
        }
        result.update({k: v for k, v in info.items() if v is not None})
        if info.get("sampleRate") and info.get("bitDepth"):
            if info["bitDepth"] >= 24 and info["sampleRate"] > 44100:
                result["quality"] = f"Hi-Res FLAC · {info['bitDepth']}-bit / {info['sampleRate']//1000} kHz"
            else:
                result["quality"] = f"FLAC · {info['bitDepth']}-bit / {info['sampleRate']} Hz"
        return jsonify(result)
    except requests.RequestException:
        return jsonify({"error": "Could not resolve the Internet Archive item"}), 502

if __name__ == "__main__":
    # For local testing only. Deploy behind HTTPS for use from BitChord.
    app.run(host="0.0.0.0", port=int(__import__("os").environ.get("PORT", "8080")))
