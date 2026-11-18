# Changelog · Registro de cambios

Todos los cambios importantes de TuxEnc se anotan aquí. El formato sigue [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/) y las versiones siguen el [versionado semántico](https://semver.org/lang/es/).

All notable changes to TuxEnc are listed here (Spanish first, English below each version).

## [Sin publicar] · Unreleased

## [1.1.0] - 2026-11-18

### Añadido
- **TheTVDB como cuarto buscador.** Suele ser el único con los títulos de capítulo traducidos de muchas series (por ejemplo, *Foyle's War*). Se usa para buscar series y, sobre todo, para completar en tu idioma los títulos que TMDB solo tiene en inglés. Admite también enlaces de TheTVDB en «Identificar…».
- **Buscadores sin configurar nada:** el AppImage trae sus propias claves de TMDB y TheTVDB. IMDb (OMDb) sigue siendo opcional con tu propia clave gratuita.
- Aviso en el primer arranque con los buscadores que ya funcionan.
- Créditos de los datos (TMDB, TheTVDB, TVmaze, OMDb) en Preferencias → Acerca de, en «Identificar…» y en el README.

### Cambiado
- **Un único botón «⚙ Ajustes ▾»** sustituye a «⚙ Ajustes» y «☰». Su menú tiene tres entradas: 🎞 Conversión (el panel lateral de siempre), 🏷 Renombrado y buscadores, y 🔧 Preferencias.
- **Sección «Buscadores»:** muestra el estado de cada buscador (clave integrada, tu clave o sin clave) y permite poner tus propias claves y, en TheTVDB, un PIN de suscriptor. Tu clave siempre manda sobre la integrada.

### Added / Changed (English)
- **TheTVDB** as a fourth search service, mainly to get localized episode titles; TheTVDB links accepted in «Identify…».
- Built-in TMDB and TheTVDB keys: nothing to set up. IMDb (OMDb) stays optional with your own free key.
- First-run notice, and data credits (TMDB, TheTVDB, TVmaze, OMDb).
- Single **⚙ Settings ▾** menu (Conversion · Renaming and search services · Preferences), replacing ⚙ and ☰.
- **Search services** section showing each service's status, with optional own keys (and a TheTVDB subscriber PIN).

## [1.0.2] - 2026-11-18

### Mejorado
- **Audio sin recomprimir cuando ya ocupa poco.** Si una pista ya está en el formato elegido (por ejemplo AAC), con los mismos canales y un bitrate igual o menor que el pedido, se copia tal cual en vez de recomprimirla. Así no crece ni pierde calidad. Es una casilla nueva en ⚙ Ajustes → Audio, activada por defecto. Era la causa de que algunos capítulos salieran algo más grandes que el original: su audio AAC de menos de 160 kbps se recomprimía a 160 kbps.
- **Bitrate real del audio en MKV sin etiquetas `BPS`:** se mide en los dos primeros minutos del archivo. Lo usan la copia del audio y la decisión de copiar el vídeo, que antes suponía 128 kbps por pista estéreo.

### Improved
- Audio tracks already in the chosen format, with the same channels and an equal or lower bitrate, are copied instead of re-encoded (new option in Settings → Audio, on by default). This made some episodes slightly bigger than the original.
- Audio bitrate is measured in MKV files without `BPS` tags, for both the audio and the video copy decisions.

## [1.0.1] - 2026-11-18

### Corregido
- El porcentaje, la barra y el tiempo restante se quedaban congelados durante muchos minutos y de repente saltaban (por ejemplo, del 3 % al 95 %), aunque la conversión seguía avanzando. Pasaba con vídeos que tienen pistas de subtítulos con pocos textos: FFmpeg informa del tiempo de la pista más atrasada. Ahora el avance se calcula también con los fotogramas de vídeo ya convertidos.

### Fixed
- Progress, bar and remaining time froze for long periods and then jumped (e.g. 3 % → 95 %) while the conversion kept going. It happened with videos that have sparse subtitle tracks (FFmpeg reports the time of the most delayed track). Progress now also uses the number of video frames already written.

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
[1.1.0]: #
[1.0.2]: #
[1.0.1]: #
[1.0.0]: #
