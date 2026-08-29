#!/usr/bin/env python3
"""
Descarga el m3u del usuario, extrae los tvg-id usados por los canales en vivo,
descarga una guía EPG pública (XMLTV) y genera un epg.xml.gz filtrado que
contiene solo los canales presentes en el m3u.
"""

import gzip
import os
import re
import sys
import urllib.request
from xml.etree import ElementTree as ET

# URL del m3u (se pasa como variable de entorno, viene de un Secret de GitHub)
M3U_URL = os.environ.get("M3U_URL")

# Fuentes EPG públicas a combinar (se prueban en orden, se fusionan resultados)
EPG_SOURCE_URLS = [
    "https://epgshare01.online/epgshare01/epg_ripper_ES1.xml.gz",
]

OUTPUT_PATH = "epg.xml.gz"


def fail(msg):
    print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(1)


def download(url, timeout=90):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def extract_tvg_ids(m3u_text):
    ids = set()
    for m in re.finditer(r'tvg-id="([^"]*)"', m3u_text):
        val = m.group(1).strip()
        if val:
            ids.add(val)
    return ids


def main():
    if not M3U_URL:
        fail("No se definió la variable de entorno M3U_URL (configura el Secret M3U_URL en GitHub).")

    print("1) Descargando m3u...")
    try:
        m3u_bytes = download(M3U_URL)
    except Exception as e:
        fail(f"No se pudo descargar el m3u: {e}")
    m3u_text = m3u_bytes.decode("utf-8", errors="ignore")

    tvg_ids = extract_tvg_ids(m3u_text)
    print(f"   tvg-id únicos encontrados en el m3u: {len(tvg_ids)}")
    if not tvg_ids:
        fail("No se encontraron tvg-id en el m3u, revisa la URL.")

    matched = {}
    programme_elements = []
    channel_elements = {}

    for src_url in EPG_SOURCE_URLS:
        print(f"2) Descargando fuente EPG: {src_url}")
        try:
            raw = download(src_url)
        except Exception as e:
            print(f"   Aviso: no se pudo descargar {src_url}: {e}")
            continue

        try:
            xml_bytes = gzip.decompress(raw)
        except OSError:
            xml_bytes = raw  # por si algún día no viene comprimido

        try:
            root = ET.fromstring(xml_bytes)
        except ET.ParseError as e:
            print(f"   Aviso: no se pudo parsear {src_url}: {e}")
            continue

        for ch in root.findall("channel"):
            cid = ch.get("id")
            if cid in tvg_ids and cid not in channel_elements:
                channel_elements[cid] = ch
                matched[cid] = True

        for pr in root.findall("programme"):
            if pr.get("channel") in tvg_ids:
                programme_elements.append(pr)

    print(f"3) Canales con guía encontrada: {len(channel_elements)} / {len(tvg_ids)}")
    unmatched = sorted(tvg_ids - set(channel_elements.keys()))
    if unmatched:
        print(f"   Sin coincidencia ({len(unmatched)}), primeros 30:")
        for u in unmatched[:30]:
            print(f"     - {u}")

    new_root = ET.Element("tv", {"generator-info-name": "auto-epg-filter"})
    for ch in channel_elements.values():
        new_root.append(ch)
    for pr in programme_elements:
        new_root.append(pr)

    out_xml = ET.tostring(new_root, encoding="utf-8", xml_declaration=True)
    with gzip.open(OUTPUT_PATH, "wb") as f:
        f.write(out_xml)

    print(f"4) Guardado {OUTPUT_PATH}: {len(channel_elements)} canales, {len(programme_elements)} programas.")


if __name__ == "__main__":
    main()
