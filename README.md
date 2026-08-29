# Auto-EPG para tu m3u

Genera automáticamente un `epg.xml.gz` filtrado (solo tus canales) a partir de
una fuente EPG pública de España, y lo mantiene actualizado con GitHub Actions.

## Instalación (5 minutos)

1. **Crea un repositorio nuevo en GitHub** (puede ser público, ej. `mi-epg`).
   No subas tu m3u al repo — solo estos dos archivos:
   - `.github/workflows/update-epg.yml`
   - `scripts/build_epg.py`

2. **Configura el secreto con la URL de tu m3u** (importante: tu m3u tiene
   credenciales en la URL, por eso va como *secret*, nunca como texto plano
   en el repo):
   - Ve a `Settings` → `Secrets and variables` → `Actions` → `New repository secret`
   - Nombre: `M3U_URL`
   - Valor: la URL completa de tu m3u

3. **Habilita permisos de escritura para Actions**:
   - `Settings` → `Actions` → `General` → `Workflow permissions`
   - Marca `Read and write permissions` → Guardar

4. **Ejecuta el workflow por primera vez**:
   - Pestaña `Actions` → `Actualizar EPG` → `Run workflow`
   - Revisa el log: te dirá cuántos de tus `tvg-id` encontraron coincidencia
     en el EPG (verás una lista de los que no coincidieron, por si quieres
     ajustarlos más adelante).

5. **URL final para tu reproductor IPTV** (ponla en el campo "EPG URL" /
   "XMLTV URL" de tu app, ej. TiviMate, IPTV Smarters, GSE, Kodi):

   ```
   https://raw.githubusercontent.com/TU_USUARIO/TU_REPO/main/epg.xml.gz
   ```

   (sustituye `TU_USUARIO/TU_REPO` por los tuyos)

## Cómo funciona

- El workflow corre cada 6 horas (`cron: "0 */6 * * *"`, editable en el yml).
- Descarga tu m3u desde `M3U_URL`, extrae todos los `tvg-id` únicos.
- Descarga `epg_ripper_ES1.xml.gz` (fuente pública, ~124 canales de España).
- Se queda solo con los `<channel>` y `<programme>` que coinciden con tus
  `tvg-id`, y publica `epg.xml.gz` en la raíz del repo.
- Solo hace commit si hubo cambios reales.

## Si algunos canales no tienen coincidencia

Es normal: solo cubre canales de TDT/pago España que estén en esa fuente
(AMC, MTV, BBC, Eurosport, canales internacionales, etc. pueden no estar).
Puedes:
- Añadir más URLs de fuentes a la lista `EPG_SOURCE_URLS` en
  `scripts/build_epg.py` (por ejemplo otras del catálogo
  [epgshare01.online](https://epgshare01.online/epgshare01/)).
- O revisar/corregir el `tvg-id` de esos canales en tu m3u para que coincida
  con el id real usado en la fuente EPG.
