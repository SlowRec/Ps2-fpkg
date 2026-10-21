# Tutorial: instalar tus juegos en la PS4 con PS Classics fPKG

Esta guía explica, paso a paso, cómo convertir un juego de cada consola en un **fPKG** (un juego
instalable con su propio icono en el menú de la PS4) y cómo instalarlo con **GoldHEN**.

Consolas: PS2 · PS1 · PSP · NES · SNES · GBA (y Game Boy / Color) · Genesis (y Master System /
Game Gear) · Dreamcast · GameCube / Wii.

---

## 1. Lo que necesitas

| Qué | Para qué |
| --- | --- |
| Una **PS4 con GoldHEN** activo | Instalar y abrir fPKG. GoldHEN se activa cada vez que se enciende la consola (con el exploit de tu firmware). |
| Una **PC con Windows** | Para usar `PS-Classics-fPKG.exe`. |
| **Copias de tus juegos** | Archivos de juegos que tengas (ISO, ROM, etc.). La app no trae juegos. |
| Una **memoria USB** o la **PS4 y la PC en la misma red** | Para pasar el fPKG a la consola. |
| Solo para **PS1, PS2 y PSP**: un *clásico* de esa consola instalado en tu PS4 | La app copia de ahí el emulador, que es de Sony y no se puede incluir (ver el paso 2). |

Las demás consolas (NES, SNES, GBA, Genesis, Dreamcast, GameCube/Wii) **no necesitan nada más**:
el emulador viene dentro de la app.

---

## 2. Preparar la app (una sola vez)

1. Descarga **PS-Classics-fPKG.exe** de la página de *Releases* del repositorio.
2. Guárdalo en una carpeta propia, por ejemplo `C:\PS Classics\`, y ábrelo con doble clic.
   - Si Windows SmartScreen avisa: **Más información → Ejecutar de todas formas**.
   - La primera vez tarda unos segundos en abrir.
3. Al abrirse, la app crea junto al .exe la carpeta `emuladores\` con `ps2\`, `ps1\` y `psp\`.

### Solo PS1, PS2 y PSP: traer el emulador de tu PS4 (una vez)

Los emuladores de estas consolas son de Sony y no se pueden incluir en la app, pero la app los
copia sola desde un **clásico de esa consola que tengas instalado en tu PS4** (comprado o de
PlayStation Plus): cualquier juego de PS2 para PS4 trae el emulador de PS2, cualquier clásico de
PS1 el de PS1 y cualquier clásico de PSP el de PSP.

1. En la PS4, activa el FTP de GoldHEN: **Ajustes → GoldHEN → Servidor FTP** (puerto 2121).
2. Abre en la PS4 el clásico de esa consola y **déjalo abierto** (puede quedarse en el menú del juego).
3. En la app, en la pestaña de esa consola, pulsa **Traer de mi PS4**, confirma y escribe la IP
   de la PS4 si te la pide (*Ajustes → Red → Ver estado de la conexión*).
4. Espera uno o dos minutos. Al terminar, el campo *Emulador* muestra **✓ Listo** y ya puedes
   cerrar el juego en la PS4.

La app copia solo el emulador (no el juego), descifra sus ejecutables con el FTP de GoldHEN y los
vuelve a firmar para que GoldHEN los abra. Se guarda en `emuladores\ps2\` (o `ps1\` / `psp\`)
junto al .exe y desde entonces se usa solo.

> **Importante:** no se ha podido probar en una PS4. Si un juego creado así no abre, prueba con
> otro clásico como origen del emulador (en PS2 los más compatibles son *Jak and Daxter*,
> *Rogue Galaxy* y *Kinetica*) o copia a mano una carpeta de emulador que ya sepas que funciona.

**Si ya tienes el emulador en un archivo:** usa el botón **Importar…** de la pestaña y elige:
- una **herramienta que lo traiga dentro**: **PSP-FPKG** (PSP), **PSX-FPKG** (PS1) o **PS2-FPKG**
  (PS2, se usa la base *Jak v2*, la más compatible). Puedes elegir su .exe o directamente el
  .7z/.zip en que se descarga; la app saca de ahí el emulador sin ejecutar nada. Si el .7z no se
  abre, instala 7-Zip o descomprímelo primero y elige el .exe de dentro;
- el **.pkg** de un clásico (la app lo extrae);
- un **.zip** o **.7z** con la carpeta del emulador.

La app detecta de qué consola es, descarta el juego que traiga y lo guarda en `emuladores\`.
También puedes copiar a mano una carpeta de emulador (la que tiene `eboot.bin`) con
**Abrir carpeta**.

---

## 3. Crear un fPKG (igual para todas las consolas)

1. Abre la app y elige la **pestaña** de la consola.
2. Agrega el juego (botón **…** o **Agregar…**). La app detecta sola el serial, el nombre y busca
   la **carátula** en internet (se ve a la derecha).
3. Revisa:
   - **Nombre del juego:** es el que aparecerá en el menú de la PS4. Puedes escribir el que quieras.
   - **Carátula:** si no es la que quieres, elige tu propia imagen con **…**. Con ella se hacen el
     icono y el fondo. **Icono propio** y **Fondo propio** son opcionales.
   - **Calidad de imagen y sonido:** ya viene en lo mejor recomendado para cada consola.
4. En **Empaquetado e instalación** elige la **Carpeta de salida** (dónde se guardará el .pkg).
5. Pulsa **Crear fPKG** y espera a que el registro diga `Listo: …pkg` y `Verificación correcta`.

> Cada juego tiene un identificador propio: puedes instalar muchos a la vez. Si vuelves a crear
> el mismo juego y lo instalas, se actualiza el que ya estaba.

---

## 4. Instalar el fPKG en la PS4

### Opción A: por la red (sin USB)

1. PS4 y PC conectadas al **mismo router**.
2. En la PS4 (con GoldHEN activo) abre **Remote Package Installer**.
3. Averigua la IP de la PS4: *Ajustes → Red → Ver estado de la conexión* (por ejemplo `192.168.1.50`).
4. En la app escribe esa **IP de la PS4** y marca **Enviar a la PS4 al terminar** antes de crear el
   fPKG. Si ya lo creaste, usa **Enviar un PKG existente…**.
5. Si Windows pregunta por el firewall, **permite** el acceso (usa el puerto 8000).
6. **No cierres la app** hasta que la PS4 termine de descargar (lo ves en *Notificaciones →
   Descargas* de la PS4).

### Opción B: por USB

1. Formatea la memoria en **exFAT** (en FAT32 no caben archivos de más de 4 GB; la app avisa si el
   juego pesa más).
2. Copia el `.pkg` a la **raíz** de la memoria (no dentro de carpetas).
3. Conéctala a la PS4 y ve a **Ajustes → Debug Settings → Game → Package Installer** (o al
   *Package Installer* de GoldHEN), elige el .pkg y espera a que se instale.

Cuando termina, el juego aparece en el menú de la PS4 con su icono: ábrelo como cualquier juego.

---

## 5. Guía por consola

### PS2

| | |
| --- | --- |
| **Archivo del juego** | `.iso` (juegos en DVD) o `.bin` (juegos en CD: la app lo deja tal cual y le añade el sector LIMG que necesita el emulador). Juegos de varios discos: agrégalos todos, en orden. |
| **Cómo obtenerlo** | Copia tu disco a `.iso` con ImgBurn (*Create image file from disc*) en la PC. |
| **Necesita** | El emulador de PS2: **Traer de mi PS4** (paso 2). |
| **Recomendado** | Perfil **Máxima**, *Pantalla 16:9*, *Sin entrelazado* y *Config. oficial* (ya vienen marcados). |
| **Menú en el juego** | El emulador de PS2 de Sony no tiene menú: guarda desde el propio juego (tarjeta de memoria virtual). |

- Si un juego va lento, cambia a **Rendimiento**. *60 FPS* y *Quitar desenfoque* son opcionales y
  dependen del juego (pueden cambiar su velocidad).
- Para parches de pantalla ancha y la configuración oficial la app necesita **internet** la primera
  vez que convierte cada juego.

### PS1

| | |
| --- | --- |
| **Archivo del juego** | `.cue` + `.bin` (formato en bruto). No sirve `.iso`, `.chd` ni `.pbp`. Varios discos: agrégalos en orden (hasta 5). |
| **Cómo obtenerlo** | ImgBurn → *Create image file from disc*, que crea `.cue` + `.bin`. Si el juego tiene varias pistas `.bin`, deja todas junto al `.cue`: la app las une. |
| **Necesita** | El emulador de PS1: **Traer de mi PS4** (paso 2). |
| **Recomendado** | Perfil **Máxima** (resolución 6x) y *Menú Gráficos* activado. |
| **Menú en el juego** | Botón **OPTIONS**: estados guardados, **rebobinar** y el menú **Gráficos** (filtro y antialiasing). |

- Juegos PAL que van lentos: marca **Forzar 60 Hz**.
- Juegos antiguos sin sticks: **Simular sticks analógicos** permite usar el stick izquierdo.

### PSP

| | |
| --- | --- |
| **Archivo del juego** | `.iso`. Si tienes `.cso`, conviértelo antes a `.iso` (por ejemplo con UMDGen o maxcso). |
| **Cómo obtenerlo** | Desde una PSP con firmware personalizado: *Copiar UMD a ISO* y pásalo por USB. |
| **Necesita** | El emulador de PSP: **Traer de mi PS4**, o **Importar…** con PSP-FPKG.exe (paso 2). |
| **Recomendado** | Perfil **Máxima** (antialiasing SSAA 4x). |
| **Menú en el juego** | El menú del emulador de PlayStation Plus: estados guardados y rebobinar. |

- El icono y el fondo del propio juego se usan si no eliges carátula.
- La app descifra el ejecutable del juego automáticamente (tu ISO original no se modifica).

### NES y SNES

| | |
| --- | --- |
| **Archivo del juego** | NES: `.nes`, `.fds`, `.zip`. SNES: `.sfc`, `.smc`, `.zip`. |
| **Necesita** | Nada (emuladores Nestopia y Snes9x incluidos). |
| **Recomendado** | Imagen **Nítido**. *CRT* si te gusta el aspecto de televisor antiguo. En SNES deja *Sonido sincronizado*. |
| **Menú en el juego** | **L1 + R1**: 4 ranuras de partidas guardadas con miniatura, escalado, filtro, shader, mandos y salir. |

### GBA (y Game Boy / Game Boy Color)

| | |
| --- | --- |
| **Archivo del juego** | `.gba`, `.gb`, `.gbc` o `.zip`. |
| **Necesita** | Nada (emulador mGBA incluido). |
| **Recomendado** | Imagen **Nítido** (o *Píxel exacto* para píxeles perfectos). |
| **Menú en el juego** | **L1 + R1**, igual que NES/SNES. |

### Genesis / Mega Drive (y Master System, Game Gear, SG-1000)

| | |
| --- | --- |
| **Archivo del juego** | Genesis: `.md`, `.gen`, `.smd`, `.bin`. Master System: `.sms`. Game Gear: `.gg`. SG-1000: `.sg`. También `.zip`. |
| **Necesita** | Nada (emulador Genesis Plus GX incluido). |
| **Recomendado** | Imagen **Nítido**; *CRT* queda muy bien en Genesis. |
| **Menú en el juego** | **L1 + R1**, igual que NES/SNES. |

### Dreamcast

| | |
| --- | --- |
| **Archivo del juego** | `.gdi` (con sus pistas `track01.bin`, `track02.raw`… en la misma carpeta), `.chd` (lo mejor: un solo archivo), `.cdi` o `.cue` + `.bin`. |
| **Cómo pasar a .chd** | `chdman createcd -i juego.gdi -o juego.chd` (chdman viene con MAME). |
| **Necesita** | Nada (emulador Resonance, basado en Flycast, incluido). |
| **BIOS (opcional)** | `dc_boot.bin` y `dc_flash.bin` de tu Dreamcast en el campo *BIOS*. Sin ella se usa la BIOS libre de Flycast, que funciona con casi todos los juegos. |
| **Recomendado** | Resolución **Alta (2x)** y *Pantalla ancha* activada (16:9 real en los ~230 juegos con parche; los demás en 4:3). *Máxima (3x)* se ve mejor, pero algunos juegos pueden ir lentos. |
| **Menú en el juego** | **L3 + R3** (o clic en el touchpad): 10 ranuras de estados guardados, trucos, cambio de disco, ajustes de imagen y **cerrar el juego**. |

Controles: X/○/□/△ = A/B/X/Y · L2/R2 = gatillos · OPTIONS = Start · stick izquierdo = stick.
Las memorias VMU y los estados se guardan en `/data/Resonance` de la PS4.

### GameCube / Wii

| | |
| --- | --- |
| **Archivo del juego** | `.rvz` (lo mejor: más pequeño), `.iso`, `.gcm`, `.gcz`, `.ciso`, `.wia`, `.wbfs`; WiiWare `.wad`. Dos discos: agrégalos en orden. |
| **Cómo obtenerlo** | Copia tus discos con una Wii y *CleanRip*; en la PC, Dolphin convierte a `.rvz` (clic derecho → *Convertir archivo*). |
| **Necesita** | Nada (emulador DolphinPS4 incluido). |
| **Calidad** | DolphinPS4 trae ajustes ya probados en PS4; cada juego se puede ajustar en su menú (resolución hasta 3x, filtrado, etc.). |
| **Menú en el juego** | **L3 + R3**: 8 ranuras de estados guardados, todos los ajustes (globales o *solo este juego*), trucos y **salir**. |

Controles GameCube: X = A · □ = B · ○ = X · △ = Y · R1 = Z · L2/R2 = L/R (analógicos) · OPTIONS =
Start · stick derecho = C-stick. En Wii, el touchpad es *Home* y el stick derecho mueve el puntero.
Las tarjetas de memoria y estados se guardan en `/data/DolphinPS4` de la PS4.

- La primera vez que juegas puede haber tirones breves mientras se preparan los *shaders*; se
  guardan y la siguiente vez va fluido.
- GameCube en PS4 es exigente: algunos juegos pesados pueden ir lentos.

### N64 y PS3

**No disponibles:** todavía no existe un emulador de N64 ni de PS3 que funcione en PS4.

---

## 6. Problemas frecuentes

| Problema | Solución |
| --- | --- |
| La app dice **Falta el emulador** (PS1/PS2/PSP) | Usa **Traer de mi PS4** con un clásico de esa consola abierto en la PS4, o **Importar…** si lo tienes en un archivo (paso 2). |
| **Traer de mi PS4** no conecta | FTP de GoldHEN activado (puerto 2121), IP correcta, PS4 y PC en la misma red, y el clásico abierto en la PS4 (no solo instalado). |
| **Remote Package Installer** no recibe nada | PS4 y PC en la misma red; GoldHEN activo; permite la app en el firewall de Windows; revisa la IP. |
| La PS4 dice que **no hay espacio** | Libera espacio: la instalación necesita el tamaño del juego (y algo más mientras se instala). |
| El juego **no aparece** tras instalar por USB | El .pkg debe estar en la raíz de una memoria **exFAT**, no dentro de carpetas. |
| El juego **va lento** | Baja la calidad (PS2: *Rendimiento*; PS1: *Alta*; PSP: *Equilibrado*; Dreamcast: *Alta* o *Nativa*) y vuelve a crear el fPKG; o en Dreamcast/GameCube cámbialo desde el menú L3 + R3. |
| **Pantalla negra** al abrir (PS1/PS2/PSP) | Prueba con otro clásico como emulador (en PS2 los de *Jak and Daxter* o *Rogue Galaxy* son los más compatibles). |
| No encuentra la **carátula** | Escribe bien el nombre y pulsa **Buscar**, o elige tu propia imagen. |
| Quiero **cambiar el nombre o la carátula** | Créalo otra vez con el nuevo nombre/imagen e instálalo encima: se actualiza. |
| Quiero **borrar** un juego | Como cualquier juego de la PS4: botón OPTIONS sobre su icono → *Eliminar*. Las partidas de NES/SNES/GBA/Genesis, Dreamcast y GameCube se quedan en `/data/…`. |
