"""De dónde sale este TuxEnc: compilación oficial (GitHub Actions), local o desde el código.

packaging/build.py genera ``_build_info.py`` dentro del AppImage con los datos del CI
(commit, repositorio, run). Sirve para que «Acerca de» diga de dónde sale y cómo comprobarlo.
No es una prueba de autenticidad por sí sola (una copia alterada podría copiar el texto): la
prueba está fuera, en el SHA-256 y la atestación de la Release.
"""
from __future__ import annotations

from . import VERSION


def render_module(env: dict[str, str], built: str) -> str:
    """Contenido de _build_info.py (lo usa el script de compilación)."""
    official = env.get("GITHUB_ACTIONS") == "true" and bool(env.get("GITHUB_SHA"))
    info = {"official": official, "built": built}
    if official:
        server = env.get("GITHUB_SERVER_URL", "https://github.com").rstrip("/")
        repo = env.get("GITHUB_REPOSITORY", "")
        info.update(repo=repo, commit=env.get("GITHUB_SHA", ""),
                    run_url=f"{server}/{repo}/actions/runs/{env.get('GITHUB_RUN_ID', '')}",
                    server=server)
    return '"""Generado al compilar. No editar ni subir al repositorio."""\nINFO = ' + repr(info) + "\n"


def load() -> dict:
    """{"kind": "official" | "local" | "source", …}"""
    try:
        from . import _build_info  # type: ignore[attr-defined]
    except ImportError:
        return {"kind": "source"}
    info = dict(getattr(_build_info, "INFO", {}) or {})
    if not info.get("official"):
        return {"kind": "local", "built": info.get("built", "")}
    server, repo = info.get("server", "https://github.com"), info.get("repo", "")
    commit = info.get("commit", "")
    return {"kind": "official", "built": info.get("built", ""), "repo": repo, "commit": commit,
            "commit_url": f"{server}/{repo}/commit/{commit}", "run_url": info.get("run_url", ""),
            "release_url": f"{server}/{repo}/releases/tag/v{VERSION}"}
