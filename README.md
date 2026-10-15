# QR Studio for Modal

A web app that accepts a URL and an optional center logo, checks the complete QR code, and exports PNG, JPEG, WebP, SVG, PDF, TIFF, BMP and GIF. The interface uses FastAPI and a small HTML/CSS/JavaScript frontend. Modal serves the UI and API together.

## Deploy to Modal

Use Python 3.11 or newer. Clone the repository and deploy from its root:

```bash
git clone https://github.com/aflah02/qr-code-maker.git
cd qr-code-maker
python -m venv .venv
source .venv/bin/activate
pip install 'modal>=1.0,<2'
modal setup
modal deploy app.py
```

On Windows, activate with `.venv\Scripts\activate` instead. Skip `modal setup` if already authenticated. Modal builds the container, installs Cairo and the Python dependencies, and prints the deployed web URL. No application API keys or database are needed. The deployed endpoint is publicly accessible by default.

For a temporary deployment that reloads code during development:

```bash
modal serve app.py
```

`app.py` defines the Modal image and endpoint. It includes `qr_engine.py`, `qr_exports.py`, `web_app.py` and the `static/` directory in the container automatically. Keep these files together.

## Use

Paste a URL and choose a **Logo style**:

- **No logo** generates a plain QR code, even if you previously uploaded a logo.
- **Original color** preserves the uploaded logo's colors.
- **Black and white** converts a colored logo to pure black and white in the PNG and SVG downloads. Adjust **Black-and-white contrast** to retain the details you want. A higher value makes more of the logo black.

For the two logo styles, upload a PNG, JPEG, WebP or self-contained SVG up to 5 MB. Switching to **No logo** hides the upload controls and excludes the logo. Switching back restores the selected file.

The preview updates after changes. **Customize output** offers:

- **QR pattern style:** squares, rounded squares or dots. Finder, timing and alignment patterns remain square for scanning.
- **Canvas shape:** square/rectangle, rounded rectangle, circle/oval, hexagon or triangle. The full QR code and its white margin fit inside the shape.
- **Dimensions:** presets at 1024, 2048, 4096 or 6000 pixels, or custom width and height from 512 to 8000 pixels per edge, up to 36 megapixels in total. Rectangular canvases keep the QR pattern square and centered. Triangle canvases place the code lower so it fits inside the outline.
- **Print resolution:** any integer from 72 to 1200 dpi. The preview reports the corresponding size in millimeters.

Select an **Export format** and download the file, or download all eight formats as one ZIP. Larger formats are generated when requested, so they do not slow down the preview.

| Export | Details |
| --- | --- |
| PNG | Lossless, with alpha transparency and DPI metadata |
| JPEG (.jpg) | High quality, white background and DPI metadata |
| WebP | Lossless, alpha transparency and resolution in EXIF metadata |
| SVG | Vector QR modules with an embedded PNG logo |
| PDF | Vector QR modules with an embedded logo and page size derived from pixels/DPI |
| TIFF | Lossless LZW compression, transparency and DPI metadata |
| BMP | Uncompressed RGB on white, with resolution metadata |
| GIF | Static image with a 256-color palette on white |

PNG, WebP, TIFF and SVG preserve transparent outer corners for shaped canvases. JPEG, BMP and GIF flatten those areas onto white. GIF does not carry standard print DPI metadata. All formats preserve the chosen pixel dimensions where applicable. SVG and PDF retain scalable QR geometry.

The longest logo edge determines its size. Proportions and transparency are preserved, with white padding behind the artwork. Plain QR codes work when no logo is supplied. URLs without a scheme get `https://` automatically.

Codes use error correction H and a four-module white margin. The final composite is decoded at two image sizes and with mild blur. Automatic logo reduction is enabled by default and reports any adjustment. A warning appears if the scan checks still fail. Verify the final printed size with a phone and keep the white margin intact.

SVG downloads contain vector QR modules and an embedded PNG logo. Uploaded SVG logos are rendered at up to 2048 pixels before embedding. The image build includes Cairo for this conversion.

The app does not fetch destination URLs, use redirects or create shortened links. Uploads and generated files are processed for the request and are not saved persistently. SVG logos cannot load external resources. The browser retains its current downloads until the inputs change or the page is closed.

## Run locally

```bash
pip install -r requirements.txt
uvicorn web_app:create_app --factory --reload
```

Open `http://127.0.0.1:8000`. For local SVG support, install Cairo (`libcairo2` on Debian/Ubuntu or `brew install cairo` on macOS). PNG, JPEG and WebP work without the Cairo system library. Modal installs Cairo automatically, so no local Cairo installation is needed to deploy.

## Tests

```bash
pip install -r requirements-dev.txt
python -m pytest -q
```

Tests cover QR destinations, upload formats, different logo proportions, explicit logo-free output, black-and-white conversion, every QR style/canvas shape combination, all eight export types, custom dimensions and DPI, PDF page dimensions, ZIP contents, static assets, API error handling and the Modal entry point.

## API

`POST /api/generate` accepts multipart form data:

| Field | Default | Description |
| --- | --- | --- |
| `url` | Required | HTTP or HTTPS destination |
| `logo` | Omitted | PNG, JPEG, WebP or SVG file |
| `logo_mode` | with_logo | `none` ignores the logo, `with_logo` uses an uploaded logo if present |
| `monochrome` | false | Convert the logo to pure black and white |
| `bw_threshold` | 170 | Black-and-white conversion threshold, 1–254 |
| `logo_percent` | 18 | Longest logo edge, 8–28% of QR pattern width |
| `padding_percent` | 12 | Padding relative to the logo size, 0–30% |
| `pixels` | 4096 | Default side length, 512–8000 |
| `width` | Omitted | Custom width, 512–8000, overrides `pixels` |
| `height` | Width | Custom height, 512–8000; total area must be at most 36 megapixels |
| `dpi` | 600 | Print resolution, 72–1200 |
| `module_style` | square | `square`, `rounded` or `dots` |
| `canvas_shape` | square | `square`, `rounded`, `circle`, `hexagon` or `triangle` |
| `auto_reduce` | true | Reduce the logo if needed for scan checks |

The JSON response includes the normalized destination, actual width/height, verification checks, a preview, the PNG and a PNG+SVG ZIP as base64, and the SVG as text. These original fields remain available for API compatibility.

`POST /api/export` accepts the same fields plus `format`: `png`, `jpg`, `webp`, `svg`, `pdf`, `tiff`, `bmp`, `gif`, or `zip`. `jpeg` and `tif` are accepted aliases. The response is the file itself, with an attachment filename. ZIP exports contain all eight formats.

Interactive API documentation is available at `/docs`; health status is at `/health`.
