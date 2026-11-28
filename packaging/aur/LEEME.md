# Paquete de AUR: `tuxenc-bin`

`tuxenc-bin/` tiene el PKGBUILD que se publica en AUR. Toma el zip de la Release oficial de GitHub, extrae el AppImage en `/opt/tuxenc` (no necesita FUSE) y pone:

- `/usr/bin/tuxenc`: lanzador que exporta `TUXENC_PACKAGED=pacman` y `APPDIR=/opt/tuxenc`;
- la entrada del menú, los iconos (de 16 a 512 px y SVG) y el metainfo;
- las licencias (TuxEnc y FFmpeg) y la documentación.

Con `TUXENC_PACKAGED`, TuxEnc sabe que lo instaló el gestor de paquetes:

- no se actualiza solo ni ofrece integrarse en la carpeta del usuario;
- Preferencias dice que se actualiza con el sistema (`paru -Syu`);
- si queda la copia AppImage integrada de antes, ofrece quitarla (su entrada del menú taparía la del paquete);
- «Desinstalar» remite a `pacman -R tuxenc-bin`.

Esto funciona a partir de la versión que incluye el modo paquete (1.3.7). Con versiones anteriores el paquete funciona, pero Preferencias no lo explica.

## Publicar por primera vez (en Arch/CachyOS)

1. Cuenta en https://aur.archlinux.org con la clave SSH pública añadida.
2. `bash packaging/aur/actualizar.sh 1.3.7` (pone la versión y la suma de la Release y rehace `.SRCINFO`).
3. Probar: `cd packaging/aur/tuxenc-bin && makepkg -si`, abrir TuxEnc desde el menú y desinstalar con `sudo pacman -R tuxenc-bin`.
4. `git clone ssh://aur@aur.archlinux.org/tuxenc-bin.git /tmp/aur-tuxenc-bin`, copiar `PKGBUILD`, `.SRCINFO` y `tuxenc.sh`, y `git commit` + `git push`.

## Cada versión nueva

`bash packaging/aur/actualizar.sh X.Y.Z`, probar con `makepkg -si` y subir los tres archivos al repositorio de AUR.
