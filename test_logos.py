import base64
import io
import json
from pathlib import Path
from xml.etree import ElementTree

import pytest
import zxingcpp
from fastapi.testclient import TestClient
from PIL import Image, ImageDraw

from qr_engine import generate_qr, prepare_logo
from qr_exports import FORMATS, export_file, flatten_white
from web_app import create_app

ASSETS = Path(__file__).parent / "static" / "logos"
CATALOG = json.loads((ASSETS / "catalog.json").read_text())


def white_backed_logo():
    image = Image.new("RGBA", (80, 80), "white")
    draw = ImageDraw.Draw(image)
    draw.rectangle((10, 10, 69, 69), fill=(30, 60, 180, 255))
    draw.rectangle((30, 30, 49, 49), fill="white")
    draw.rectangle((10, 10, 19, 19), fill=(245, 245, 245, 128))
    data = io.BytesIO()
    image.save(data, format="PNG")
    return data.getvalue()


def embedded_logo(svg):
    root = ElementTree.fromstring(svg)
    node = root.find(".//{http://www.w3.org/2000/svg}image")
    return node, Image.open(io.BytesIO(base64.b64decode(node.get("href").split(",", 1)[1])))


@pytest.mark.parametrize("preset", CATALOG, ids=lambda item: item["id"])
@pytest.mark.parametrize("monochrome", [False, True])
def test_bundled_logos_scan_in_color_and_black_and_white(preset, monochrome):
    raw = (ASSETS / preset["file"]).read_bytes()
    result = generate_qr("https://example.com/preset", raw, pixels=1024, monochrome=monochrome)
    assert result.verified and result.has_logo
    assert zxingcpp.read_barcode(Image.open(io.BytesIO(result.png))).text == result.url
    if monochrome:
        _, artwork = embedded_logo(result.svg)
        white = Image.new("RGBA", artwork.size, "white")
        white.alpha_composite(artwork)
        assert white.convert("L").getextrema() == (0, 255)


def test_white_removal_tolerance_preserves_color_and_existing_alpha():
    raw = white_backed_logo()
    exact = prepare_logo(raw, remove_white_background=True, white_tolerance=0)
    assert exact.size == (60, 60)
    assert exact.getpixel((25, 25))[3] == 0  # Inner white detail is removed too.
    assert exact.getpixel((5, 5))[3] == 128  # Near-white remains at tolerance 0.
    tolerant = prepare_logo(raw, remove_white_background=True, white_tolerance=20, logo_opacity=50)
    assert tolerant.getpixel((5, 5))[3] == 0
    assert tolerant.getpixel((15, 15)) == (30, 60, 180, 128)
    original = prepare_logo(raw)
    assert original.size == (80, 80) and original.getpixel((0, 0))[3] == 255


def test_monochrome_keeps_white_key_transparent_and_opacity_is_embedded():
    result = generate_qr("https://example.com", white_backed_logo(), pixels=1024,
                         monochrome=True, remove_white_background=True, logo_opacity=35)
    _, image = embedded_logo(result.svg)
    assert image.mode == "RGBA"
    assert image.getchannel("A").getextrema() == (0, 89)
    assert {color for _, color in image.convert("RGB").getcolors(2)} <= {(0, 0, 0), (255, 255, 255)}
    assert result.verified and result.logo_opacity == 35 and result.remove_white_background


def test_zero_opacity_removes_logo_space_entirely():
    plain = generate_qr("https://example.com", pixels=1024)
    hidden = generate_qr("https://example.com", white_backed_logo(), pixels=1024, logo_opacity=0)
    assert hidden.png == plain.png and hidden.svg == plain.svg
    assert hidden.logo_opacity == 0 and not hidden.has_logo


def test_logo_size_changes_embedded_dimensions_and_keeps_center():
    raw = (ASSETS / "github.svg").read_bytes()
    small = generate_qr("https://example.com", raw, pixels=1024, logo_percent=10, auto_reduce=False)
    large = generate_qr("https://example.com", raw, pixels=1024, logo_percent=20, auto_reduce=False)
    a, _ = embedded_logo(small.svg)
    b, _ = embedded_logo(large.svg)
    assert float(b.get("width")) == pytest.approx(2 * float(a.get("width")), abs=1e-5)
    for axis, dimension in [("x", "width"), ("y", "height")]:
        center_a = float(a.get(axis)) + float(a.get(dimension)) / 2
        center_b = float(b.get(axis)) + float(b.get(dimension)) / 2
        assert center_a == pytest.approx(center_b, abs=1e-5)
    assert small.verified and large.verified


def test_empty_white_removal_and_invalid_controls_have_actionable_errors():
    data = io.BytesIO()
    Image.new("RGB", (20, 20), "white").save(data, format="PNG")
    with pytest.raises(ValueError, match="no visible artwork"):
        generate_qr("https://example.com", data.getvalue(), remove_white_background=True)
    for options in [{"logo_opacity": -1}, {"logo_opacity": 101}, {"white_tolerance": 101}]:
        with pytest.raises(ValueError, match="between 0 and 100"):
            generate_qr("https://example.com", **options)


def test_preset_api_and_static_assets_and_no_logo_override():
    with TestClient(create_app()) as client:
        presets = client.get("/api/logos").json()
        assert {item["id"] for item in presets} == {item["id"] for item in CATALOG}
        for preset in presets:
            response = client.get(preset["src"])
            assert response.status_code == 200 and "<svg" in response.text
        values = {"url": "https://example.com", "pixels": 1024, "builtin_logo": "huggingface",
                  "logo_opacity": 65, "remove_white_background": "true", "logo_percent": 22}
        response = client.post("/api/generate", data=values)
        assert response.status_code == 200, response.text
        data = response.json()
        assert data["has_logo"] and data["verified"] and data["logo_opacity"] == 65
        assert data["requested_logo_percent"] == 22 and data["remove_white_background"]
        assert client.post("/api/export", data={**values, "format": "svg"}).text == data["svg"]
        response = client.post("/api/generate", data={**values, "builtin_logo": "../../README.md"})
        assert response.status_code == 422
        response = client.post("/api/generate", data=values,
                               files={"logo": ("logo.png", white_backed_logo(), "image/png")})
        assert response.status_code == 422
        response = client.post("/api/generate", data={**values, "logo_mode": "none", "builtin_logo": "invalid"},
                               files={"logo": ("ignored.png", b"invalid", "image/png")})
        assert response.status_code == 200 and not response.json()["has_logo"]
        for invalid in [{"logo_opacity": 101}, {"white_tolerance": -1}]:
            assert client.post("/api/generate", data={**values, **invalid}).status_code == 422


@pytest.mark.parametrize("kind", list(FORMATS))
def test_every_export_scans_with_transparent_resized_faded_logo(kind):
    result = generate_qr("https://example.com/transparency", white_backed_logo(),
                         pixels=1024, logo_percent=24, logo_opacity=50,
                         remove_white_background=True, canvas_shape="rounded")
    content = export_file(result, kind)
    if kind == "svg":
        from cairosvg import svg2png
        _, logo = embedded_logo(content)
        assert logo.getchannel("A").getextrema() == (0, 128)
        image = Image.open(io.BytesIO(svg2png(bytestring=content)))
    elif kind == "pdf":
        import fitz
        pdf = fitz.open(stream=content, filetype="pdf")
        page = pdf[0].get_pixmap(matrix=fitz.Matrix(600/72, 600/72))
        image = Image.frombytes("RGB", (page.width, page.height), page.samples)
    else:
        image = Image.open(io.BytesIO(content))
    assert zxingcpp.read_barcode(flatten_white(image)).text == result.url
