# Changelog · Registro de cambios

Todos los cambios importantes de TuxEnc se anotan aquí. El formato sigue [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/) y las versiones siguen el [versionado semántico](https://semver.org/lang/es/).

All notable changes to TuxEnc are listed here (Spanish first, English below each version).

## [Sin publicar] · Unreleased

## [1.0.0] - 2026-11-17

Primera versión pública.

### Conversión
- Convierte a H.264, H.265, AV1 y VP9, en MKV, MP4 o WebM, con FFmpeg 8.1 incluido.
- **Varios vídeos a la vez**: el número se elige a mano o en *Auto* (según el procesador). Opción de prioridad baja para seguir usando el equipo.
- Aceleración por GPU: NVIDIA NVENC, AMD/Intel VAAPI e Intel Quick Sync. Solo se ofrecen las de la gráfica que tienes.
- Control de calidad: calidad constante, bitrate medio (con 2 pasadas opcionales) o bitrate constante.
- Si el original ya tiene menos bitrate que el pedido, el vídeo se copia sin recomprimir.
- Resolución máxima, opción «Permitir ampliar», recorte automático de bandas negras, desentrelazado, reducción de ruido y fotogramas por segundo.
- Selección automática de pistas de audio y subtítulos según tus idiomas, con ajuste por vídeo.
- Presets propios, importación de presets de HandBrake (`.json`) y exportación.
- Pausar, reanudar, cancelar y reintentar. Menú «🧹 Limpiar»: quitar terminados, los que no han empezado o vaciar la cola.
- Al terminar: avisar, cerrar TuxEnc, suspender o apagar (con cuenta atrás cancelable).
- Si el convertido ocupa más que el original, el original nunca se borra solo: TuxEnc pregunta con cuál te quedas.

### Renombrado y biblioteca
- Identifica series y películas en TMDB, TVmaze e IMDb (OMDb) y las renombra con formatos configurables, como `{series}`, `{season}`, `{episode}`, `{title}`, `{year}`, `{resolution}` o `{initial}`.
- Se puede solo convertir, solo renombrar (con deshacer) o las dos cosas: el vídeo convertido nace con su nombre y en su carpeta.
- Ventana «Identificar…»: elegir la serie o película y luego la temporada y el capítulo con un clic, aplicarlo a todos los capítulos de la serie y buscar pegando un enlace o código de IMDb, TMDB o TVmaze.
- Títulos de capítulo en español: si no están en español de España se prueba el de Latinoamérica. Si solo existen en inglés, se conserva el que ya trae el nombre del archivo.
- Resolución automática en el nombre (`[2160p]`, `[1080p]`, `[720p]`, `[480p]`), medida en el vídeo resultante.
- Destino «📚 Biblioteca» con carpetas separadas para series y películas, subtítulos externos y metadatos dentro del archivo.

### Instalación
- Un solo AppImage, sin dependencias.
- Integración opcional en el menú y el escritorio, con desinstalación completa desde el menú.
- Actualización con un doble clic sobre la versión nueva, aunque TuxEnc esté abierto: se cierra, se actualiza y se vuelve a abrir conservando la cola.
- Interfaz en español e inglés.

---

### English

First public release.

- **Transcoding:** H.264, H.265, AV1 and VP9 (MKV, MP4, WebM) with FFmpeg 8.1 bundled.
  - Several videos at once, with low-priority mode.
  - GPU acceleration: NVENC, VAAPI and QSV, only for the GPUs present.
  - Constant quality, average bitrate (optional 2-pass) or constant bitrate.
  - Copies the video without re-encoding when the source bitrate is already lower than requested.
  - Filters: max resolution, autocrop, deinterlace, denoise and fps.
  - Automatic audio and subtitle selection by language.
  - Custom presets and HandBrake preset import.
  - Pause, resume, cancel, retry and a «Clear» menu.
  - End actions: notify, quit, suspend or shut down.
  - The original is never deleted automatically when the result is bigger.
- **Renaming and library:** TMDB, TVmaze and IMDb (OMDb) identification with configurable formats.
  - Convert, rename (with undo) or both.
  - «Identify…» window with one-click season and episode selection; search also accepts an IMDb, TMDB or TVmaze link or code.
  - Spanish episode titles: Latin-American Spanish fallback, and the file's own title is kept when only English is available.
  - Automatic `{resolution}`, library destination, external subtitles and metadata.
- **Installation:** a single AppImage, with optional menu and desktop integration and full uninstall.
  - Updating works even while TuxEnc is open; the queue is kept.
  - Spanish and English UI.

[Sin publicar]: #
[1.0.0]: #
