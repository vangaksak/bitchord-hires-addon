# BitChord Hi-Res Lossless — Internet Archive

A self-hosted BitChord addon starter. It searches Internet Archive audio items and returns original `.flac` files only. It does not convert lossy files into FLAC.

## Files
- `manifest.json` — BitChord addon manifest
- `server.py` — HTTP API implementation
- `requirements.txt` — Python dependencies

## Run locally
```bash
python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS/Linux:
source .venv/bin/activate
pip install -r requirements.txt
python server.py
```
Test:
- `http://127.0.0.1:8080/manifest.json`
- `http://127.0.0.1:8080/search?q=bach`
- `http://127.0.0.1:8080/stream/IDENTIFIER`

## Connect to BitChord
BitChord must be able to reach the server over public HTTPS. Deploy this app to a Python host (or put it behind a reverse proxy / HTTPS tunnel). Then open:

**Settings → Sources → Add an addon**

Paste the public URL ending in `/manifest.json` (for example `https://YOUR-DOMAIN/manifest.json`) and run the health check.

## Important limitations
- This is a starter addon, not a hosted service. You must deploy it to an HTTPS server before BitChord on your phone can use it.
- Internet Archive is a public archive, not a commercial Hi-Res catalogue. Search results and playback availability vary.
- The addon reports Hi-Res only when it reads 24-bit audio with a sample rate above 44.1 kHz from the FLAC STREAMINFO header. If the header cannot be read, it reports FLAC lossless without inventing specifications.
- Respect each item's rights and access terms. Only stream material you are authorized to access.
- `checkValidLossless` is set to `0` so the source remains searchable on ordinary outputs. Use wired USB DAC/headphones for the best chance of preserving the source quality. Bluetooth codecs can be lossy.
