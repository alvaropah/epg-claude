#!/usr/bin/env python3
"""
Descarga el m3u del usuario, extrae tvg-id (y tvg-name como respaldo) de los
canales en vivo, descarga una guía EPG pública (XMLTV) y genera un
epg.xml.gz filtrado con solo los canales presentes en el m3u.

Estrategia de emparejamiento (en este orden):
  1) tvg-id exacto, sin distinguir mayúsculas/minúsculas.
  2) Si no hay match de id, se compara el tvg-name normalizado (sin acentos,
     sin sufijos de calidad como HD/UHD/4K, sin símbolos) contra el id y los
     display-name de la fuente EPG.
En ambos casos, el <channel id="..."> de salida se reescribe con el tvg-id
EXACTO tal cual aparece en tu m3u, para que tu reproductor lo reconozca.
"""

import gzip
import os
import re
import sys
import unicodedata
import urllib.request
from xml.etree import ElementTree as ET

M3U_URL = os.environ.get("M3U_URL")

EPG_SOURCE_URLS = [
    "https://epgshare01.online/epgshare01/epg_ripper_ES1.xml.gz",
]

OUTPUT_PATH = "epg.xml.gz"

QUALITY_TOKENS = r'\b(HD|UHD|FHD|SD|4K|RAW|HEVC|H265|VIP|BACKUP)\b'


def fail(msg):
    print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(1)


def download(url, timeout=90):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def normalize(s):
    """Normaliza un nombre de canal para comparación: sin acentos, sin
    sufijos de calidad (HD/UHD/4K...), sin símbolos, en minúsculas."""
    if not s:
        return ""
    s = unicodedata.normalize("NFKD", s)          # descompone acentos y letras "modificadoras" (ᵁᴴᴰ -> UHD)
    s = s.encode("ascii", "ignore").decode("ascii")  # quita lo que no sea ascii (acentos sueltos, símbolos raros)
    s = s.upper()
    s = re.sub(QUALITY_TOKENS, "", s)
    s = re.sub(r"[^A-Z0-9]", "", s)
    return s.lower()


def parse_m3u(m3u_text):
    """Devuelve dict tvg_id -> tvg_name para cada canal en vivo del m3u."""
    tvg_map = {}
    for line in m3u_text.splitlines():
        if not line.startswith("#EXTINF"):
            continue
        id_m = re.search(r'tvg-id="([^"]*)"', line)
        if not id_m:
            continue
        tid = id_m.group(1).strip()
        if not tid:
            continue
        name_m = re.search(r'tvg-name="([^"]*)"', line)
        tname = name_m.group(1).strip() if name_m else ""
        if tid not in tvg_map or not tvg_map[tid]:
            tvg_map[tid] = tname
    return tvg_map


def main():
    if not M3U_URL:
        fail("No se definió la variable de entorno M3U_URL (configura el Secret M3U_URL en GitHub).")

    print("1) Descargando m3u...")
    try:
        m3u_bytes = download(M3U_URL)
    except Exception as e:
        fail(f"No se pudo descargar el m3u: {e}")
    m3u_text = m3u_bytes.decode("utf-8", errors="ignore")

    tvg_map = parse_m3u(m3u_text)
    tvg_ids = set(tvg_map.keys())
    print(f"   tvg-id únicos encontrados en el m3u: {len(tvg_ids)}")
    if not tvg_ids:
        fail("No se encontraron tvg-id en el m3u, revisa la URL.")

    tvg_ids_lower = {tid.lower(): tid for tid in tvg_ids}
    tvg_names_norm = {tid: normalize(name) for tid, name in tvg_map.items()}

    # Recolectar todos los <channel> y <programme> de todas las fuentes
    all_channels = []       # list of (source_id, element)
    programmes_by_srcid = {}  # source_id (lower) -> [elementos <programme>]

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
            xml_bytes = raw
        try:
            root = ET.fromstring(xml_bytes)
        except ET.ParseError as e:
            print(f"   Aviso: no se pudo parsear {src_url}: {e}")
            continue

        for ch in root.findall("channel"):
            cid = ch.get("id") or ""
            all_channels.append((cid, ch))

        for pr in root.findall("programme"):
            cid = (pr.get("channel") or "").lower()
            programmes_by_srcid.setdefault(cid, []).append(pr)

    print(f"   Canales totales cargados de las fuentes EPG: {len(all_channels)}")

    # --- Paso 1: match exacto por tvg-id (case-insensitive) ---
    matched = {}  # tvg_id_original -> (source_id, channel_element)
    for cid, ch in all_channels:
        original = tvg_ids_lower.get(cid.lower())
        if original and original not in matched:
            matched[original] = (cid, ch)

    id_match_count = len(matched)

    # --- Paso 2: match por nombre normalizado (para lo que quedó sin match) ---
    # Índice: nombre normalizado -> (source_id, channel_element)
    name_index = {}
    for cid, ch in all_channels:
        keys = {normalize(cid)}
        for dn in ch.findall("display-name"):
            if dn.text:
                keys.add(normalize(dn.text))
        for k in keys:
            if k and k not in name_index:
                name_index[k] = (cid, ch)

    for tid in tvg_ids - set(matched.keys()):
        key = tvg_names_norm.get(tid, "")
        if key and key in name_index:
            matched[tid] = name_index[key]

    name_match_count = len(matched) - id_match_count

    print(f"3) Coincidencias por tvg-id: {id_match_count}")
    print(f"   Coincidencias adicionales por nombre: {name_match_count}")
    print(f"   Total con guía encontrada: {len(matched)} / {len(tvg_ids)}")

    unmatched = sorted(tvg_ids - set(matched.keys()))
    if unmatched:
        print(f"   Sin coincidencia ({len(unmatched)}), primeros 30:")
        for u in unmatched[:30]:
            print(f"     - {u} (tvg-name: {tvg_map.get(u, '')!r})")

    # --- Construir el XML de salida ---
    new_root = ET.Element("tv", {"generator-info-name": "auto-epg-filter"})
    for tid, (src_id, ch) in matched.items():
        ch.set("id", tid)  # reescribe con el tvg-id exacto del m3u
        new_root.append(ch)

    prog_count = 0
    for tid, (src_id, ch) in matched.items():
        for pr in programmes_by_srcid.get(src_id.lower(), []):
            pr.set("channel", tid)
            new_root.append(pr)
            prog_count += 1

    out_xml = ET.tostring(new_root, encoding="utf-8", xml_declaration=True)
    with gzip.open(OUTPUT_PATH, "wb") as f:
        f.write(out_xml)

    print(f"4) Guardado {OUTPUT_PATH}: {len(matched)} canales, {prog_count} programas.")


if __name__ == "__main__":
    main()
