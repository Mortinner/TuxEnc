# Changelog · Registro de cambios

Todos los cambios importantes de TuxEnc se anotan aquí. El formato sigue [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/) y las versiones siguen el [versionado semántico](https://semver.org/lang/es/).

All notable changes to TuxEnc are listed here (Spanish first, English below each version).

## [Sin publicar] · Unreleased

## [1.3.2] - 2026-11-21

### Cambiado
- **«Acerca de» más claro y escueto:** enlace a github.com/Mortinner, copyright, «Verificado por GitHub» (enlazado a la Release, con su `SHA256SUMS` y su certificado de procedencia) y la licencia. Se añade un apartado **Sistema** con el entorno de ejecución (AppImage integrado, sin integrar o código fuente), el commit y la fecha de compilación, las versiones de Python, Qt y FFmpeg y la aceleración por hardware que incluye el FFmpeg empaquetado. Una compilación local lo indica («Compilación local, no oficial»).

### English
- Changed: a shorter About tab with copyright, «Verified by GitHub» (linked to the release), the license, and a System section (runtime, commit, build date, Python, Qt and FFmpeg versions, hardware acceleration included in the bundled FFmpeg).

## [1.3.1] - 2026-11-20

### Cambiado
- **Busca actualizaciones cada vez que se abre**, no una vez al día. Es una sola consulta a GitHub y no retrasa nada. Se puede desactivar en ☰ → Preferencias → Actualizaciones.
- **El botón del aviso de versión nueva dice «Actualizar…»** en lugar de «Ver novedades». Abre la misma ventana, con las novedades plegadas y Actualizar / Saltar esta versión / Ahora no.

### Corregido
- **El título de la ventana ya no repite el nombre** («TuxEnc 1.3.0 — TuxEnc»). El escritorio añadía « — TuxEnc» a cualquier título que no acabara en «TuxEnc».

### Mejorado
- **Renombrar dentro del NAS, todavía más rápido.** Linux no deja renombrar a la vez dos archivos de la misma carpeta, y con los capítulos en orden los hilos se esperaban unos a otros dentro de cada temporada. Ahora los movimientos alternan carpetas (T01, T02, T03…). En la prueba con el bloqueo por carpeta simulado, 777 capítulos pasan de 11 s a 4 s.

### English
- Changed: TuxEnc checks for updates every time it starts (it can be turned off in Preferences). The new-version notice button now says «Update…».
- Fixed: the window title no longer repeats the name («TuxEnc 1.3.0 — TuxEnc»).
- Improved: renames on a NAS alternate folders so parallel moves don't wait for each other (Linux allows one rename at a time per folder).

## [1.3.0] - 2026-11-20

### Corregido
- **Capítulos numerados solo con un número** («Dinosaucers 01.mp4» … «Dinosaucers 71.mp4»): antes solo se identificaba el primero y «Usar esta misma serie» no se aplicaba a ninguno, porque cada archivo parecía una serie distinta («Dinosaucers 02», «Dinosaucers 03»…). Ahora se reconocen como capítulos cuando está claro que es una serie: números con cero delante («01») o que pasan de una cifra a dos, con varios archivos del mismo título en la carpeta o una carpeta con su nombre. Las películas con número («Rocky 2», «Ocean's 11», «2012») siguen siendo películas.
- **Numeración absoluta:** si el número pasa de los capítulos de la primera temporada, se convierte a su temporada y capítulo con la lista del buscador (en una serie de 65 + 6 capítulos, el «66» es el S02E01).
- **El botón principal espera a que termine el análisis y la identificación.** Antes se podía pulsar en cuanto había un vídeo listo y solo se llevaba esos; ahora espera, y al pasar el ratón explica por qué («Espera un momento: aún se están identificando 12 vídeo(s)»). La barra de estado dice también «Identificando…».
- **La etiqueta «Solo renombrar» ya no se descoloca** mientras se identifican los vídeos. Salía un instante como un rectángulo encima del título, fila tras fila, porque cada fila crecía al identificarse. Ahora la fila tiene desde el principio el alto que tendrá.

### Mejorado
- **Renombrar en el NAS es mucho más rápido.** Antes se preguntaba al disco unas 6 veces por archivo, cada vez con la espera de la red; ahora se lista cada carpeta una vez, las carpetas de destino se crean una sola vez y los archivos se mueven varios a la vez. En la prueba con 10 ms de latencia por consulta, 240 capítulos pasan de 15 s a 1 s. Se mantiene todo lo demás: si algo falla no se cambia nada, nunca se pisa un archivo y se puede deshacer. Las copias entre discos siguen yendo de una en una.
- **«Usar esta misma serie»** dice a cuántos capítulos se aplicará («para los otros 70 capítulos de «Dinosaucers»»).
- **`renombrado.log` anota también el análisis y la identificación de cada tanda:** cuántos archivos, cuántos no se pudieron leer, cuánto tardó cada fase y cuántos quedaron identificados, dudosos o sin encontrar.

### Añadido
- **«Acerca de» muestra de dónde sale esta versión:** «Compilado por GitHub Actions» con el commit y la compilación enlazados, la Release con su `SHA256SUMS` y su certificado de procedencia, y cómo comprobar una descarga. Una compilación local lo dice («Compilación local, no oficial»).
- **El título de la ventana muestra la versión** («TuxEnc 1.3.0»), también mientras convierte («45% · TuxEnc 1.3.0»).

### English
- Fixed: episodes numbered with just a number («Dinosaucers 01.mp4») are now recognized as episodes when the folder makes it clear it is a show; numbered movies («Rocky 2», «Ocean's 11», «2012») stay movies. Absolute numbers beyond season 1 are converted to season and episode.
- Fixed: the main button waits until analysis and identification finish, with a tooltip explaining why. The «Rename only» tag no longer flickers as a rectangle while videos are identified.
- Improved: renaming on a NAS is much faster (one listing per folder, folders created once, several moves at a time; 240 episodes from 15 s to 1 s with 10 ms simulated latency), still all-or-nothing and undoable. «Use this same show» shows how many episodes it applies to. `renombrado.log` also records the analysis and identification of each batch.
- Added: About shows where this build comes from (GitHub Actions commit and run, the release with its `SHA256SUMS` and provenance attestation, how to verify a download) or says it is a local build. The window title shows the version.

## [1.2.7] - 2026-11-20

### Añadido
- **TuxEnc se actualiza desde la propia app.** Al abrirse (como mucho una vez al día y sin retrasar nada) mira si hay una versión nueva publicada en GitHub. Si la hay, lo avisa en la barra de avisos con **«Ver novedades»**: ahí están las novedades de cada versión nueva y los botones **Actualizar**, **Saltar esta versión** y **Ahora no**.
- **La descarga se comprueba antes de instalar nada:** solo se descarga de GitHub y por HTTPS, el zip tiene que coincidir con la suma SHA-256 publicada en su Release (`SHA256SUMS`) y dentro tiene que estar el AppImage de esa versión. Si algo no cuadra, no se toca nada y se explica qué ha pasado.
- **Se instala sin cortar lo que estás haciendo:** la versión nueva se pone en su sitio y se usa al reiniciar. Puedes reiniciar ahora, **al terminar la cola** o más tarde, y los vídeos en espera vuelven a la cola solos. Al abrirse por primera vez, la versión nueva actualiza el menú y los iconos.
- **Volver a la versión anterior:** la versión que se sustituye se guarda, y en **☰ → Preferencias → Actualizaciones** hay un botón para volver a ella. La que se deja ya no se vuelve a ofrecer; las siguientes, sí.
- **☰ → Preferencias → Actualizaciones:** activar o desactivar la comprobación al arrancar, **«Buscar ahora»** y el estado de la última comprobación. Todo queda anotado en `actualizaciones.log`.
- La actualización automática funciona en la copia integrada en el sistema (la que abre el menú de aplicaciones). Un AppImage suelto, sin integrar, solo avisa y abre la página de descarga.

### English
- Added: TuxEnc updates itself. At startup (at most once a day) it checks GitHub for a new release and shows it in the notice bar with «What's new», Update, Skip this version and Not now.
- The download is verified before anything is installed: GitHub over HTTPS only, the zip must match the SHA-256 published in the release's `SHA256SUMS`, and it must contain that version's AppImage. Otherwise nothing is touched.
- The new version is put in place and used after a restart (now, when the queue finishes, or later); waiting videos are re-queued. The previous version is kept and you can go back to it from ☰ → Preferences → Updates, where you can also turn off the startup check or check now. Everything is logged to `actualizaciones.log`.

## [1.2.6] - 2026-11-20

### Corregido
- **Renombrar muchos vídeos tardaba minutos sin mostrar nada** (unos 8 minutos con 279 capítulos de un NAS, y todas las filas en «Preparando…» hasta el final). Antes de mover cada archivo se volvía a analizar el vídeo para saber su resolución, uno detrás de otro y leyendo además los primeros minutos de cada MKV. La resolución ya se conocía desde que se añadió: ahora se usa esa y el paso de renombrar es solo mover los archivos (229 capítulos en 0,1 s en la prueba).

### Añadido
- **Avance del renombrado archivo a archivo:** cada fila pasa a «Renombrando…» en cuanto su archivo está en su sitio, y la barra de estado cuenta «Renombrando 37 de 279».
- **Aviso cuando el destino está en otro disco o montaje** (por ejemplo, otro recurso compartido del NAS): ahí no se puede renombrar sin más y cada archivo se copia entero. La fila lo indica («⇢ Copiando a otro disco…») y la barra de estado avisa de que irá más lento.
- **`renombrado.log` anota cada lote:** cuántos vídeos, el destino, cuántos archivos se movieron, cuántos hubo que copiar entre discos y cuánto tardó cada fase.

### English
- Fixed: renaming many videos took minutes with no feedback (every video was probed again before being moved). The known resolution is now reused: renaming is just moving the files (229 episodes in 0.1 s in testing).
- Added: per-file progress for rename batches («Renaming…» per row, «Renaming 37 of 279» in the status bar); a notice when the destination is on another drive or mount and files must be copied; `renombrado.log` records each batch with timings.

## [1.2.5] - 2026-11-20

### Corregido
- **Identificar muchos capítulos de una misma carpeta seguía tardando minutos** (unos 5 minutos con 229 capítulos de un NAS). Para buscar los subtítulos de cada vídeo se recorría la carpeta entera preguntando al disco por cada archivo: con 229 capítulos eran unas 52.000 consultas, cada una con la latencia de la red. Ahora cada carpeta se lista una sola vez (se reutiliza 30 s) y solo se mira el tipo de los archivos que son subtítulos. En la simulación, de 273 s a 0,03 s, con los mismos subtítulos encontrados.
- **Al añadir vídeos ya no se lee el principio de cada archivo.** En los MKV que no declaran el bitrate del audio, se leían los dos primeros minutos para medirlo nada más añadirlos, aunque solo se fueran a renombrar. Ahora al añadir solo se lee la cabecera y esa medida se hace al empezar a convertir cada vídeo (sigue sirviendo para decidir si copiar audio y vídeo sin recomprimir).

### English
- Fixed: identifying many episodes in one folder still took minutes (about 5 minutes for 229 episodes on a NAS). The subtitle search listed the whole folder and queried the disk for every file, for every video (~52,000 network round trips). Each folder is now listed once (reused for 30 s) and only subtitle files are checked.
- Adding videos no longer reads the start of each file: the audio bitrate of MKVs without BPS tags is now measured when the video starts converting, not when it is added.

## [1.2.4] - 2026-11-20

### Corregido
- **Al añadir muchos vídeos de golpe (por ejemplo, una serie entera de 229 capítulos), TuxEnc se quedaba bloqueado durante mucho tiempo** y gastaba varios GB de memoria. Con cada vídeo añadido se rehacía la lista entera y se volvían a aplicar los estilos de todas las filas, un trabajo que crece con el cuadrado del número de vídeos y que va por un único hilo. Ahora las filas nuevas se insertan en su sitio y los estilos solo se aplican si cambian. Con 229 vídeos, la lista está lista en unos segundos y usa unos 200 MB, cuando antes agotaba la memoria.
- **«Usar esta misma serie para los demás capítulos» solo cambiaba los capítulos sin identificar.** Si los demás ya se habían identificado solos (con la serie o el proveedor equivocados), seguían igual y había que corregirlos uno a uno. Ahora se aplica a todos los capítulos de esa serie que no han empezado, estén identificados o no, y cada uno conserva su número de capítulo. Cuentan los que tienen el mismo nombre de serie en el archivo y los que se identificaron con la serie que tenía ese capítulo antes de corregirlo. Solo se respetan los capítulos a los que se eligió un episodio a mano.

### English
- Fixed: adding many videos at once (e.g. a 229-episode show) froze TuxEnc for a long time and used several GB of RAM. The list was rebuilt and restyled on every added video (quadratic work on the GUI thread). New rows are now inserted in place and styles are only applied when they change: 229 videos load in seconds using about 200 MB.
- Fixed: «Use this same show for the other episodes» only changed unidentified episodes. It now applies to every not-started episode of that show, identified or not (same show name in the file, or identified as the show this episode had before the correction). Episodes picked by hand are kept.

## [1.2.3] - 2026-11-19

### Corregido
- **Con la cola en marcha, apagar «Convertir» y añadir vídeos para renombrar hacía que se convirtieran igualmente.** La cola miraba los interruptores al empezar cada vídeo y no los de cuando se añadió. Ahora cada vídeo guarda su tarea, sus ajustes y su destino al confirmarlo, y lo que es solo para renombrar nunca entra en la conversión.
- Reintentar un vídeo ya no le hace perder los ajustes con los que se añadió.
- En inglés, el botón «Audio & subtitles…» se veía como «Audio _subtitles…».

### Cambiado
- **El botón Iniciar confirma lo nuevo.** Con la cola en marcha queda inhabilitado; si añades vídeos, pasa a **«＋ Añadir (n)»** o, con solo «Renombrar», a **«🏷 Renombrar (n)»**. Mientras no lo pulses, esos vídeos («Nuevo · sin confirmar») siguen a los interruptores, al preset y a «Guardar en», y puedes corregir su identificación. Al pulsarlo:
  - Las conversiones se suman a la cola y esperan su turno, sin pasar del número de «Simultáneos».
  - Lo que es solo para renombrar no pasa por la cola: se renombra en ese momento, aunque la cola esté convirtiendo. Se puede deshacer.
- Una vez confirmado, un vídeo ya no cambia aunque toques el preset o los interruptores.
- **Detener:** lo que aún no había empezado vuelve a quedar pendiente y sigue de nuevo a los ajustes.
- **«Simultáneos» solo se puede cambiar con la cola parada.**
- Cada fila lleva una etiqueta con su tarea: «Convertir + renombrar», «Solo convertir» o «Solo renombrar».

### English
- Fixed: with the queue running, turning «Convert» off and adding videos to rename still converted them. Each video now keeps the task, settings and destination it was confirmed with.
- With the queue running, the Start button turns into «＋ Add (n)» (or «🏷 Rename (n)» with only «Rename») when you add videos; until pressed they follow the current switches and preset. Conversions join the queue without exceeding «At once»; rename-only runs right away. «Stop» returns not-started videos to pending. «At once» can only be changed with the queue stopped. Task tag on each row.
- Fixed: retrying no longer drops a video's settings; «Audio & subtitles…» showed as «Audio _subtitles…».

## [1.2.2] - 2026-11-18

### Corregido
- **Elegir un capítulo a mano en «Identificar…» no cambiaba nada** si el nombre del archivo ya traía un título y el buscador lo daba en inglés: la opción «conservar el título del archivo» volvía a poner el del archivo. Ahora, cuando eliges el capítulo en la lista, manda tu elección. La opción sigue aplicándose a la identificación automática y a los capítulos que reciben la serie con «Usar esta misma serie…».

### English
- Fixed: picking an episode by hand in «Identify…» was overridden by the «keep the file's title» option.

## [1.2.1] - 2026-11-18

### Corregido
- **TheTVDB: todas las temporadas salían con los títulos de capítulo de la última** (por ejemplo, el S01E01 y el S02E01 de *Foyle's War* con el mismo título). La consulta de títulos traducidos de TheTVDB devuelve la serie entera, aunque se le pida una temporada, y los capítulos se mezclaban por número. Ahora se filtra cada temporada en TuxEnc y las traducciones se emparejan por el identificador del capítulo, porque la lista traducida de TheTVDB puede numerar las temporadas de otra forma. También desaparecen los capítulos fantasma («sin título todavía») que salían de los especiales.
- **El registro del renombrado no se escribía nunca.** Ahora se guarda en `~/.cache/tuxenc/logs/renombrado.log`, junto a los demás registros (☰ → Preferencias → Registros), y anota qué se buscó y de qué buscador sale cada título.

### Cambiado
- La fila indica de qué buscador sale el título del capítulo cuando no es el de la serie (por ejemplo, «Cincuenta naves (título de TheTVDB)»).
- «Acerca de» y README: «Built with Claude, Anthropic».

### English
- Fixed: with TheTVDB every season got the episode titles of the last season; translations are now matched by episode id.
- Fixed: the renaming log was never written; it is now `~/.cache/tuxenc/logs/renombrado.log`.
- The row shows which service the episode title came from when it differs; About: «Built with Claude, Anthropic».

## [1.2.0] - 2026-11-18

### Cambiado
- **Un solo menú ☰** arriba a la derecha (sustituye a «⚙ Ajustes» y a «⋯»), con seis entradas: Conversión, Renombrado, Buscadores, Presets, Preferencias y Acerca de.
- **Ventana única de ajustes** con una pestaña para cada una. Todo se puede configurar siempre, estén activados o no la conversión y el renombrado. Los ajustes de conversión dejan el panel lateral y pasan a su pestaña; la cola ocupa ahora todo el ancho. Pulsar la línea de resumen abre la pestaña Conversión.
- **Presets** en su propia pestaña: usar, guardar los ajustes actuales, eliminar los tuyos, importar de HandBrake y exportar. El desplegable de presets sigue en la ventana principal.
- **Interruptores deslizantes** para activar Convertir y Renombrar, en lugar de botones.

### Añadido
- «Acerca de» con autor (Mortinner), contacto, licencia y créditos de los datos.

### Corregido
- Al cerrar los ajustes podía preguntar por un reinicio de idioma aunque no se hubiera cambiado (con el idioma en «Automático»).

### English
- Single **☰** menu and one settings window with tabs (Conversion, Renaming, Search services, Presets, Preferences, About), always configurable. The side panel is gone; the queue uses the full width.
- Presets tab; on/off switches for Convert and Rename; About with author and contact.
- Fixed a spurious language restart question.

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
[1.2.2]: #
[1.2.1]: #
[1.2.0]: #
[1.1.0]: #
[1.0.2]: #
[1.0.1]: #
[1.0.0]: #
