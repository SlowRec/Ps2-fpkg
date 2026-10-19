# PS2 ISO → fPKG de PS4

Convierte juegos de PS2 (`.iso`, o `.bin` de 2352 bytes/sector) en **fPKG de PS4** con el
emulador oficial de *PS2 Classics*, listos para instalar en una PS4 con soporte de fPKG
(por ejemplo, con GoldHEN).

- Lee el **serial** del disco (`SYSTEM.CNF`) y genera TITLE_ID y CONTENT_ID válidos.
- Soporta **varios discos** (`image/disc01.iso`, `disc02.iso`, …).
- Convierte automáticamente imágenes **BIN** (CD en bruto) a ISO.
- Genera `param.sfo`, `config-emu-ps4.txt`, icono y fondo (o usa tus imágenes).
- Crea el proyecto `.gp4` y llama a **PkgTool** (LibOrbisPkg, software libre) para firmar el fPKG.
- Ventana gráfica y línea de comandos.

> **Importante:** esta herramienta **no incluye archivos de Sony**. El emulador se toma de un
> PS2 Classic de PS4 que tengas tú, y las ISOs deben ser copias de tus propios discos.

## Requisitos

1. **Python 3.9 o superior** (en Windows, el instalador de python.org ya trae la interfaz gráfica).
2. **Pillow** (opcional, recomendado): `pip install pillow`. Sirve para redimensionar tus imágenes
   y dibujar el título en el icono. Sin Pillow se usa un icono genérico.
3. **PkgTool** de [LibOrbisPkg](https://github.com/maxton/LibOrbisPkg/releases): descarga
   `PkgTool.Core` y copia el ejecutable a la carpeta `tools/` (o indica su ruta en la app).
   También se acepta `PkgTool.Core.dll` si tienes .NET instalado.
4. **Emulador base**: la carpeta de un PS2 Classic de PS4 (la que contiene `eboot.bin`,
   `ps2-emu-compiler.self`, `lua_include/`, `sce_sys/`, …). Puedes obtenerla:
   - volcando un PS2 Classic instalado en tu PS4 con un *dumper* de aplicaciones, o
   - extrayendo un fPKG de PS2 Classic que ya tengas:
     `PkgTool.Core pkg_extract --passcode 00000000000000000000000000000000 juego.pkg carpeta`
     (los archivos quedan en `carpeta/uroot/`; puedes indicar `carpeta` directamente).

   Las bases más usadas por la comunidad son las de *Jak and Daxter*, *Rogue Galaxy* y
   *Kinetica*. La compatibilidad depende del juego y de la base elegida.

## Uso con ventana

Windows: doble clic en `PS2-fPKG.bat`. En cualquier sistema:

```
python -m ps2fpkg
```

1. **Agregar…** las ISOs (en orden de disco). El serial se detecta solo.
2. Escribe el **nombre** que verás en el menú de la PS4.
3. Elige la carpeta del **emulador base**, **PkgTool** y la **carpeta de salida**.
4. (Opcional) icono, fondo, parche `.lua`, `.conf` del emulador y argumentos extra.
5. **Crear fPKG**. El resultado es `CONTENT_ID.pkg`, p. ej.
   `UP9000-SLUS20946_00-SLUS20946PS2FPKG.pkg`.

Las rutas del emulador, PkgTool y salida se recuerdan en `~/.ps2fpkg.json`.

## Uso por línea de comandos

```
python -m ps2fpkg "Jak and Daxter.iso" -e emu_base -o salida -t "Jak and Daxter" --icon portada.jpg
```

Juego de dos discos con ajustes del emulador:

```
python -m ps2fpkg disco1.iso disco2.iso -e emu_base -o salida -t "Mi juego" \
    --emu-arg=--gs-uprender=2x2 --emu-arg=--gs-upscale=edgesmooth
```

| Opción | Descripción |
| --- | --- |
| `-e, --emu` | carpeta del emulador base (obligatoria) |
| `-o, --output` | carpeta de salida |
| `-t, --title` | nombre en el menú de PS4 (por defecto, el serial) |
| `--serial` | fuerza el serial (`SLUS-20946`) si no se puede leer del disco |
| `--title-id`, `--content-id` | IDs personalizados del PKG |
| `--icon`, `--background` | imágenes para `icon0.png` (512×512) y `pic0/pic1.png` (1920×1080) |
| `--config-lua` | parche del juego → `patches/<SERIAL>_config.lua` |
| `--cli-conf` | opciones del emulador → `patches/<SERIAL>_cli.conf` |
| `--emu-arg` | línea para `config-emu-ps4.txt` (reemplaza la existente con la misma clave) |
| `--pkgtool` | ruta a PkgTool |
| `--gp4-only` | solo prepara el proyecto `.gp4` (para compilarlo con otra herramienta) |
| `--keep-work` | conserva la carpeta de trabajo |

## Qué hace exactamente

1. Copia (por referencia, sin duplicar) todos los archivos de la base **excepto** el disco del
   juego original, `param.sfo`, `keystone`, trofeos, licencias, PlayGo e imágenes del menú.
2. Añade tus discos como `image/discNN.iso` (las ISOs no se copian: PkgTool las lee directamente,
   así no necesitas el doble de espacio; solo los BIN se convierten).
3. Reescribe `config-emu-ps4.txt` con `--ps2-title-id=<SERIAL>`, `--max-disc-num=<N>` y tus argumentos.
4. Genera `sce_sys/param.sfo` (categoría `gd`), `icon0.png`, `pic0.png` y `pic1.png`.
5. Escribe `project.gp4` y ejecuta `PkgTool pkg_build`.

El espacio libre necesario es aproximadamente el tamaño del juego (el `.pkg` final).

## Pruebas

```
python -m unittest discover tests
```

La prueba completa con PkgTool se activa definiendo `PS2FPKG_PKGTOOL` con la ruta a PkgTool:
crea un PKG real, lo extrae y comprueba el contenido.
