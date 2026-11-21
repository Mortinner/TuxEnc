# Seguridad · Security

**Español** · [English below](#english)

## Versiones con soporte

Solo la última versión publicada en [Releases](https://github.com/Mortinner/TuxEnc/releases/latest) recibe correcciones. Si usas una anterior, actualiza antes de informar.

## Cómo informar de un fallo de seguridad

**No abras una incidencia pública.** Usa el aviso privado de GitHub: pestaña **Security → Report a vulnerability** de este repositorio. Si no puedes, escribe a [mortinner@gmail.com](mailto:mortinner@gmail.com) con el asunto «TuxEnc seguridad».

Incluye la versión de TuxEnc, tu distribución y los pasos para reproducirlo. Recibirás respuesta en unos días. Cuando esté corregido se publicará una versión nueva y, si quieres, se te mencionará en sus notas.

## Comprobar una descarga

Cada Release incluye `SHA256SUMS` (`sha256sum -c SHA256SUMS`) y una atestación de procedencia de GitHub que demuestra que el zip y el AppImage se compilaron en las Actions de este repositorio a partir de un commit concreto:

```
gh attestation verify TuxEnc-X.Y.Z-linux-x86_64.zip --repo Mortinner/TuxEnc
```

Desde la 1.2.7, las actualizaciones desde la propia app hacen esta comprobación solas: solo descargan de GitHub por HTTPS y no instalan nada si el zip no coincide con el checksum SHA-256 de su Release.

---

<a name="english"></a>
## Supported versions

Only the latest version in [Releases](https://github.com/Mortinner/TuxEnc/releases/latest) receives fixes. Please update before reporting.

## Reporting a vulnerability

**Please do not open a public issue.** Use GitHub's private reporting: **Security → Report a vulnerability** in this repository, or email [mortinner@gmail.com](mailto:mortinner@gmail.com) with the subject "TuxEnc security". Include the TuxEnc version, your distribution and steps to reproduce. You will get an answer within a few days.

## Verifying a download

Each Release ships `SHA256SUMS` and a GitHub build provenance attestation: `gh attestation verify TuxEnc-X.Y.Z-linux-x86_64.zip --repo Mortinner/TuxEnc`. Since 1.2.7, in-app updates do this check themselves: GitHub over HTTPS only, and nothing is installed unless the zip matches the release's SHA-256 checksum.
