"""Generate logo QR codes in memory, without fetching the encoded URL."""
from __future__ import annotations

import base64
import io
import math
import re
import warnings
from dataclasses import dataclass
from functools import lru_cache
from urllib.parse import urlsplit
from xml.sax.saxutils import escape

import qrcode
import zxingcpp
from defusedxml import ElementTree
from PIL import Image, ImageDraw, ImageFilter, ImageOps, UnidentifiedImageError
from qrcode.exceptions import DataOverflowError

MAX_LOGO_BYTES = 5 * 1024 * 1024
MAX_LOGO_PIXELS = 16_000_000
SVG_NS = "http://www.w3.org/2000/svg"


@dataclass(frozen=True)
class ScanCheck:
    label: str
    pixels: int
    passed: bool


@dataclass(frozen=True)
class QRResult:
    url: str
    png: bytes
    svg: str
    preview: bytes
    pixels: int
    width: int
    height: int
    module_style: str
    canvas_shape: str
    dpi: int
    requested_logo_percent: int
    used_logo_percent: int
    has_logo: bool
    monochrome: bool
    checks: tuple[ScanCheck, ...]

    @property
    def verified(self) -> bool:
        return all(check.passed for check in self.checks)

    @property
    def logo_reduced(self) -> bool:
        return self.has_logo and self.used_logo_percent < self.requested_logo_percent


def normalize_url(value: str) -> str:
    value = value.strip()
    if not value:
        raise ValueError("Enter a URL to generate your QR code.")
    if any(ch.isspace() or ord(ch) < 32 or ord(ch) == 127 for ch in value):
        raise ValueError("The URL contains spaces or control characters. Use an encoded URL.")
    if "://" not in value:
        value = "https://" + value
    try:
        parts = urlsplit(value)
        if parts.scheme.lower() not in {"http", "https"} or not parts.hostname:
            raise ValueError
        _ = parts.port
        if any(ch in parts.hostname for ch in '\\<>"{}|^`'):
            raise ValueError
        if value.endswith("://"):
            raise ValueError
    except ValueError as exc:
        raise ValueError("Enter a valid http:// or https:// URL.") from exc
    return value


def _deny_external_resource(url: str, resource_type: str) -> bytes:
    raise ValueError("SVG logos must contain their artwork directly, without linked files.")


def _svg_image(raw: bytes) -> Image.Image:
    """Rasterize a self-contained SVG, blocking external resources and XML entities."""
    try:
        root = ElementTree.fromstring(raw)
        if root.tag not in {"svg", f"{{{SVG_NS}}}svg"}:
            raise ValueError("The uploaded XML is not an SVG image.")
        nodes = list(root.iter())
        if len(nodes) > 10_000:
            raise ValueError("This SVG is too complex. Upload a PNG version instead.")
        for node in nodes:
            tag = node.tag.rsplit("}", 1)[-1]
            if tag in {"script", "foreignObject", "image"}:
                raise ValueError("Use an SVG with self-contained vector artwork or upload a PNG.")
            for name, val in node.attrib.items():
                attr = name.rsplit("}", 1)[-1]
                if attr.lower().startswith("on"):
                    raise ValueError("SVG event handlers are not supported.")
                if attr == "href" and not val.startswith("#"):
                    raise ValueError("SVG logos cannot link to external files.")
        vb = root.get("viewBox")
        if vb:
            box = [float(x) for x in re.split(r"[\s,]+", vb.strip())]
            if len(box) != 4:
                raise ValueError("The SVG has an invalid viewBox.")
            width, height = box[2:]
        else:
            def dimension(value: str) -> float:
                match = re.fullmatch(r"\s*([0-9]+(?:\.[0-9]+)?)\s*(px|pt|mm|cm|in)?\s*", value)
                if not match:
                    raise ValueError("Give the SVG a viewBox or fixed width and height.")
                units = {None: 1, "px": 1, "pt": 96/72, "mm": 96/25.4, "cm": 96/2.54, "in": 96}
                return float(match[1]) * units[match[2]]
            width = dimension(root.get("width", "300"))
            height = dimension(root.get("height", "150"))
        if not all(math.isfinite(x) and x > 0 for x in (width, height)):
            raise ValueError("The SVG dimensions must be positive.")
        aspect = width / height
        if not .02 <= aspect <= 50:
            raise ValueError("The SVG is unusually wide or tall. Crop it before uploading.")
        from cairosvg.surface import PNGSurface
        png = PNGSurface.convert(
            bytestring=raw,
            unsafe=False,
            url_fetcher=_deny_external_resource,
            output_width=max(1, round(2048 * min(1, aspect))),
            output_height=max(1, round(2048 * min(1, 1/aspect))),
        )
        return Image.open(io.BytesIO(png)).convert("RGBA")
    except ValueError:
        raise
    except ImportError as exc:
        raise ValueError("SVG support needs CairoSVG. Install requirements.txt, or upload a PNG.") from exc
    except Exception as exc:
        raise ValueError("This SVG could not be read. Export it as a PNG and try again.") from exc


def load_logo(raw: bytes | None) -> Image.Image | None:
    if raw is None:
        return None
    if not raw:
        raise ValueError("The logo file is empty.")
    if len(raw) > MAX_LOGO_BYTES:
        raise ValueError("Choose a logo smaller than 5 MB.")
    if raw.lstrip(b"\xef\xbb\xbf \t\r\n").startswith(b"<"):
        image = _svg_image(raw)
    else:
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("error", Image.DecompressionBombWarning)
                image = Image.open(io.BytesIO(raw))
                if image.format not in {"PNG", "JPEG", "WEBP"}:
                    raise ValueError("Upload a PNG, JPEG, WebP or SVG logo.")
                if image.width * image.height > MAX_LOGO_PIXELS:
                    raise ValueError("Resize the logo to under 16 megapixels before uploading.")
                image = ImageOps.exif_transpose(image).convert("RGBA")
        except (UnidentifiedImageError, OSError, Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
            raise ValueError("This image could not be read. Upload a PNG, JPEG, WebP or SVG logo.") from exc
    crop = image.getchannel("A").getbbox()
    if crop is None:
        raise ValueError("The logo is fully transparent. Choose an image with visible artwork.")
    image = image.crop(crop)
    image.thumbnail((2048, 2048), Image.Resampling.LANCZOS)
    return image


def _placement(matrix: list[list[bool]], logo: Image.Image | None, percent: int, padding: int):
    if logo is None:
        return None
    side = len(matrix)
    longest_edge = (side - 8) * percent / 100
    scale = longest_edge / max(logo.size)
    width, height = logo.width * scale, logo.height * scale
    gap = max(.45, longest_edge * padding / 100)
    return ((side-width)/2, (side-height)/2, width, height, gap)


@lru_cache(maxsize=40)
def _protected_modules(side: int) -> frozenset[tuple[int, int]]:
    """Keep finder, timing and alignment patterns square in every module style."""
    body = side - 8
    version = (body - 17) // 4
    centers = qrcode.util.pattern_position(version)
    protected = set()
    for y in range(side):
        for x in range(side):
            if ((x < 13 and y < 13) or (x >= side-13 and y < 13)
                or (x < 13 and y >= side-13) or x in {10,12} or y in {10,12}
                or any(abs(x-4-cx) <= 2 and abs(y-4-cy) <= 2 for cx in centers for cy in centers)):
                protected.add((x,y))
    return frozenset(protected)


def _render(matrix: list[list[bool]], logo: Image.Image | None, placement, pixels: int, monochrome: bool = False, module_style: str = "square") -> Image.Image:
    image = Image.new("RGB", (pixels, pixels), "white")
    draw = ImageDraw.Draw(image)
    unit = pixels / len(matrix)
    protected = _protected_modules(len(matrix)) if module_style != "square" else frozenset()
    for y, row in enumerate(matrix):
        for x, dark in enumerate(row):
            if dark:
                bounds = (round(x*unit), round(y*unit), round((x+1)*unit)-1, round((y+1)*unit)-1)
                if module_style == "square" or (x,y) in protected:
                    draw.rectangle(bounds, fill="black")
                elif module_style == "rounded":
                    draw.rounded_rectangle(bounds, radius=.3*unit, fill="black")
                else:
                    draw.ellipse(bounds, fill="black")
    if logo is not None and placement is not None:
        x, y, width, height, gap = placement
        draw.rounded_rectangle(
            ((x-gap)*unit, (y-gap)*unit, (x+width+gap)*unit, (y+height+gap)*unit),
            radius=.6*unit, fill="white",
        )
        resampling = Image.Resampling.NEAREST if monochrome else Image.Resampling.LANCZOS
        resized = logo.resize((max(1, round(width*unit)), max(1, round(height*unit))), resampling)
        image.paste(resized, (round(x*unit), round(y*unit)), resized)
    return image


def _scan(image: Image.Image, url: str) -> bool:
    try:
        if image.mode == "RGBA":
            background = Image.new("RGBA", image.size, "white")
            background.alpha_composite(image)
            image = background.convert("RGB")
        code = zxingcpp.read_barcode(image)
        return code is not None and code.text == url
    except (ValueError, RuntimeError):
        return False


def _checks(image: Image.Image, url: str, modules: int, qr_pixels: float | None = None) -> tuple[ScanCheck, ...]:
    factor = max(image.size) / qr_pixels if qr_pixels else 1
    small = max(320, modules*5) * factor
    large = max(640, modules*8) * factor
    samples = [
        ("Smaller image", small, False),
        ("Larger image", large, False),
        ("Mild blur", large, True),
    ]
    checks = []
    for label, pixels, blur in samples:
        width = max(1, round(image.width * pixels / max(image.size)))
        height = max(1, round(image.height * pixels / max(image.size)))
        sample = image.resize((width, height), Image.Resampling.LANCZOS)
        if blur:
            sample = sample.filter(ImageFilter.GaussianBlur(.5))
        checks.append(ScanCheck(label, max(width,height), _scan(sample, url)))
    return tuple(checks)


def _svg(matrix: list[list[bool]], url: str, logo: Image.Image | None, placement, module_style: str = "square") -> str:
    side = len(matrix)
    protected = _protected_modules(side) if module_style != "square" else frozenset()
    paths, styled = [], []
    for y,row in enumerate(matrix):
        for x,dark in enumerate(row):
            if not dark:
                continue
            if module_style == "square" or (x,y) in protected:
                paths.append(f"M{x},{y}h1v1h-1z")
            elif module_style == "rounded":
                styled.append(f'<rect x="{x}" y="{y}" width="1" height="1" rx="0.3"/>')
            else:
                styled.append(f'<circle cx="{x+.5}" cy="{y+.5}" r="0.5"/>')
    path = "".join(paths)
    artwork = ""
    if logo is not None and placement is not None:
        x,y,width,height,gap = placement
        buf = io.BytesIO(); logo.save(buf, format="PNG")
        encoded = base64.b64encode(buf.getvalue()).decode("ascii")
        artwork = (
            f'<rect x="{x-gap:.6f}" y="{y-gap:.6f}" width="{width+2*gap:.6f}" height="{height+2*gap:.6f}" rx="0.6" fill="white"/>'
            f'<image x="{x:.6f}" y="{y:.6f}" width="{width:.6f}" height="{height:.6f}" href="data:image/png;base64,{encoded}"/>'
        )
    return (
        f'<svg xmlns="{SVG_NS}" width="1024" height="1024" viewBox="0 0 {side} {side}" role="img">'
        f'<title>QR code for {escape(url)}</title><rect width="{side}" height="{side}" fill="white"/>'
        f'<g fill="black"><path d="{path}"/>{"".join(styled)}</g>{artwork}</svg>'
    )


def _canvas_geometry(width: int, height: int, shape: str) -> tuple[int,int,int]:
    if shape == "triangle":
        side = max(1,int(.9*width*height/(width+height)))
        return (width-side)//2, int(height-side-.04*min(width,height)), side
    if shape == "circle":
        size = .96 / math.sqrt(1/width**2 + 1/height**2)
    elif shape == "hexagon":
        size = .96 * min(width,height,2*width*height/(2*height+width))
    elif shape == "rounded":
        size = .88 * min(width,height)
    else:
        size = min(width,height)
    side = max(1,int(size))
    return (width-side)//2, (height-side)//2, side


def _canvas_image(qr_image: Image.Image, width: int, height: int, shape: str, box) -> Image.Image:
    if shape == "square":
        canvas = Image.new("RGB", (width,height), "white")
    else:
        canvas = Image.new("RGBA", (width,height), (255,255,255,0))
        draw = ImageDraw.Draw(canvas)
        if shape == "triangle":
            draw.polygon([(width*.5,0),(width-1,height-1),(0,height-1)],fill="white")
        elif shape == "circle":
            draw.ellipse((0,0,width-1,height-1), fill="white")
        elif shape == "rounded":
            draw.rounded_rectangle((0,0,width-1,height-1),radius=.12*min(width,height),fill="white")
        else:
            draw.polygon([(width*.25,0),(width*.75,0),(width-1,height*.5),(width*.75,height-1),(width*.25,height-1),(0,height*.5)],fill="white")
    canvas.paste(qr_image,(box[0],box[1]))
    return canvas


def _canvas_svg(svg: str, width: int, height: int, shape: str, box, modules: int) -> str:
    x,y,side = box
    inner = svg.split(">",1)[1].rsplit("</svg>",1)[0]
    if shape == "triangle":
        background = f'<polygon points="{width/2},0 {width},{height} 0,{height}" fill="white"/>'
    elif shape == "circle":
        background = f'<ellipse cx="{width/2}" cy="{height/2}" rx="{width/2}" ry="{height/2}" fill="white"/>'
    elif shape == "hexagon":
        points = f'{width*.25},0 {width*.75},0 {width},{height*.5} {width*.75},{height} {width*.25},{height} 0,{height*.5}'
        background = f'<polygon points="{points}" fill="white"/>'
    else:
        radius = .12*min(width,height) if shape == "rounded" else 0
        background = f'<rect width="{width}" height="{height}" rx="{radius}" fill="white"/>'
    return (f'<svg xmlns="{SVG_NS}" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img">'
            f'{background}<svg x="{x}" y="{y}" width="{side}" height="{side}" viewBox="0 0 {modules} {modules}">{inner}</svg></svg>')


def generate_qr(
    url: str,
    logo_bytes: bytes | None = None,
    logo_percent: int = 18,
    padding_percent: int = 12,
    pixels: int = 4096,
    dpi: int = 600,
    auto_reduce: bool = True,
    monochrome: bool = False,
    bw_threshold: int = 170,
    width: int | None = None,
    height: int | None = None,
    module_style: str = "square",
    canvas_shape: str = "square",
) -> QRResult:
    url = normalize_url(url)
    width = width if width is not None else pixels
    height = height if height is not None else width
    if not 8 <= logo_percent <= 28:
        raise ValueError("Choose a logo size between 8% and 28%.")
    if not 0 <= padding_percent <= 30:
        raise ValueError("Choose logo padding between 0% and 30%.")
    if not 512 <= width <= 8000 or not 512 <= height <= 8000 or width*height > 36_000_000:
        raise ValueError("Choose dimensions from 512 to 8000 px, with at most 36 million pixels in total.")
    if not 72 <= dpi <= 1200:
        raise ValueError("Choose a print resolution from 72 to 1200 dpi.")
    if module_style not in {"square","rounded","dots"} or canvas_shape not in {"square","rounded","circle","hexagon","triangle"}:
        raise ValueError("Choose a supported QR style and canvas shape.")
    if not 1 <= bw_threshold <= 254:
        raise ValueError("Choose a black-and-white threshold between 1 and 254.")
    if len(url.encode("utf-8")) > 1273:
        raise ValueError("This URL is too long for a QR code with high error correction. Use a shorter URL.")
    logo = load_logo(logo_bytes)
    if logo is not None and monochrome:
        # Flatten transparency onto the QR's white center before thresholding.
        background = Image.new("RGBA", logo.size, "white")
        background.alpha_composite(logo)
        logo = ImageOps.grayscale(background).point(lambda x: 255 if x >= bw_threshold else 0).convert("RGBA")
    qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_H, border=4, box_size=1)
    qr.add_data(url, optimize=0)
    try:
        qr.make(fit=True)
    except (DataOverflowError, ValueError) as exc:
        raise ValueError("This URL is too long. Use a shorter URL and try again.") from exc
    matrix = qr.get_matrix()
    percentages = [logo_percent]
    if logo is not None and auto_reduce:
        percentages += list(range(logo_percent-2, 5, -2))
    for used in percentages:
        placement = _placement(matrix, logo, used, padding_percent)
        sample = _render(matrix, logo, placement, max(1024, len(matrix)*10), monochrome, module_style)
        checks = _checks(sample, url, len(matrix))
        if all(c.passed for c in checks):
            break
    box = _canvas_geometry(width,height,canvas_shape)
    qr_image = _render(matrix, logo, placement, box[2], monochrome, module_style)
    image = _canvas_image(qr_image,width,height,canvas_shape,box)
    # Verify downscaled samples of the actual downloadable PNG as well.
    checks = _checks(image, url, len(matrix), box[2])
    png = io.BytesIO(); image.save(png, format="PNG", dpi=(dpi,dpi))
    preview = io.BytesIO()
    image.thumbnail((900,900),Image.Resampling.NEAREST)
    image.save(preview,format="PNG")
    svg = _canvas_svg(_svg(matrix,url,logo,placement,module_style),width,height,canvas_shape,box,len(matrix))
    return QRResult(
        url=url, png=png.getvalue(), svg=svg, preview=preview.getvalue(),
        pixels=max(width,height), width=width, height=height, module_style=module_style, canvas_shape=canvas_shape,
        dpi=dpi, requested_logo_percent=logo_percent,
        used_logo_percent=used if logo is not None else 0, has_logo=logo is not None,
        monochrome=monochrome and logo is not None, checks=checks,
    )
