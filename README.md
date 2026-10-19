# PS2 ISO → fPKG de PS4

Convierte juegos de PS2 (`.iso`, o `.bin` de 2352 bytes/sector) en **fPKG de PS4** con el
emulador oficial de *PS2 Classics*, optimizados para verse lo mejor posible y listos para
instalar en una PS4 con **GoldHEN** (por USB o directamente por la red).

> **Importante:** esta herramienta **no incluye archivos de Sony**. El emulador se toma de un
> PS2 Classic de PS4 que tengas tú, y las ISOs deben ser copias de tus propios discos.

## Qué hace

- Lee el **serial** y la **versión exacta** del juego (CRC del ejecutable, igual que PCSX2).
- Aplica el perfil de **calidad máxima** del emulador y los **parches de imagen** de la base de
  datos de PCSX2 para esa versión del juego (16:9, sin entrelazado…).
- Usa la **configuración oficial de Sony** para el juego cuando existe.
- Soporta **varios discos** y convierte imágenes **BIN** a ISO automáticamente.
- Genera `param.sfo`, icono y fondo (o usa tus imágenes).
- Crea el fPKG con un **PkgTool parcheado** y **verifica todos sus hashes y firmas** antes de darlo por bueno.
- Lo **envía a la PS4** por la red (Remote Package Installer) sin USB.

## Calidad de imagen y sonido

| Ajuste | Por defecto | Qué hace |
| --- | --- | --- |
| Perfil **máxima** | ✓ | `--gs-uprender=2x2` (resolución interna al doble en cada eje, el máximo que admite el emulador de PS4) y `--gs-upscale=edgesmooth` (suavizado de bordes al escalar a la pantalla). |
| Pantalla panorámica 16:9 | ✓ | Parche 16:9 de PCSX2 para tu versión del juego + `--host-display-mode=16:9`. Si el juego no tiene parche, se mantiene la proporción 4:3 original (sin estirar). |
| Sin entrelazado | ✓ | Parche de PCSX2 que quita el entrelazado: imagen más nítida y sin parpadeo. |
| Configuración oficial | ✓ | Las opciones que Sony definió para ese juego en su versión oficial de PS2 Classics (correcciones gráficas, de sonido y de velocidad). Tienen prioridad sobre el perfil. |
| Modo 480p | | Activa el modo progresivo del propio juego, si tiene parche. |
| Quitar desenfoque | | Quita filtros de desenfoque/bloom que algunos juegos aplican. |
| 60 FPS | | Parche de 60 FPS. Algunos juegos van más rápido o exigen más a la consola. |

- **Perfil rendimiento:** resolución nativa + suavizado, para juegos que van lentos a 2x.
- **Perfil original:** no toca la configuración del emulador base.
- **Sonido:** el emulador reproduce el audio original del PS2; no hay un ajuste que lo
  "mejore". Se garantiza la salida de audio (`--host-audio=1`) y, si Sony corrigió el audio de
  ese juego (latencia, volumen), se aplica con la configuración oficial.
- Los parches de PCSX2 se traducen a Lua del emulador de PS4. Hoy cubren el 16:9 de unos
  **4.100 juegos** (96 % de los que tienen parche en PCSX2). Si un parche usa códigos que el
  emulador de PS4 no admite, se omite completo en lugar de aplicarlo a medias.
- Ningún ajuste es perfecto para todos los juegos. Si un juego se ve mal, prueba
  `--sin-16-9`, el perfil `rendimiento`, o ajusta opciones con `--emu-arg`.

## Requisitos

1. **Python 3.9 o superior** (en Windows, el instalador de python.org ya trae la ventana).
2. **Pillow** (recomendado): `pip install pillow`. Redimensiona tus imágenes y dibuja el título en el icono.
3. **PkgTool parcheado**: en Windows ya viene en `tools/win-x64/`. En Linux/macOS compílalo con
   `python tools/build_pkgtool.py` (necesita git y .NET SDK 8).
   > El PkgTool original de LibOrbisPkg **falla con muchos juegos grandes** (“Playgo Chunk hash
   > file was not allocated enough space”), según el tamaño exacto del juego y de las imágenes.
   > El incluido calcula ese tamaño de forma exacta.
4. **Emulador base**: la carpeta de un PS2 Classic de PS4 (la que contiene `eboot.bin`,
   `ps2-emu-compiler.self`, `lua_include/`, `sce_sys/`, …). Puedes obtenerla:
   - volcando un PS2 Classic instalado en tu PS4 con un *dumper* de aplicaciones, o
   - extrayendo un fPKG de PS2 Classic que ya tengas:
     `PkgTool.Core pkg_extract --passcode 00000000000000000000000000000000 juego.pkg carpeta`
     (los archivos quedan en `carpeta/uroot/`; puedes indicar `carpeta` directamente).

   Las bases más usadas por la comunidad son las de *Jak and Daxter*, *Rogue Galaxy* y
   *Kinetica*. Si la app avisa de que los ejecutables son **ELF sin firmar**, fírmalos como
   fSELF (`make_fself`) antes; si no, la PS4 puede no abrir el juego.
5. **Internet** (opcional): para descargar los parches de PCSX2 y la configuración oficial.
   Se guardan en `~/.ps2fpkg/cache`. Sin internet: `--parches CARPETA` con archivos `.pnach`.

## Uso con ventana

Windows: doble clic en `PS2-fPKG.bat`. En cualquier sistema: `python -m ps2fpkg`

1. **Agregar…** las ISOs (en orden de disco). El serial se detecta solo.
2. Escribe el **nombre** que verás en el menú de la PS4 y elige el **emulador base**.
3. Revisa **Calidad de imagen y sonido** (ya viene en máxima).
4. Para instalar por red, escribe la **IP de la PS4** y marca **Enviar a la PS4 al terminar**.
5. **Crear fPKG**.

## Uso por línea de comandos

```
python -m ps2fpkg "Jak and Daxter.iso" -e emu_base -o salida -t "Jak and Daxter" --icon portada.jpg
```

Con más opciones y envío directo a la PS4:

```
python -m ps2fpkg disco1.iso disco2.iso -e emu_base -o salida -t "Mi juego" --480p --instalar-en 192.168.1.50
```

`python -m ps2fpkg --help` muestra todas las opciones (`--calidad`, `--sin-16-9`,
`--con-entrelazado`, `--480p`, `--sin-desenfoque`, `--60fps`, `--sin-config-oficial`,
`--parches`, `--sin-internet`, `--config-lua`, `--cli-conf`, `--emu-arg`, `--gp4-only`…).

## Instalar en la PS4 con GoldHEN

Los PKG son fPKG firmados con la clave falsa estándar (passcode de ceros), que es lo que
instala GoldHEN. Cada juego tiene un CONTENT_ID propio (`UP9000-SLUS20946_00-SLUS20946PS2FPKG`),
así que puedes tener muchos instalados a la vez y reinstalar uno lo actualiza.

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

## Qué hace exactamente

1. Copia (por referencia, sin duplicar) los archivos de la base **excepto** el disco del juego
   original, `param.sfo`, `keystone`, trofeos, licencias, PlayGo e imágenes del menú.
2. Añade tus discos como `image/discNN.iso` (las ISOs no se copian; solo los BIN se convierten).
3. Escribe `config-emu-ps4.txt`: serial, número de discos, perfil de calidad, rutas de parches
   y tus argumentos (con varios discos activa el script de cambio de disco de la base).
4. Parches de PCSX2 → `feature_data/<SERIAL>_features.lua`; configuración oficial →
   `patches/<SERIAL>_cli.conf`.
5. Genera `sce_sys/param.sfo` (categoría `gd`), `icon0.png`, `pic0.png` y `pic1.png`.
6. Escribe `project.gp4`, ejecuta `PkgTool pkg_build` y después `pkg_validate`.

## Pruebas

```
python -m unittest discover tests
```

La prueba completa con PkgTool se activa definiendo `PS2FPKG_PKGTOOL` con la ruta a PkgTool:
crea un PKG real, lo verifica, lo extrae y comprueba el contenido.

## Créditos

- [LibOrbisPkg](https://github.com/maxton/LibOrbisPkg) (LGPL-3.0) — creación de PKG; corrección de PlayGo en `tools/build_pkgtool.py`.
- [PCSX2 patches](https://github.com/PCSX2/pcsx2_patches) — parches de imagen por juego (se descargan, no se incluyen).
- [Playstation-2-Classics-Patches-PS4](https://github.com/xXxTheDarkprogramerxXx/Playstation-2-Classics-Patches-PS4) — configuraciones oficiales por juego (se descargan, no se incluyen).
- [Remote Package Installer](https://github.com/flatz/ps4_remote_pkg_installer) — instalación por red.
- Opciones del emulador contrastadas con PS-Classics-fPKG-Builder, mkps4 y easy-ps2-fpkg.
