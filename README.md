# PS Classics → fPKG de PS4

Convierte juegos de **PS2, PS1, PSP, NES y SNES** en **fPKG de PS4**, cada uno con su icono en
el menú de la consola, optimizados para verse y sonar lo mejor posible y listos para instalar
con **GoldHEN** (por USB o directamente por la red).

| Consola | Emulador en la PS4 | Entrada | Lo que aporta tu PC |
| --- | --- | --- | --- |
| PS2 | oficial de Sony (PS2 Classics) | `.iso` o `.bin` | la carpeta de un PS2 Classic que tengas |
| PS1 | oficial de Sony (PS1HD, PlayStation Plus) | `.cue` + `.bin` | la carpeta de un PS1 Classic que tengas |
| PSP | oficial de Sony (PSPHD, PlayStation Plus) | `.iso` | la carpeta de un PSP Classic que tengas |
| NES | pNES (Nestopia) — **incluido** | `.nes`, `.fds`, `.zip` | nada más |
| SNES | pSNES (Snes9x) — **incluido** | `.sfc`, `.smc`, `.zip` | nada más |
| N64 | — | — | **no disponible** (ver abajo) |

> **Importante:** esta herramienta **no incluye archivos de Sony**. Los emuladores de PS1, PS2 y
> PSP salen de juegos clásicos de PS4 que tengas tú, y los juegos deben ser copias de los tuyos.
> Los emuladores de NES y SNES incluidos son software libre (GPL-3.0).

## Menú dentro del juego: partidas guardadas y pantalla

| Consola | Cómo se abre | Qué tiene |
| --- | --- | --- |
| PS1 | botón **OPTIONS** | estados guardados (varias ranuras), **rebobinar**, presets visuales y el menú **Gráficos** (resolución, filtro Lanczos/cúbico, antialiasing), que la app deja activado |
| PSP | el menú del emulador de PlayStation Plus (como en PS1) | estados guardados y **rebobinar**; la calidad de imagen se elige en la app antes de crear el PKG |
| NES / SNES | **L1 + R1** | 4 ranuras de estados guardados (con miniatura), escalado, filtro, shader, mandos y salir. Al empezar el juego aparece el aviso «L1 + R1: MENU DE PARTIDAS GUARDADAS Y PANTALLA» |
| PS2 | — | el emulador de PS2 de Sony **no trae menú**: las partidas se guardan en la tarjeta de memoria virtual desde el propio juego, y la pantalla se configura en la app antes de crear el PKG |

En PS2 se podría construir un menú propio con funciones internas del emulador, pero no están
documentadas y no se pueden probar sin la consola; un error ahí puede impedir que arranque el
juego, así que no se incluye.

## Nombre y carátula

- **Nombre del juego:** el que escribas es el que aparece en el menú de la PS4 (por defecto, el
  nombre del archivo sin etiquetas como «(USA)»).
- **Carátula:** con una sola imagen se hacen el **icono** (la carátula entera sobre una versión
  desenfocada de sí misma) y el **fondo** (la carátula desenfocada de fondo y nítida a la derecha).
- **Buscar carátula:** al elegir el juego la app la busca sola y la muestra; también con el botón
  **Buscar** o `--buscar-caratula`. PS1 y PS2 se buscan por serial (colecciones de carátulas que
  usan DuckStation y PCSX2) y todas las consolas por nombre en las carátulas de libretro. Si no
  aparece o no es la que quieres, elige tu propia imagen.
- **Icono propio / fondo propio:** reemplazan a los hechos con la carátula.

## Calidad de imagen y sonido

En todas las consolas el perfil por defecto es el de **máxima calidad**; cada pestaña permite
bajarlo si un juego va lento.

**PS2**

| Ajuste | Por defecto | Qué hace |
| --- | --- | --- |
| Perfil **máxima** | ✓ | `--gs-uprender=2x2` (resolución interna al doble en cada eje, el máximo del emulador) y `--gs-upscale=edgesmooth` (suavizado de bordes). |
| Pantalla panorámica 16:9 | ✓ | Parche 16:9 de PCSX2 para tu versión exacta del juego. Sin parche, se mantiene la proporción 4:3 (sin estirar). |
| Sin entrelazado | ✓ | Parche de PCSX2 que quita el entrelazado: imagen más nítida y sin parpadeo. |
| Configuración oficial | ✓ | Las opciones que Sony definió para ese juego en su versión oficial (correcciones gráficas, de sonido y de velocidad). Tienen prioridad sobre el perfil. |
| Modo 480p · Quitar desenfoque · 60 FPS | | Parches opcionales de PCSX2 (si existen para el juego). |

Los parches de PCSX2 se traducen al Lua del emulador de PS4 y cubren el 16:9 de unos
**4.100 juegos** (96 % de los que tienen parche en PCSX2). Si un parche usa códigos que el
emulador no admite, se omite completo en lugar de aplicarlo a medias.

**PS1**

| Ajuste | Por defecto | Qué hace |
| --- | --- | --- |
| Perfil **máxima** | ✓ | `--scale=6`: resolución interna 6x (el máximo del emulador). Alta = 4x, rendimiento = 2x. |
| Menú Gráficos | ✓ | Activa el menú *Gráficos* del emulador: desde el juego eliges filtro (Lanczos, cúbico) y antialiasing (CMAA). |
| Música CD-Audio | ✓ | Genera el TOC del disco para que suenen las pistas de audio; une los `.bin` de cada pista si vienen separados. |
| Forzar 60 Hz · Sticks analógicos · Saltar logo | | Para juegos PAL, juegos sin soporte analógico, y arranque directo. |

**PSP**

| Ajuste | Por defecto | Qué hace |
| --- | --- | --- |
| Perfil **máxima** | ✓ | `--antialias=SSAA4x`: supermuestreo, la mejor imagen. Equilibrado = MSAA4x (solo bordes); rendimiento = sin antialiasing. |
| Arte del UMD | ✓ | Usa el icono y el fondo del propio juego si no eliges otros. |
| EBOOT descifrado | ✓ | El emulador lo necesita: se descifra automáticamente (no se toca tu ISO original). |

**NES y SNES**

| Imagen | Qué hace |
| --- | --- |
| **Nítido** (por defecto) | Pantalla completa en 4:3, shader *sharp-bilinear*: píxeles definidos sin parpadeo ni bordes borrosos. |
| Suavizado | Shader *SABR* (tipo xBR): redondea los píxeles. |
| CRT | Shader *crt-easymode*: líneas y máscara de televisor antiguo. |
| Píxel exacto | Escala entera sin filtro. |

En SNES, el **sonido sincronizado** (activado) evita chasquidos. Son ajustes iniciales: luego
se pueden cambiar desde el menú del emulador en la PS4.

**Sobre el sonido:** todos los emuladores reproducen el audio original de cada consola; no hay
un ajuste que lo "mejore" más allá de que suene completo y sin cortes, que es lo que se asegura
(salida de audio activada, música CD-Audio en PS1, sincronía en SNES, correcciones oficiales en PS2).

## Nintendo 64

**No es posible por ahora:** no existe ningún emulador de N64 para PS4 (ni de Sony ni homebrew)
con el que crear paquetes. La pestaña N64 de la app lo explica; si aparece uno, se podrá añadir.

## Requisitos

1. **Python 3.9 o superior** (en Windows, el instalador de python.org ya trae la ventana).
2. **Pillow** (recomendado): `pip install pillow`. Ajusta tus imágenes y dibuja el título en el icono.
3. **PkgTool parcheado** y **eboot_decrypt**: en Windows ya vienen en `tools/win-x64/`. En
   Linux/macOS: `python tools/build_pkgtool.py` (git y .NET SDK 8) y, para PSP en macOS,
   `python tools/build_pspdecrypt.py`.
   > El PkgTool original de LibOrbisPkg **falla con muchos juegos grandes** (“Playgo Chunk hash
   > file was not allocated enough space”), según el tamaño exacto del juego y de las imágenes.
   > El incluido calcula ese tamaño de forma exacta.
4. **Emulador base** (solo PS1, PS2 y PSP): la carpeta de un clásico de PS4 de esa consola
   (la que contiene `eboot.bin`, `sce_module/`, `sce_sys/`, …). Puedes obtenerla volcando el
   juego instalado en tu PS4 con un *dumper* de aplicaciones, o extrayendo un fPKG que ya tengas:
   `PkgTool.Core pkg_extract --passcode 00000000000000000000000000000000 juego.pkg carpeta`
   (los archivos quedan en `carpeta/uroot/`; puedes indicar `carpeta` directamente).
   - PS2: las bases más usadas son las de *Jak and Daxter*, *Rogue Galaxy* y *Kinetica*.
   - PS1 y PSP: cualquier clásico de PlayStation Plus de esa consola.
   - Si la app avisa de que los ejecutables son **ELF sin firmar**, fírmalos como fSELF
     (`make_fself`) antes; si no, la PS4 puede no abrir el juego.
5. **Internet** (opcional, PS2): para descargar los parches de PCSX2 y la configuración oficial.
   Se guardan en `~/.ps2fpkg/cache`. Sin internet: `--parches CARPETA` con archivos `.pnach`.

## Uso con ventana

Windows: doble clic en `PS2-fPKG.bat`. En cualquier sistema: `python -m ps2fpkg`

1. Elige la **pestaña** de la consola (PS2, PS1, PSP, NES, SNES).
2. Agrega el juego (el serial, el nombre y la carátula se detectan solos) y, en PS1/PS2/PSP,
   el **emulador base**. Cambia el nombre o la carátula si quieres.
3. Revisa **Calidad de imagen y sonido** (ya viene en máxima).
4. Para instalar por red, escribe la **IP de la PS4** y marca **Enviar a la PS4 al terminar**.
5. **Crear fPKG**.

La app recuerda la carpeta de salida, la IP de la PS4 y el emulador base de cada consola.

## Uso por línea de comandos

```
python -m ps2fpkg "Jak and Daxter.iso" -e base_ps2 -o salida -t "Jak and Daxter"
python -m ps2fpkg ps1 "Crash Bandicoot.cue" -e base_ps1 -o salida
python -m ps2fpkg psp "LocoRoco.iso" -e base_psp -o salida
python -m ps2fpkg nes "Super Mario Bros. (World).nes" -o salida
python -m ps2fpkg snes "Super Metroid (USA).sfc" -o salida --imagen crt --instalar-en 192.168.1.50
python -m ps2fpkg nes "zelda.nes" -t "Zelda (mi copia)" --caratula portada.jpg
```

`python -m ps2fpkg ps1 --help` (o `ps2`, `psp`, `nes`, `snes`) muestra todas las opciones.

## Instalar en la PS4 con GoldHEN

Los PKG son fPKG firmados con la clave falsa estándar (passcode de ceros), que es lo que
instala GoldHEN, y se verifican (hashes y firmas) al crearlos. Cada juego tiene un CONTENT_ID
propio, así que puedes tener muchos instalados a la vez y reinstalar uno lo actualiza.

**Por la red (sin USB):**
1. En la PS4, con GoldHEN activo, abre **Remote Package Installer**.
2. En la PC: marca *Enviar a la PS4* en la ventana, o usa
   `python -m ps2fpkg instalar JUEGO.pkg --ps4 IP_DE_LA_PS4`.
3. Deja la app abierta en la PC hasta que la PS4 termine de descargar.
   Si el firewall pregunta, permite las conexiones (puerto 8000).

Sin `--ps4`, `instalar` solo muestra la URL del PKG para usarla en cualquier instalador por URL.

**Por USB:** copia el `.pkg` a la raíz de una memoria y en la PS4 ve a
*Ajustes → Debug Settings → Game → Package Installer*. Si el PKG pesa más de 4 GB, la memoria
debe estar en **exFAT** (FAT32 no admite archivos tan grandes); la app avisa cuando es el caso.

## Cómo funciona cada consola

- **PS2:** discos en `image/discNN.iso`, opciones en `config-emu-ps4.txt`, parches de PCSX2 en
  `feature_data/<SERIAL>_features.lua`, configuración oficial en `patches/<SERIAL>_cli.conf`.
- **PS1:** discos en `data/discN.bin` (+ `.cue` y `.toc`), opciones en `config-title.txt`.
  Se descartan el disco y los scripts del juego original de la base.
- **PSP:** copia de la ISO con el EBOOT descifrado en `data/USER_L0.IMG`, opciones en `config-title.txt`.
- **NES/SNES:** la app pemu con la ROM en `autoboot/`. La versión incluida tiene un parche
  (`tools/pemu-autoboot.patch`) para que, al abrir el juego desde el menú de la PS4, cargue esa
  ROM directamente con los ajustes de imagen elegidos, que al salir del juego se cierre, y que
  el aviso inicial indique en PS4 cómo abrir el menú (L1 + R1).
  Partidas guardadas: `/data/pnes` y `/data/psnes` en la PS4.

En todas: `sce_sys/param.sfo`, `icon0.png`, `pic0.png`, `pic1.png`, `project.gp4`,
`PkgTool pkg_build` y después `pkg_validate`.

## Pruebas

```
python -m unittest discover tests
```

Definiendo `PS2FPKG_PKGTOOL` con la ruta a PkgTool, las pruebas crean PKG reales de PS1, PS2 y
SNES, los verifican, los extraen y comprueban su contenido.

## Licencias y créditos

- [LibOrbisPkg](https://github.com/maxton/LibOrbisPkg) (LGPL-3.0) — creación de PKG; corrección de PlayGo en `tools/build_pkgtool.py`.
- [pemu](https://github.com/Cpasjuste/pemu) (GPL-3.0) — emuladores de NES y SNES incluidos en `emus/`; código del parche en `tools/pemu-autoboot.patch` y compilación en `tools/build_pemu.py`.
- [pspdecrypt](https://github.com/John-K/pspdecrypt) (GPL-3.0) — descifrado del EBOOT de PSP (`tools/build_pspdecrypt.py`).
- [PCSX2 patches](https://github.com/PCSX2/pcsx2_patches) — parches de imagen de PS2 (se descargan, no se incluyen).
- [Playstation-2-Classics-Patches-PS4](https://github.com/xXxTheDarkprogramerxXx/Playstation-2-Classics-Patches-PS4) — configuraciones oficiales de PS2 (se descargan, no se incluyen).
- [Remote Package Installer](https://github.com/flatz/ps4_remote_pkg_installer) — instalación por red.
- Carátulas: [ps2-covers](https://github.com/xlenore/ps2-covers) y [psx-covers](https://github.com/xlenore/psx-covers)
  (por serial) y [libretro-thumbnails](https://thumbnails.libretro.com/) (por nombre); se descargan, no se incluyen.
- Formato del TOC de PS1 contrastado con [Cue2toc](https://github.com/Goatman13/Cue2toc); opciones de
  los emuladores contrastadas con PS-Classics-fPKG-Builder, mkps4, easy-ps2-fpkg y las notas de
  [PlayStation-PS1HD](https://github.com/andshrew/PlayStation-PS1HD).
