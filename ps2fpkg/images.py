"""Imágenes del menú de PS4: icon0.png (512x512) y pic0/pic1.png (1920x1080)."""

import io
import struct
import zlib

ICON_SIZE = (512, 512)
BG_SIZE = (1920, 1080)

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:  # Pillow es opcional
    Image = None


def png_size(path):
    with open(path, "rb") as f:
        head = f.read(24)
    if head[:8] != b"\x89PNG\r\n\x1a\n":
        return None
    return struct.unpack(">II", head[16:24])


def _png_bytes(width, height, row_fn):
    raw = bytearray()
    for y in range(height):
        raw += b"\x00" + row_fn(y)

    def chunk(tag, data):
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data))

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", zlib.compress(bytes(raw), 9)) + chunk(b"IEND", b"")


def _gradient(width, height):
    top, bottom = (24, 34, 74), (6, 8, 20)

    def row(y):
        t = y / max(1, height - 1)
        px = bytes(round(a + (b - a) * t) for a, b in zip(top, bottom))
        return px * width

    return _png_bytes(width, height, row)


def _load_font(size):
    for name in ("DejaVuSans-Bold.ttf", "arialbd.ttf", "Arial Bold.ttf", "Helvetica.ttc"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    try:
        return ImageFont.load_default(size)
    except TypeError:  # Pillow < 10.1
        return ImageFont.load_default()


def _placeholder_pil(size, title, subtitle):
    img = Image.open(io.BytesIO(_gradient(*size))).convert("RGB")
    draw = ImageDraw.Draw(img)
    w, h = size
    font_px, small_px = max(16, h // 9), max(12, h // 18)
    font, small = _load_font(font_px), _load_font(small_px)
    # Ajuste de línea simple para títulos largos.
    words, lines, line = title.split(), [], ""
    for word in words:
        test = f"{line} {word}".strip()
        if draw.textlength(test, font=font) > w * 0.86 and line:
            lines.append(line)
            line = word
        else:
            line = test
    if line:
        lines.append(line)
    line_h = font_px * 1.2
    y = h / 2 - line_h * len(lines) / 2 - small_px
    for ln in lines:
        draw.text((w / 2, y), ln, font=font, fill=(240, 240, 250), anchor="mt")
        y += line_h
    draw.text((w / 2, y + small_px * 0.6), subtitle, font=small, fill=(150, 160, 200), anchor="mt")
    return img


def make(dst, size, source=None, title="", subtitle="PlayStation 2", fit="cover"):
    """Crea un PNG del tamaño pedido a partir de `source` o un marcador con el título.
    fit="cover" llena el espacio recortando; "contain" muestra la imagen entera sobre un fondo."""
    if source:
        if Image is not None:
            img = Image.open(source).convert("RGB")
            img = _cover(img, size) if fit == "cover" else _contain(img, size)
            img.save(dst, "PNG")
            return
        if source.lower().endswith(".png") and png_size(source) == size:
            with open(source, "rb") as f, open(dst, "wb") as out:
                out.write(f.read())
            return
        raise ValueError(
            f"{source}: sin Pillow solo se aceptan PNG de {size[0]}x{size[1]} exactos. "
            "Instala Pillow (pip install pillow) para redimensionar automáticamente."
        )
    if Image is not None:
        _placeholder_pil(size, title, subtitle).save(dst, "PNG")
    else:
        with open(dst, "wb") as out:
            out.write(_gradient(*size))


def _cover(img, size):
    """Escala y recorta al centro para llenar `size` sin deformar."""
    tw, th = size
    scale = max(tw / img.width, th / img.height)
    img = img.resize((max(tw, round(img.width * scale)), max(th, round(img.height * scale))), Image.LANCZOS)
    left, top = (img.width - tw) // 2, (img.height - th) // 2
    return img.crop((left, top, left + tw, top + th))


def _contain(img, size):
    """Escala la imagen entera dentro de `size`, centrada sobre el degradado."""
    tw, th = size
    scale = min(tw / img.width, th / img.height)
    img = img.resize((max(1, round(img.width * scale)), max(1, round(img.height * scale))), Image.LANCZOS)
    canvas = Image.open(io.BytesIO(_gradient(tw, th))).convert("RGB")
    canvas.paste(img, ((tw - img.width) // 2, (th - img.height) // 2))
    return canvas


def _backdrop(img, size, blur, darken):
    """La imagen llenando `size`, desenfocada y oscurecida (fondo a juego con la carátula)."""
    from PIL import ImageEnhance, ImageFilter
    bg = _cover(img, size).filter(ImageFilter.GaussianBlur(blur))
    return ImageEnhance.Brightness(bg).enhance(darken)


def _shadow(canvas, box, radius=18, opacity=150):
    from PIL import ImageFilter
    shadow = Image.new("L", canvas.size, 0)
    ImageDraw.Draw(shadow).rectangle(box, fill=opacity)
    shadow = shadow.filter(ImageFilter.GaussianBlur(radius))
    canvas.paste((0, 0, 0), (0, 0), shadow)


def icon_from_cover(src, dst, size=ICON_SIZE):
    """Icono cuadrado: la carátula entera sobre una versión desenfocada de sí misma."""
    img = Image.open(src).convert("RGB")
    canvas = _backdrop(img, size, blur=18, darken=0.55)
    inner = (round(size[0] * 0.9), round(size[1] * 0.9))
    scale = min(inner[0] / img.width, inner[1] / img.height)
    fg = img.resize((max(1, round(img.width * scale)), max(1, round(img.height * scale))), Image.LANCZOS)
    pos = ((size[0] - fg.width) // 2, (size[1] - fg.height) // 2)
    _shadow(canvas, (pos[0] + 6, pos[1] + 8, pos[0] + fg.width + 6, pos[1] + fg.height + 8), radius=10)
    canvas.paste(fg, pos)
    canvas.save(dst, "PNG")


def background_from_cover(src, dst, size=BG_SIZE):
    """Fondo de pantalla: la carátula desenfocada de fondo y nítida a la derecha."""
    img = Image.open(src).convert("RGB")
    canvas = _backdrop(img, size, blur=40, darken=0.45)
    height = round(size[1] * 0.78)
    fg = img.resize((max(1, round(img.width * height / img.height)), height), Image.LANCZOS)
    if fg.width > size[0] * 0.45:  # carátulas apaisadas
        width = round(size[0] * 0.45)
        fg = img.resize((width, max(1, round(img.height * width / img.width))), Image.LANCZOS)
    pos = (round(size[0] * 0.74 - fg.width / 2), (size[1] - fg.height) // 2)
    _shadow(canvas, (pos[0] + 10, pos[1] + 14, pos[0] + fg.width + 10, pos[1] + fg.height + 14), radius=22)
    canvas.paste(fg, pos)
    canvas.save(dst, "PNG")
