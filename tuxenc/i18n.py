"""Traducciones de la interfaz (español / inglés)."""

from __future__ import annotations

import locale
import os

_lang = "es"

# clave: (español, inglés)
STRINGS: dict[str, tuple[str, str]] = {
    # generales
    "app_tagline": ("Transcodificador de vídeo · varios a la vez", "Video transcoder · several at once"),
    "add": ("Añadir", "Add"),
    "add_files": ("Añadir vídeos…", "Add videos…"),
    "add_folder": ("Añadir carpeta…", "Add folder…"),
    "settings": ("Ajustes", "Settings"),
    "preferences": ("Preferencias", "Preferences"),
    "start": ("Iniciar", "Start"),
    "pause": ("Pausar", "Pause"),
    "resume": ("Reanudar", "Resume"),
    "stop": ("Detener", "Stop"),
    "clear_done": ("Quitar de la lista los vídeos terminados", "Remove finished videos from the list"),
    "clear_short": ('Quitar terminados', 'Clear finished'),
    "parallel_locked": ("Se puede cambiar cuando la cola esté parada. Lo que añadas ahora espera su turno.",
                        "It can be changed when the queue is stopped. What you add now waits its turn."),
    "add_n": ("Añadir ({n})", "Add ({n})"),
    "rename_n": ("Renombrar ({n})", "Rename ({n})"),
    "add_n_tip": ("Los vídeos nuevos se harán con lo que esté elegido ahora (interruptores, preset y "
                  "destino). Hasta que lo pulses puedes cambiarlo o corregir la identificación.",
                  "The new videos will use what is chosen now (switches, preset and destination). "
                  "Until you press it you can change it or fix the identification."),
    "status_pending": (" · {n} nuevo(s): pulsa «Añadir»", " · {n} new: press «Add»"),
    "status_pending_ren": (" · {n} nuevo(s): pulsa «Renombrar»", " · {n} new: press «Rename»"),
    "st_new": ("Nuevo · sin confirmar", "New · not confirmed"),
    "task_both": ("Convertir + renombrar", "Convert + rename"),
    "task_conv": ("Solo convertir", "Convert only"),
    "task_ren": ("Solo renombrar", "Rename only"),
    "task_none": ("Sin tarea", "No task"),
    "clear_menu": ("Limpiar", "Clear"),
    "clear_menu_tip": ("Quitar vídeos de la lista (no se borra ningún archivo)",
                       "Remove videos from the list (no file is deleted)"),
    "clear_finished_n": ("Quitar terminados ({n})", "Remove finished ({n})"),
    "clear_pending_n": ("Quitar los que no han empezado ({n})", "Remove those not started ({n})"),
    "clear_all_n": ("Vaciar la cola ({n})", "Empty the queue ({n})"),
    "clear_all_running_q": ("Hay {n} vídeo(s) convirtiéndose. Si vacías la cola se cancelarán "
                            "y se perderá lo que llevan hecho (los originales no se tocan).\n\n"
                            "¿Vaciar la cola?",
                            "{n} video(s) are being converted. Emptying the queue will cancel them "
                            "and their progress will be lost (originals are not touched).\n\n"
                            "Empty the queue?"),
    "close": ("Cerrar", "Close"),
    "cancel": ("Cancelar", "Cancel"),
    "accept": ("Aceptar", "OK"),
    "yes": ("Sí", "Yes"),
    "no": ("No", "No"),
    "modified": ("modificado", "modified"),
    "drop_title": ("Arrastra aquí tus vídeos", "Drop your videos here"),
    "drop_sub": ("o carpetas enteras · también puedes usar los botones",
                 "or whole folders · you can also use the buttons"),
    "video_files": ("Vídeos", "Videos"),
    "all_files": ("Todos los archivos", "All files"),
    "choose_folder": ("Elegir carpeta", "Choose folder"),
    "analyzing": ("Analizando {n} archivo(s)…", "Analyzing {n} file(s)…"),
    "not_video": ("No se ha podido leer como vídeo:\n{names}", "Could not be read as video:\n{names}"),
    "already_queued": ("Ya estaba en la cola", "Already in the queue"),
    "no_videos_found": ("No se han encontrado vídeos en esa carpeta.", "No videos found in that folder."),

    # modos y renombrado
    "mode_convert": ("Convertir", "Convert"),
    "mode_rename": ("Renombrar", "Rename"),
    "mode_convert_tip": ("Transcodificar los vídeos con los ajustes del preset.",
                         "Transcode the videos with the preset settings."),
    "mode_rename_tip": ("Identificar cada vídeo en TMDB / TVmaze / IMDb y darle su nombre (y carpeta) "
                        "según los formatos de ☰ Preferencias → Renombrado.",
                        "Identify each video on TMDB / TVmaze / IMDb and give it its name (and folder) "
                        "using the formats in ☰ Preferences → Renaming."),
    "need_a_mode": ("Activa «Convertir», «Renombrar» o los dos.", "Turn on “Convert”, “Rename” or both."),
    "undo_rename": ('Deshacer renombrado', 'Undo rename'),
    "undo_rename_tip": ("Deshacer el último renombrado (los archivos vuelven a su nombre y carpeta)",
                        "Undo the last rename (files go back to their name and folder)"),
    "undo_done": ("Renombrado deshecho: {n} archivo(s) han vuelto a su sitio.",
                  "Rename undone: {n} file(s) are back in place."),
    "undo_fail": ("No se pudo deshacer:\n{err}", "Could not undo:\n{err}"),
    "id_pending": ("🔎 Identificando…", "🔎 Identifying…"),
    "id_ambiguous": ('⚠ No está claro qué es: pulsa «Identificar…»', '⚠ Not sure what this is: click “Identify…”'),
    "id_none": ('⚠ No se ha encontrado: pulsa «Identificar…» para buscarlo', '⚠ Not found: click “Identify…” to search for it'),
    "id_error": ("⚠ {err}", "⚠ {err}"),
    "match_btn": ('Identificar…', 'Identify…'),
    "match_tip": ('Elegir qué serie o película es y, en las series, qué capítulo', 'Choose which show or movie it is and, for shows, which episode'),
    "match_title": ('Identificar «{name}»', 'Identify “{name}”'),
    "match_guess": ('Lo que se ha entendido del nombre del archivo: {guess}', 'What was understood from the file name: {guess}'),
    "id_episode": ("⚠ {show}: falta saber qué capítulo es. Pulsa «Identificar…»",
                   "⚠ {show}: which episode is it? Click “Identify…”"),
    "match_step1": ("1 · ¿Qué serie o película es?", "1 · Which show or movie is it?"),
    "match_step2": ("2 · ¿Qué capítulo?", "2 · Which episode?"),
    "match_query_ph": ("Título, o pega un enlace de IMDb, TMDB o TVmaze",
                       "Title, or paste an IMDb, TMDB or TVmaze link"),
    "match_query_tip": ("Si no aparece por su nombre, búscala en IMDb (o TMDB, TVmaze), copia la dirección "
                        "de la página y pégala aquí. También vale el código de IMDb (tt1234567).",
                        "If it doesn't show up by name, look it up on IMDb (or TMDB, TVmaze), copy the page "
                        "address and paste it here. An IMDb code (tt1234567) works too."),
    "match_any_year": ("Cualquier año", "Any year"),
    "match_year_tip": ("Año de estreno (opcional, ayuda a distinguir remakes)",
                       "Release year (optional, helps tell remakes apart)"),
    "match_season": ("Temporada", "Season"),
    "match_season_n": ("Temporada {n}", "Season {n}"),
    "match_specials": ("Especiales", "Specials"),
    "match_loading": ("Cargando…", "Loading…"),
    "match_no_seasons": ("No se pudieron cargar las temporadas", "Could not load the seasons"),
    "match_no_eps": ("Esta temporada no tiene capítulos publicados todavía.",
                     "This season has no published episodes yet."),
    "match_no_title": ("(sin título todavía)", "(no title yet)"),
    "match_eps_hint": ("Haz clic en el capítulo. Para un capítulo doble, selecciona dos seguidos "
                       "con Mayús o Ctrl.",
                       "Click the episode. For a double episode, select two in a row with Shift or Ctrl."),
    "match_manual": ("No está en la lista: escribirlo a mano", "Not in the list: type it by hand"),
    "match_s_prefix": ("Temporada ", "Season "),
    "match_e_prefix": ("Capítulo ", "Episode "),
    "match_movie_note": ("Es una película: no hay capítulos que elegir.",
                         "It's a movie: there are no episodes to pick."),
    "match_pick_first": ("Elige a la izquierda qué serie o película es.",
                         "Pick on the left which show or movie it is."),
    "match_pick_episode": ("{show}: elige el capítulo a la derecha.", "{show}: pick the episode on the right."),
    "match_search": ("Buscar", "Search"),
    "match_kind_auto": ("Serie o película", "Show or movie"),
    "match_kind_series": ("Serie", "TV show"),
    "match_kind_movie": ("Película", "Movie"),
    "match_use": ('Aceptar', 'OK'),
    "match_none": ("Sin resultados. Prueba con el título original (en inglés) o pega el enlace de su "
                   "página en IMDb, TMDB o TVmaze.",
                   "No results. Try the original title or paste the link to its IMDb, TMDB or TVmaze page."),
    "match_searching": ("Buscando…", "Searching…"),
    "match_same": ('Usar esta misma serie para los demás capítulos (cada uno conserva su número de capítulo; no cambia los que elegiste a mano)', 'Use this same show for the other episodes (each keeps its own episode number; the ones you picked by hand are kept)'),
    "kind_series": ("Serie", "Show"),
    "kind_movie": ("Película", "Movie"),
    "renamed_ok": ("✓ Renombrado", "✓ Renamed"),
    "rename_running": ("Renombrando {n} vídeo(s)…", "Renaming {n} video(s)…"),
    "rename_fail": ("No se pudo renombrar (no se ha cambiado nada):\n{err}",
                    "Could not rename (nothing was changed):\n{err}"),
    "rename_done_msg": ("{n} vídeo(s) renombrados.", "{n} video(s) renamed."),
    "unidentified_convert": ('{n} vídeo(s) aún no están identificados. Esperarán en la cola hasta que los identifiques; el resto empieza ya.\n\n¿Empezar?', '{n} video(s) are not identified yet. They will wait in the queue until you identify them; the rest start now.\n\nStart?'),
    "unidentified_rename": ("{n} vídeo(s) aún no están identificados y no se renombrarán. "
                            "¿Renombrar los demás?",
                            "{n} video(s) are not identified and won't be renamed. Rename the others?"),
    "nothing_to_rename": ("No hay vídeos identificados para renombrar.", "There are no identified videos to rename."),
    "held": ('Esperando a que lo identifiques', 'Waiting for you to identify it'),
    "bar_tmdb": ("Para identificar películas hace falta una clave de TMDB (gratuita). Sin ella solo se "
                 "identifican series.", "Identifying movies needs a (free) TMDB key. Without it only TV "
                 "shows are identified."),
    "bar_import": ("Tienes claves guardadas en Retitler. ¿Usarlas también aquí?",
                   "You have keys saved in Retitler. Use them here too?"),
    "bar_library": ("Elige las carpetas de tu biblioteca (series y películas).",
                    "Choose your library folders (shows and movies)."),
    "bar_configure": ("Configurar", "Configure"),
    "bar_import_btn": ("Importar claves", "Import keys"),
    "bar_dismiss": ("Ahora no", "Not now"),
    "imported_keys": ("Claves importadas de Retitler: {names}.", "Keys imported from Retitler: {names}."),
    "out_library": ("📚 Biblioteca (series / películas)", "📚 Library (shows / movies)"),
    "post_warning": ("Terminado con avisos: {w}", "Done with warnings: {w}"),

    # preferencias: renombrado
    "tab_conversion": ("Conversión", "Conversion"),
    "tab_rename": ("Renombrado", "Renaming"),
    "tab_engines": ("Buscadores", "Search services"),
    "tab_presets": ("Presets", "Presets"),
    "tab_prefs": ("Preferencias", "Preferences"),
    "tab_about": ("Acerca de", "About"),
    "menu_tip": ("Ajustes de TuxEnc", "TuxEnc settings"),
    "conv_info": ("Ajustes de conversión. Preset: {preset}", "Conversion settings. Preset: {preset}"),
    "conv_info_off": ("la conversión está desactivada, pero puedes dejarlo configurado",
                      "conversion is off, but you can set it up anyway"),
    "presets_hint": ("Los presets guardan todos los ajustes de conversión. Los marcados con ★ son tuyos. "
                     "Doble clic para usar uno; arriba, en la ventana principal, también puedes cambiarlo.",
                     "Presets store all conversion settings. Those marked ★ are yours. Double-click to use "
                     "one; you can also switch it from the main window."),
    "preset_use": ("Usar este preset", "Use this preset"),
    "preset_current": ("en uso", "in use"),
    "preset_builtin": ("Preset incorporado", "Built-in preset"),
    "preset_user": ("Preset tuyo", "Your preset"),
    "settings_tip": ("Conversión, renombrado y buscadores, y preferencias de TuxEnc",
                     "Conversion, renaming and search services, and TuxEnc preferences"),
    "menu_conversion": ("Conversión (vídeo, audio y subtítulos)", "Conversion (video, audio and subtitles)"),
    "menu_rename": ("Renombrado y buscadores…", "Renaming and search services…"),
    "menu_prefs": ("Preferencias (idioma, integración, registros, acerca de)…",
                   "Preferences (language, integration, logs, about)…"),
    "bar_engines": ("Buscadores listos, sin configurar nada: {ready}.",
                    "Search services ready, nothing to set up: {ready}."),
    "bar_engines_missing": ("{missing} necesita tu propia clave (gratuita y opcional).",
                            "{missing} needs your own key (free and optional)."),
    "bar_engines_missing_n": ("{missing} necesitan tu propia clave (gratuita y opcional).",
                              "{missing} need your own key (free and optional)."),
    "bar_see_engines": ("Ver buscadores", "See services"),
    "rp_keys": ("Buscadores", "Search services"),
    "rp_keys_hint": ("TuxEnc trae sus propias claves de TMDB y TheTVDB, así que funcionan sin hacer nada. "
                     "TVmaze no necesita clave. IMDb (OMDb) necesita la tuya: es gratuita, pero tiene un "
                     "límite diario que, compartido, se agotaría enseguida. Si lo prefieres, en cualquiera "
                     "puedes poner tu propia clave.",
                     "TuxEnc includes its own TMDB and TheTVDB keys, so they work out of the box. TVmaze needs "
                     "no key. IMDb (OMDb) needs yours: it's free, but its daily limit would run out quickly if "
                     "shared. You can use your own key for any of them if you prefer."),
    "rp_keys_hint_nobuiltin": ("Esta copia de TuxEnc se compiló sin claves integradas. TVmaze no necesita clave "
                               "(solo series, títulos en inglés). TMDB y TheTVDB son gratuitas y dan títulos en "
                               "español; TMDB hace falta para películas. IMDb (OMDb) es opcional.",
                               "This TuxEnc build has no built-in keys. TVmaze needs no key (TV shows only, English "
                               "titles). TMDB and TheTVDB are free and give localized titles; TMDB is needed for "
                               "movies. IMDb (OMDb) is optional."),
    "rp_key_placeholder": ("Tu propia clave (opcional)", "Your own key (optional)"),
    "rp_pin_placeholder": ("PIN de suscriptor (solo si tu clave lo pide)", "Subscriber PIN (only if your key needs it)"),
    "rp_key_builtin": ("✓ Funcionando con la clave integrada de TuxEnc.", "✓ Working with TuxEnc's built-in key."),
    "rp_key_free": ("✓ Funciona sin clave (series, títulos en inglés).", "✓ Works without a key (TV shows, English titles)."),
    "rp_key_none_omdb": ("✗ Sin clave: IMDb no se usa. Consigue la tuya gratis y pégala aquí.",
                         "✗ No key: IMDb is not used. Get yours for free and paste it here."),
    "rp_key_clear_mine": ("Quitar la mía", "Remove mine"),
    "rp_key_save": ("Guardar", "Save"),
    "rp_key_clear": ("Borrar", "Remove"),
    "rp_key_get": ("Conseguir…", "Get one…"),
    "rp_key_env": ("✓ Funcionando con tu clave (variable de entorno).", "✓ Working with your key (environment variable)."),
    "rp_key_keyring": ("✓ Funcionando con tu clave (guardada en el llavero del sistema).",
                       "✓ Working with your key (saved in the system keyring)."),
    "rp_key_file": ("✓ Funcionando con tu clave (en ~/.config/tuxenc/renombrado/secrets.json, solo legible por ti).",
                    "✓ Working with your key (in ~/.config/tuxenc/renombrado/secrets.json, readable only by you)."),
    "rp_key_none": ("✗ Sin clave: este buscador no se usa.", "✗ No key: this service is not used."),
    "rp_key_invalid": ("El servicio dice que esa clave no es válida; no se ha guardado.",
                       "The service says that key is not valid; it was not saved."),
    "rp_key_unchecked": ("guardada sin comprobar ({err})", "saved without checking ({err})"),
    "rp_import_retitler": ("Importar las claves de Retitler", "Import keys from Retitler"),
    "rp_titles": ("Títulos", "Titles"),
    "rp_title_lang": ("Idioma de los títulos", "Title language"),
    "rp_formats": ("Formato de los nombres", "Name format"),
    "rp_series": ("Series", "TV shows"),
    "rp_movies": ("Películas", "Movies"),
    "rp_custom": ("Personalizado…", "Custom…"),
    "rp_example": ("Ejemplo: {ex}", "Example: {ex}"),
    "rp_vars": ("Variables: {series} {season} {episode} {title} {year} {resolution} {initial} · "
                "{season:02} pone un cero delante · una «/» crea carpetas.",
                "Variables: {series} {season} {episode} {title} {year} {resolution} {initial} · "
                "{season:02} adds a leading zero · a “/” creates folders."),
    "rp_keep_file_title": ("Si un capítulo solo tiene título en inglés, conservar el que ya trae el nombre del archivo",
                           "If an episode only has an English title, keep the one already in the file name"),
    "rp_keep_file_title_tip": ("Por ejemplo, «Foyle's War (2002) - S01E01 - La mujer alemana.mkv» conserva "
                               "«La mujer alemana» aunque TMDB solo tenga «The German Woman». Antes del inglés "
                               "se prueba el español de Latinoamérica de TMDB.",
                               "For example, “Foyle's War (2002) - S01E01 - La mujer alemana.mkv” keeps "
                               "“La mujer alemana” even if TMDB only has “The German Woman”."),
    "title_from_file": ("título de tu archivo", "title from your file"),
    "title_english": ("en inglés", "in English"),
    "title_from": ("título de {src}", "title from {src}"),
    "rp_skip_articles": ("{initial}: ignorar artículos (The Batman → B, El Padrino → P)",
                         "{initial}: ignore articles (The Batman → B, El Padrino → P)"),
    "rp_library": ("Biblioteca", "Library"),
    "rp_library_hint": ("Con «Guardar en: Biblioteca», las series van a su carpeta y las películas "
                        "a la suya, cada una con su formato.",
                        "With “Save to: Library”, shows go to their folder and movies to theirs, "
                        "each with its own format."),
    "rp_series_root": ("Carpeta de series", "Shows folder"),
    "rp_movie_root": ("Carpeta de películas", "Movies folder"),
    "rp_not_set": ("Sin elegir", "Not set"),
    "rp_original": ("Al convertir y renombrar, el archivo original…", "When converting and renaming, the original file…"),
    "rp_orig_keep": ("Se deja donde está", "Stays where it is"),
    "rp_orig_trash": ("Se envía a la papelera (con sus subtítulos)", "Goes to the trash (with its subtitles)"),
    "rp_orig_hint": ("Solo cuando la conversión termina bien. La papelera es recuperable.",
                     "Only when the conversion finishes successfully. The trash can be restored."),
    "fmt_s_library": ("Biblioteca con resolución — Serie (2012)/Season 01/Serie (2012) - S01E02 - Título - [1080p]",
                      "Library with resolution — Show (2012)/Season 01/Show (2012) - S01E02 - Title - [1080p]"),
    "fmt_s_jellyfin": ("Jellyfin / Plex — Serie (2012)/Season 01/Serie (2012) - S01E02 - Título",
                       "Jellyfin / Plex — Show (2012)/Season 01/Show (2012) - S01E02 - Title"),
    "fmt_s_1x01": ("1x01 — Serie - 1x02 - Título", "1x01 — Show - 1x02 - Title"),
    "fmt_s_s01e01": ("S01E01 — Serie - S01E02 - Título", "S01E01 — Show - S01E02 - Title"),
    "fmt_s_year": ("Con año — Serie (2012) - S01E02 - Título", "With year — Show (2012) - S01E02 - Title"),
    "fmt_s_folders": ("En carpetas — Serie/Temporada 01/Serie - S01E02 - Título",
                      "In folders — Show/Temporada 01/Show - S01E02 - Title"),
    "fmt_m_library": ("Biblioteca con resolución — B/Babel (2006) - [1080p]",
                      "Library with resolution — B/Babel (2006) - [1080p]"),
    "fmt_m_plain": ("Título (Año)", "Title (Year)"),
    "fmt_m_res": ("Título (Año) - [1080p]", "Title (Year) - [1080p]"),
    "fmt_m_folder": ("En carpeta / Jellyfin — Título (Año)/Título (Año)", "In a folder / Jellyfin — Title (Year)/Title (Year)"),

    # el convertido ocupa más que el original
    "bigger_q": ("⚠ El convertido ocupa más que el original ({pct} %). ¿Con cuál te quedas?",
                 "⚠ The converted file is bigger than the original ({pct} %). Which one do you keep?"),
    "bigger_use_conv": ("El convertido", "The converted one"),
    "bigger_use_conv_tip": ("El original (y sus subtítulos) va a la papelera",
                            "The original (and its subtitles) goes to the trash"),
    "bigger_use_orig": ("El original", "The original"),
    "bigger_use_orig_tip": ("El convertido va a la papelera. Si estabas renombrando, el original "
                            "ocupa su lugar con el nombre final",
                            "The converted file goes to the trash. If you were renaming, the original "
                            "takes its place with the final name"),
    "bigger_keep_both": ("Los dos", "Both"),
    "bigger_keep_both_tip": ("No se borra nada", "Nothing is deleted"),
    "bigger_kept_orig": ("✓ Te quedaste con el original", "✓ You kept the original"),
    "bigger_kept_conv": ("✓ Te quedaste con el convertido", "✓ You kept the converted one"),
    "bigger_fail": ("No se pudo completar:\n{err}", "Could not complete:\n{err}"),
    "rp_orig_hint_bigger": ("Si el convertido ocupa más que el original, el original nunca se borra solo: "
                            "TuxEnc te pregunta con cuál quedarte.",
                            "If the converted file is bigger than the original, the original is never "
                            "deleted automatically: TuxEnc asks which one to keep."),

    # pie
    "output": ("Guardar en", "Save to"),
    "out_source": ("Junto al original", "Next to the original"),
    "out_choose": ("Elegir carpeta…", "Choose folder…"),
    "parallel": ("Simultáneos", "At once"),
    "parallel_auto": ("Auto ({n})", "Auto ({n})"),
    "parallel_tip": ("Cuántos vídeos se transcodifican a la vez.\nAuto calcula el ideal para tu CPU ({cores} hilos).\n"
                     "Si lo bajas con la cola en marcha, los vídeos que ya están en curso terminan; "
                     "el cambio se aplica a los siguientes.",
                     "How many videos are transcoded at the same time.\nAuto picks the best value for your CPU ({cores} threads).\n"
                     "If you lower it while the queue runs, videos in progress finish; "
                     "the change applies to the next ones."),
    "low_prio": ("Prioridad baja", "Low priority"),
    "low_prio_tip": ("Las transcodificaciones ceden el procesador a tus otros programas, así el equipo "
                     "sigue fluido mientras trabaja.\nSi no estás usando el equipo, apenas cambia la velocidad.",
                     "Transcodes yield the processor to your other programs, so the computer stays "
                     "responsive while working.\nIf you're not using the computer, speed barely changes."),
    "when_done": ("Al terminar", "When done"),
    "end_nothing": ("No hacer nada", "Do nothing"),
    "end_notify": ("Avisar", "Notify"),
    "end_quit": ("Cerrar TuxEnc", "Quit TuxEnc"),
    "end_suspend": ("Suspender el equipo", "Suspend computer"),
    "end_shutdown": ("Apagar el equipo", "Shut down computer"),
    "status_idle": ("{n} vídeo(s) en la cola", "{n} video(s) in the queue"),
    "status_empty": ("La cola está vacía", "The queue is empty"),
    "status_run": ("{run} en curso · {wait} en espera · {done} listos",
                   "{run} running · {wait} waiting · {done} done"),
    "status_paused": ("En pausa", "Paused"),

    # estados de trabajo
    "st_waiting": ("En espera", "Waiting"),
    "st_preparing": ("Preparando…", "Preparing…"),
    "st_running": ("Transcodificando", "Transcoding"),
    "st_paused": ("En pausa", "Paused"),
    "st_done": ("Terminado", "Done"),
    "st_failed": ("Error", "Error"),
    "st_cancelled": ("Cancelado", "Cancelled"),
    "remaining": ("{t} restantes", "{t} left"),
    "pass_n": ("pasada {n}/{t}", "pass {n}/{t}"),
    "done_info": ("{size} · {ratio} del original · {t}", "{size} · {ratio} of original · {t}"),
    "tracks": ('Audio y subtítulos…', 'Audio and subtitles…'),
    "tracks_tip": ('Elegir a mano qué pistas de audio y subtítulos se conservan en este vídeo', 'Choose by hand which audio and subtitle tracks this video keeps'),
    "remove": ('Quitar de la lista', 'Remove from the list'),
    "cancel_job": ('Cancelar la conversión de este vídeo', 'Cancel converting this video'),
    "retry": ("Reintentar", "Retry"),
    "open_folder": ("Abrir carpeta", "Open folder"),
    "play": ("Reproducir", "Play"),
    "view_log": ('Ver detalles', 'Details'),
    "move_up": ("Subir", "Move up"),
    "move_down": ("Bajar", "Move down"),
    "custom_tracks": ("pistas a mano", "custom tracks"),

    # presets
    "preset": ("Preset", "Preset"),
    "preset_save": ("Guardar los ajustes actuales como preset…", "Save current settings as a preset…"),
    "preset_delete": ("Eliminar este preset", "Delete this preset"),
    "preset_import": ("Importar presets de HandBrake…", "Import HandBrake presets…"),
    "preset_export": ("Exportar mis presets…", "Export my presets…"),
    "preset_name": ("Nombre del preset:", "Preset name:"),
    "preset_exists": ("Ya existe un preset con ese nombre. ¿Reemplazarlo?",
                      "A preset with that name already exists. Replace it?"),
    "preset_delete_q": ("¿Eliminar el preset «{name}»?", "Delete preset “{name}”?"),
    "preset_imported": ("Importados {n} preset(s) de HandBrake.", "Imported {n} HandBrake preset(s)."),
    "preset_import_fail": ("No se ha podido leer el archivo de presets:\n{err}",
                           "Could not read the presets file:\n{err}"),
    "preset_hw_missing": ("Este preset usa {enc}, que no está disponible en este equipo.\n\n"
                          "Motivo: {why}\n\nSe usará {alt}. Tienes el diagnóstico completo en "
                          "☰ Preferencias → Ver diagnóstico de GPU.",
                          "This preset uses {enc}, which is not available on this computer.\n\n"
                          "Reason: {why}\n\n{alt} will be used instead. Full diagnostics in "
                          "☰ Preferences → View GPU diagnostics."),
    "nv_driver_old": ("el driver de NVIDIA es demasiado antiguo para NVENC; hace falta la versión {need} o superior",
                      "the NVIDIA driver is too old for NVENC; version {need} or newer is required"),
    "nv_no_driver": ("no se encuentra el driver propietario de NVIDIA (libcuda / libnvidia-encode)",
                     "the proprietary NVIDIA driver was not found (libcuda / libnvidia-encode)"),
    "gpu_not_present": ("este equipo no tiene gráfica {vendor}", "this computer has no {vendor} graphics card"),
    "why_unknown": ("no se ha detectado esa GPU", "that GPU was not detected"),
    "gpu_diag": ("Ver diagnóstico de GPU", "View GPU diagnostics"),
    "gpu_diag_title": ("Diagnóstico de GPU", "GPU diagnostics"),
    "my_presets": ("Mis presets", "My presets"),
    "builtin_presets": ("Incluidos", "Built-in"),

    # panel de ajustes
    "tab_video": ("Vídeo", "Video"),
    "tab_picture": ("Imagen", "Picture"),
    "tab_audio": ("Audio", "Audio"),
    "tab_subs": ("Subtítulos", "Subtitles"),
    "container": ("Formato", "Format"),
    "grp_cpu": ("── Procesador (CPU) · máxima calidad, más lento ──",
                "── Processor (CPU) · best quality, slower ──"),
    "grp_gpu": ("── Tarjeta gráfica (GPU) · muy rápido ──", "── Graphics card (GPU) · very fast ──"),
    "grp_gpu_none": ("── Tarjeta gráfica (GPU): no detectada ──", "── Graphics card (GPU): not detected ──"),
    "grp_gpu_wait": ("── Tarjeta gráfica (GPU): detectando… ──", "── Graphics card (GPU): detecting… ──"),
    "cpu_hint": ("Este códec usa solo el procesador. Tu tarjeta gráfica puede hacerlo muchísimo más rápido.",
                 "This codec uses the processor only. Your graphics card can do it much faster."),
    "use_gpu": ("Usar la GPU ({name})", "Use the GPU ({name})"),
    "uses_cpu": ("CPU", "CPU"),
    "uses_gpu": ("GPU", "GPU"),
    "codec": ("Códec", "Codec"),
    "rate_mode": ("Control de calidad", "Quality control"),
    "rate_cq": ("Calidad constante", "Constant quality"),
    "rate_abr": ("Bitrate medio", "Average bitrate"),
    "rate_cbr": ("Bitrate constante", "Constant bitrate"),
    "quality": ("Calidad", "Quality"),
    "quality_better": ("← más calidad", "← higher quality"),
    "quality_smaller": ("menos tamaño →", "smaller file →"),
    "bitrate": ("Bitrate (kbps)", "Bitrate (kbps)"),
    "a_copy_if_lower": ("Si una pista ya está en ese formato con menos bitrate, copiarla sin recomprimir",
                        "If a track is already in that format with a lower bitrate, copy it without re-encoding"),
    "a_copy_if_lower_tip": ("Por ejemplo, una pista AAC estéreo de 128 kbps se copia tal cual en vez de "
                            "recomprimirla a 160 kbps: no crece y no pierde calidad. Necesita los mismos "
                            "canales y que el archivo indique el bitrate de la pista.",
                            "For example, a 128 kbps stereo AAC track is copied as is instead of being "
                            "re-encoded to 160 kbps: it doesn't grow or lose quality. Needs the same "
                            "channels and the track bitrate to be known."),
    "copy_if_lower": ("Si el original ya tiene menos bitrate, copiar el vídeo sin recomprimir",
                      "If the original already has a lower bitrate, copy the video without re-encoding"),
    "copy_if_lower_tip": ("Recomprimir un vídeo que ya ocupa poco lo haría crecer y perder calidad. "
                          "Se copia tal cual (en segundos) y solo se procesan el audio, los subtítulos, "
                          "el formato y el nombre. No se aplica si hay que cambiar la imagen "
                          "(resolución, recorte, filtros, subtítulos incrustados) ni con códecs antiguos.",
                          "Re-encoding a video that is already small would make it bigger and lose quality. "
                          "It is copied as is (in seconds) and only audio, subtitles, format and name are "
                          "processed. Not applied when the picture must change (resolution, crop, filters, "
                          "burned subtitles) or with old codecs."),
    "video_copied": ("Vídeo copiado sin recomprimir (original: {src} kbps < {dst})",
                     "Video copied without re-encoding (original: {src} kbps < {dst})"),
    "two_pass": ("2 pasadas (más precisa, tarda más)", "2 passes (more accurate, slower)"),
    "speed": ("Velocidad", "Speed"),
    "sp_fastest": ("el más rápido, peor compresión", "fastest, worst compression"),
    "sp_fast": ("rápido", "fast"),
    "sp_balanced": ("equilibrado", "balanced"),
    "sp_recommended": ("recomendado", "recommended"),
    "sp_better": ("mejor compresión, más lento", "better compression, slower"),
    "sp_best": ("máxima compresión, muy lento", "best compression, very slow"),
    "speed_hint": ("Más lento = el codificador busca mejor: más calidad con el mismo tamaño, "
                   "o menos tamaño con la misma calidad. A cambio, tarda más.",
                   "Slower = the encoder searches harder: more quality at the same size, "
                   "or a smaller file at the same quality. In exchange, it takes longer."),
    "hint_cq": ("Fijas la calidad visual y cada escena usa lo que necesita. El tamaño final varía según "
                "el vídeo. Lo más recomendable para guardar películas.",
                "You set the visual quality and each scene uses what it needs. The final size depends on "
                "the video. Best choice for keeping movies."),
    "hint_abr": ("Fijas el tamaño: el vídeo ocupará lo que marques de media. La calidad baja en las "
                 "escenas difíciles (acción, grano). Útil si necesitas que quepa en un espacio concreto.",
                 "You set the size: the video averages the bitrate you choose. Quality drops in hard "
                 "scenes (action, grain). Useful when it must fit in a given space."),
    "hint_cbr": ("Mismo bitrate cada segundo, aunque la imagen no lo necesite. Pensado para emitir en "
                 "directo; para archivos desperdicia espacio.",
                 "Same bitrate every second, even if the picture doesn't need it. Meant for live "
                 "streaming; wastes space in files."),
    "size_per_hour": ("≈ {mb} por hora de vídeo (sin contar el audio)",
                      "≈ {mb} per hour of video (audio not included)"),
    "upscale": ("Permitir ampliar vídeos más pequeños", "Allow upscaling smaller videos"),
    "upscale_hint": ("El vídeo siempre se ajusta al recuadro elegido manteniendo su proporción. "
                     "Ampliar no añade detalle: solo aumenta el tamaño del archivo.",
                     "The video always fits inside the chosen box keeping its aspect ratio. "
                     "Upscaling adds no detail: it only makes the file bigger."),
    "bit_depth": ("Profundidad de color", "Color depth"),
    "bits8": ("8 bits", "8-bit"),
    "bits10": ("10 bits (menos bandas, recomendable)", "10-bit (less banding, recommended)"),
    "keep_chapters": ("Conservar capítulos y metadatos", "Keep chapters and metadata"),
    "resolution": ("Resolución máxima", "Maximum resolution"),
    "res_source": ("Igual que el original", "Same as source"),
    "framerate": ("Fotogramas por segundo", "Frames per second"),
    "fps_source": ("Igual que el original", "Same as source"),
    "autocrop": ("Recortar bandas negras automáticamente", "Crop black bars automatically"),
    "deinterlace": ("Desentrelazar", "Deinterlace"),
    "deint_off": ("No", "Off"),
    "deint_yadif": ("Yadif (rápido)", "Yadif (fast)"),
    "deint_bwdif": ("Bwdif (mejor calidad)", "Bwdif (better quality)"),
    "deint_hint": ("Solo afecta a los fotogramas marcados como entrelazados.",
                   "Only affects frames flagged as interlaced."),
    "denoise": ("Reducir ruido", "Denoise"),
    "dn_off": ("No", "Off"),
    "dn_light": ("Suave", "Light"),
    "dn_medium": ("Medio", "Medium"),
    "dn_strong": ("Fuerte", "Strong"),
    "a_tracks": ("Pistas de audio", "Audio tracks"),
    "a_first": ("La primera en mis idiomas", "First one in my languages"),
    "a_lang_all": ("Todas las de mis idiomas", "All in my languages"),
    "a_all": ("Todas", "All"),
    "a_none": ("Sin audio", "No audio"),
    "a_codec": ("Códec de audio", "Audio codec"),
    "audio_copy": ("Copiar sin tocar (recomendado)", "Pass through (recommended)"),
    "a_bitrate": ("Bitrate", "Bitrate"),
    "a_br_auto": ("Automático", "Automatic"),
    "a_mix": ("Canales", "Channels"),
    "mix_keep": ("Mantener los del original", "Keep original"),
    "mix_stereo": ("Estéreo", "Stereo"),
    "mix_51": ("5.1", "5.1"),
    "langs": ("Mis idiomas (por orden de preferencia)", "My languages (in order of preference)"),
    "lang_add": ("Añadir idioma…", "Add language…"),
    "lang_hint": ("Si un vídeo no tiene ninguno de tus idiomas, se usa su pista principal. "
                  "Lista vacía = cualquier idioma.",
                  "If a video has none of your languages, its main track is used. "
                  "Empty list = any language."),
    "s_tracks": ("Subtítulos", "Subtitles"),
    "s_none": ("Ninguno", "None"),
    "s_forced": ("Solo forzados (carteles y diálogos en otro idioma)",
                 "Forced only (signs and foreign dialogue)"),
    "s_first": ("El primero de mis idiomas", "First one in my languages"),
    "s_lang_all": ("Todos los de mis idiomas", "All in my languages"),
    "s_all": ("Todos", "All"),
    "s_burn": ("Incrustar en la imagen", "Burn into the picture"),
    "burn_none": ("No incrustar", "Don't burn in"),
    "burn_forced": ("Los forzados", "Forced ones"),
    "burn_first": ("El primero de mis idiomas", "First one in my languages"),
    "subs_hint": ("MP4 y WebM solo admiten subtítulos de texto. Los de imagen (PGS, VobSub) "
                  "se conservan en MKV o se pueden incrustar.",
                  "MP4 and WebM only support text subtitles. Image-based ones (PGS, VobSub) "
                  "are kept in MKV or can be burned in."),

    # diálogo de pistas
    "tracks_title": ('Audio y subtítulos de «{name}»', 'Audio & subtitles of “{name}”'),
    "tracks_audio": ("Audio", "Audio"),
    "tracks_subs": ("Subtítulos", "Subtitles"),
    "tracks_burn": ("Incrustar en la imagen", "Burn into picture"),
    "tracks_auto": ("Volver a automático", "Back to automatic"),
    "forced": ("forzado", "forced"),
    "default": ("por defecto", "default"),
    "image_sub": ("imagen", "image"),
    "no_tracks": ("(no tiene)", "(none)"),
    "not_in_container": ("no compatible con {c}", "not supported by {c}"),

    # preferencias
    "ui_language": ("Idioma de la interfaz", "Interface language"),
    "lang_auto": ("Automático (el del sistema)", "Automatic (system)"),
    "restart_needed": ("Para cambiar el idioma, TuxEnc se reiniciará (te preguntará al cerrar esta ventana).",
                       "To change the language, TuxEnc will restart (you'll be asked when closing this window)."),
    "integration": ("Integración con el sistema", "System integration"),
    "integrated_yes": ("TuxEnc está en el menú de aplicaciones.\nPara desinstalarlo usa «Desinstalar TuxEnc» en el menú.",
                       "TuxEnc is in the applications menu.\nTo uninstall it use “Uninstall TuxEnc” in the menu."),
    "integrated_no": ("TuxEnc no está integrado en el menú.", "TuxEnc is not in the applications menu."),
    "integrated_dev": ("Integración disponible solo al ejecutar el AppImage.",
                       "Integration is only available when running the AppImage."),
    "integrate_now": ("Integrar en el sistema", "Integrate into the system"),
    "integrate_update": ("Actualizar la versión integrada", "Update the integrated version"),
    "shortcut_again": ("Volver a crear el acceso directo", "Re-create the desktop shortcut"),
    "encoders_found": ("Codificadores disponibles", "Available encoders"),
    "gpu_none": ("No se ha detectado aceleración por GPU (detalles en gpu-detect.log, en la carpeta de registros).",
                 "No GPU acceleration detected (details in gpu-detect.log, in the logs folder)."),
    "detecting": ("Detectando…", "Detecting…"),
    "logs": ("Registros", "Logs"),
    "open_logs": ("Abrir carpeta de registros", "Open logs folder"),
    "about": ("Acerca de", "About"),
    "match_credits": ("Datos: TMDB · TheTVDB · TVmaze · IMDb (OMDb)", "Data: TMDB · TheTVDB · TVmaze · IMDb (OMDb)"),
    "credits_text": (
        "<b>Datos de series y películas</b><br>"
        "Este producto usa la API de TMDB, pero no está avalado ni certificado por TMDB · "
        "<a href='https://www.themoviedb.org/'>themoviedb.org</a><br>"
        "Metadatos de TheTVDB · <a href='https://thetvdb.com/'>thetvdb.com</a><br>"
        "Datos de TVmaze (CC BY-SA) · <a href='https://www.tvmaze.com/'>tvmaze.com</a><br>"
        "IMDb a través de OMDb · <a href='https://www.omdbapi.com/'>omdbapi.com</a>",
        "<b>TV and movie data</b><br>"
        "This product uses the TMDB API but is not endorsed or certified by TMDB · "
        "<a href='https://www.themoviedb.org/'>themoviedb.org</a><br>"
        "Metadata provided by TheTVDB · <a href='https://thetvdb.com/'>thetvdb.com</a><br>"
        "Data from TVmaze (CC BY-SA) · <a href='https://www.tvmaze.com/'>tvmaze.com</a><br>"
        "IMDb via OMDb · <a href='https://www.omdbapi.com/'>omdbapi.com</a>"),
    "about_text": ("<span style='font-size:20px'><b>TuxEnc {v}</b></span><br>"
                   "Transcodificador de vídeo para Linux con cola paralela, y renombrador de series y "
                   "películas para tu biblioteca.<br><br>"
                   "Usa <b>FFmpeg</b> (x264, x265, SVT-AV1, libvpx, Opus…) y <b>Qt</b>.",
                   "<span style='font-size:20px'><b>TuxEnc {v}</b></span><br>"
                   "Video transcoder for Linux with a parallel queue, and TV show and movie renamer "
                   "for your library.<br><br>"
                   "Uses <b>FFmpeg</b> (x264, x265, SVT-AV1, libvpx, Opus…) and <b>Qt</b>."),
    "about_author": ("<b>Desarrollado por {author}</b><br>"
                     "Contacto: <a href='mailto:{mail}'>{mail}</a><br>"
                     "<span style='color:#8d97b5'>Built with Claude, Anthropic</span>",
                     "<b>Developed by {author}</b><br>"
                     "Contact: <a href='mailto:{mail}'>{mail}</a><br>"
                     "<span style='color:#8d97b5'>Built with Claude, Anthropic</span>"),
    "about_license": ("Software libre bajo licencia <b>GNU GPL v3</b>: puedes usarlo, estudiarlo, "
                      "compartirlo y modificarlo · <a href='https://www.gnu.org/licenses/gpl-3.0.html'>"
                      "gnu.org/licenses/gpl-3.0</a>",
                      "Free software under the <b>GNU GPL v3</b>: you may use, study, share and modify it · "
                      "<a href='https://www.gnu.org/licenses/gpl-3.0.html'>gnu.org/licenses/gpl-3.0</a>"),

    # primer arranque / integración
    "integrate_q_title": ("Bienvenido a TuxEnc", "Welcome to TuxEnc"),
    "integrate_q": ("<b>¿Integrar TuxEnc en el sistema?</b><br><br>"
                    "Se añadirá al menú de aplicaciones (junto con «Desinstalar TuxEnc») "
                    "y se creará un acceso directo en el escritorio.<br><br>"
                    "TuxEnc se copiará a su propia carpeta, así que después puedes borrar "
                    "lo que has descargado.",
                    "<b>Integrate TuxEnc into the system?</b><br><br>"
                    "It will be added to the applications menu (together with “Uninstall TuxEnc”) "
                    "and a desktop shortcut will be created.<br><br>"
                    "TuxEnc will be copied to its own folder, so you can delete what you "
                    "downloaded afterwards."),
    "update_q": ("<b>Ya tienes TuxEnc integrado.</b><br><br>¿Quieres sustituir la versión "
                 "integrada por esta ({v})?",
                 "<b>TuxEnc is already integrated.</b><br><br>Do you want to replace the "
                 "integrated version with this one ({v})?"),
    "update_newer_q": ("<b>Hay una versión nueva de TuxEnc.</b><br><br>Tienes la {old} y esta es la {v}."
                       "<br><br>¿Actualizar?",
                       "<b>A new version of TuxEnc is available.</b><br><br>You have {old} and this is {v}."
                       "<br><br>Update?"),
    "update_older_q": ("<b>Esta versión ({v}) es anterior a la que tienes instalada ({old}).</b><br><br>"
                       "¿Sustituirla de todas formas?",
                       "<b>This version ({v}) is older than the one installed ({old}).</b><br><br>"
                       "Replace it anyway?"),
    "update_running_note": ("<br><br>TuxEnc está abierto: se cerrará solo y se abrirá la versión nueva. "
                            "Los vídeos que esperan en la cola se conservan.",
                            "<br><br>TuxEnc is open: it will close by itself and the new version will open. "
                            "Videos waiting in the queue are kept."),
    "update_cancelled_busy": ("No se ha actualizado: TuxEnc sigue abierto con conversiones en marcha.\n\n"
                              "Cuando terminen, vuelve a abrir el archivo descargado.",
                              "Not updated: TuxEnc is still open with conversions in progress.\n\n"
                              "When they finish, open the downloaded file again."),
    "update_close_old": ("Hay abierta una versión anterior de TuxEnc que no sabe cerrarse sola para "
                         "actualizar.\n\nCiérrala y vuelve a abrir el archivo descargado "
                         "(solo hará falta esta vez).",
                         "An older TuxEnc version is open that can't close by itself for the update."
                         "\n\nClose it and open the downloaded file again (only needed this once)."),
    "just_updated": ("<b>TuxEnc actualizado a la {v}.</b>{old}<br><br>Ya puedes borrar el archivo que descargaste.",
                     "<b>TuxEnc updated to {v}.</b>{old}<br><br>You can now delete the file you downloaded."),
    "just_integrated": ("<b>¡Listo! TuxEnc ya está en el menú de aplicaciones.</b><br><br>"
                        "Ya puedes borrar el archivo que descargaste.",
                        "<b>Done! TuxEnc is now in the applications menu.</b><br><br>"
                        "You can now delete the file you downloaded."),
    "integrate_yes": ("Integrar", "Integrate"),
    "integrate_later": ("Ahora no", "Not now"),
    "update_yes": ("Actualizar", "Update"),
    "install_this": ("Instalar esta versión", "Install this version"),
    "with_shortcut": ("Crear también un acceso directo en el escritorio",
                      "Also create a desktop shortcut"),
    "integrate_ok": ("¡Listo! TuxEnc ya está en el menú de aplicaciones.",
                     "Done! TuxEnc is now in the applications menu."),
    "integrate_ok_restart": ("<b>¡Listo! TuxEnc ya está en el menú de aplicaciones.</b><br><br>"
                             "Se va a reiniciar para abrirse desde su sitio. Después ya puedes "
                             "borrar el archivo que descargaste.",
                             "<b>Done! TuxEnc is now in the applications menu.</b><br><br>"
                             "It will restart to run from its own place. After that you can delete "
                             "the file you downloaded."),
    "update_ok_restart": ("<b>¡Actualizado a TuxEnc {new}!</b>{old}<br><br>"
                          "Se va a reiniciar para abrirse desde su sitio. Después ya puedes "
                          "borrar el archivo que descargaste.",
                          "<b>Updated to TuxEnc {new}!</b>{old}<br><br>"
                          "It will restart to run from its own place. After that you can delete "
                          "the file you downloaded."),
    "update_from": ("<br>(antes tenías la {v})", "<br>(you had {v} before)"),
    "restart_btn": ("Reiniciar TuxEnc", "Restart TuxEnc"),
    "restart_later": ("Más tarde", "Later"),
    "lang_restart_q": ("<b>Hay que reiniciar TuxEnc para verlo en español.</b><br><br>¿Reiniciar ahora?",
                       "<b>TuxEnc needs to restart to show in English.</b><br><br>Restart now?"),
    "lang_restart_queue": ("<br><br>Los vídeos que esperan en la cola se volverán a añadir solos.",
                           "<br><br>The videos waiting in the queue will be added back automatically."),
    "integrate_fail": ("No se ha podido integrar:\n{err}", "Integration failed:\n{err}"),

    # desinstalación
    "uninstall_title": ("Desinstalar TuxEnc", "Uninstall TuxEnc"),
    "uninstall_q": ("<b>¿Desinstalar TuxEnc de este equipo?</b><br><br>Se eliminarán:"
                    "<ul><li>El programa</li><li>Las entradas del menú y el acceso directo</li>"
                    "<li>Los iconos</li><li>Tus ajustes, presets, claves de TMDB/OMDb e historial de renombrado</li></ul>"
                    "Tus vídeos <b>no</b> se tocan.",
                    "<b>Uninstall TuxEnc from this computer?</b><br><br>This will remove:"
                    "<ul><li>The program</li><li>The menu entries and desktop shortcut</li>"
                    "<li>The icons</li><li>Your settings, presets, TMDB/OMDb keys and rename history</li></ul>"
                    "Your videos are <b>not</b> touched."),
    "uninstall_yes": ("Desinstalar", "Uninstall"),
    "uninstall_done": ("TuxEnc se ha desinstalado. Tu sistema queda como estaba.\n\n¡Hasta pronto! 🐧",
                       "TuxEnc has been uninstalled. Your system is as it was.\n\nSee you! 🐧"),

    # cierre / fin de cola
    "quit_running": ("Hay vídeos transcodificándose. Si sales, se cancelarán.\n\n¿Salir de todos modos?",
                     "Videos are being transcoded. Quitting will cancel them.\n\nQuit anyway?"),
    "quit_anyway": ("Salir", "Quit"),
    "queue_done_title": ("TuxEnc: cola terminada", "TuxEnc: queue finished"),
    "queue_done_msg": ("{ok} vídeo(s) listos", "{ok} video(s) done"),
    "queue_done_fail": (" · {n} con error", " · {n} failed"),
    "countdown_suspend": ("El equipo se suspenderá en {s} segundos.", "The computer will suspend in {s} seconds."),
    "countdown_shutdown": ("El equipo se apagará en {s} segundos.", "The computer will shut down in {s} seconds."),
    "do_it_now": ("Ahora", "Now"),
    "error_log_title": ("Registro de «{name}»", "Log of “{name}”"),
    "stop_q": ("¿Detener las transcodificaciones en curso? Los vídeos pendientes se quedan en la cola.",
               "Stop the running transcodes? Pending videos stay in the queue."),
}


def detect_system_lang() -> str:
    for var in ("LC_ALL", "LC_MESSAGES", "LANG", "LANGUAGE"):
        val = os.environ.get(var, "")
        if val:
            return "es" if val.lower().startswith(("es", "ca", "gl", "eu")) else "en"
    try:
        loc = locale.getlocale()[0] or ""
    except ValueError:
        loc = ""
    return "es" if loc.lower().startswith("es") else "en"


def set_language(lang: str) -> None:
    global _lang
    _lang = detect_system_lang() if lang in ("", "auto", None) else ("es" if lang == "es" else "en")


def current() -> str:
    return _lang


def tr_in(lang: str, key: str, **kw) -> str:
    """Como tr(), pero en un idioma concreto (p. ej. el recién elegido, antes de reiniciar)."""
    pair = STRINGS.get(key)
    lang = detect_system_lang() if lang in ("", "auto", None) else lang
    text = key if pair is None else (pair[0] if lang == "es" else pair[1])
    return text.format(**kw) if kw else text


def effective(lang: str) -> str:
    return detect_system_lang() if lang in ("", "auto", None) else ("es" if lang == "es" else "en")


def tr(key: str, **kw) -> str:
    pair = STRINGS.get(key)
    text = key if pair is None else (pair[0] if _lang == "es" else pair[1])
    return text.format(**kw) if kw else text
