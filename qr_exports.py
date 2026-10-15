"""Export only when requested, so large BMP/TIFF files do not slow the preview."""
from __future__ import annotations
import io
import zipfile
from PIL import Image
from qr_engine import QRResult

FORMATS = {
    "png": ("PNG", "image/png"),
    "jpg": ("JPEG", "image/jpeg"),
    "webp": ("WebP", "image/webp"),
    "svg": ("SVG", "image/svg+xml"),
    "pdf": ("PDF", "application/pdf"),
    "tiff": ("TIFF", "image/tiff"),
    "bmp": ("BMP", "image/bmp"),
    "gif": ("GIF", "image/gif"),
}


def flatten_white(image: Image.Image) -> Image.Image:
    if image.mode == "RGBA":
        background = Image.new("RGBA", image.size, "white")
        background.alpha_composite(image)
        return background.convert("RGB")
    return image.convert("RGB")


def export_file(result: QRResult, kind: str) -> bytes:
    kind = {"jpeg":"jpg", "tif":"tiff"}.get(kind.lower(),kind.lower())
    if kind not in FORMATS:
        raise ValueError("Choose PNG, JPEG, WebP, SVG, PDF, TIFF, BMP or GIF.")
    if kind == "png":
        return result.png
    if kind == "svg":
        return result.svg.encode()
    if kind == "pdf":
        from cairosvg import svg2pdf
        return svg2pdf(bytestring=result.svg.encode(),dpi=result.dpi)
    image = Image.open(io.BytesIO(result.png))
    output = io.BytesIO()
    if kind == "jpg":
        flatten_white(image).save(output,format="JPEG",quality=98,subsampling=0,dpi=(result.dpi,result.dpi))
    elif kind == "webp":
        exif = Image.Exif()
        exif[282], exif[283], exif[296] = result.dpi, result.dpi, 2
        image.save(output,format="WEBP",lossless=True,quality=100,method=4,exif=exif.tobytes())
    elif kind == "tiff":
        image.save(output,format="TIFF",compression="tiff_lzw",dpi=(result.dpi,result.dpi))
    elif kind == "bmp":
        flatten_white(image).save(output,format="BMP",dpi=(result.dpi,result.dpi))
    else:
        flatten_white(image).convert("P",palette=Image.Palette.ADAPTIVE,colors=256,dither=Image.Dither.NONE).save(output,format="GIF")
    return output.getvalue()


def export_bundle(result: QRResult, stem: str) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output,"w",compression=zipfile.ZIP_DEFLATED) as archive:
        for kind in FORMATS:
            archive.writestr(stem+"."+kind,export_file(result,kind))
    return output.getvalue()
