# QR Studio

A web app that accepts a URL and an optional center logo, checks the complete QR code, and exports PNG, JPEG, WebP, SVG, PDF, TIFF, BMP and GIF. Built with FastAPI and a small HTML/CSS/JavaScript frontend. Run it locally or deploy it to Modal.

## Setup

Use Python 3.11 or newer (Python 3.12 is used by the Modal image). Clone the repository and create a virtual environment:

```bash
git clone https://github.com/aflah02/qr-studio.git
cd qr-studio
python -m venv .venv
```

On macOS or Linux, use `python3` if `python` is not available. Activate the environment using the command for your shell.

**Windows Command Prompt:**

```cmd
.venv\Scripts\activate.bat
```

**Windows PowerShell:**

```powershell
.venv\Scripts\Activate.ps1
```

**macOS / Linux:**

```bash
source .venv/bin/activate
```

Run the commands below from the repository root with the environment activated.

## Run locally

Install the Python dependencies and start the development server:

```bash
python -m pip install -r requirements.txt
python -m uvicorn web_app:create_app --factory --reload
```

Open [http://127.0.0.1:8000](http://127.0.0.1:8000). Press `Ctrl+C` to stop the server. Local use does not require a Modal account.

### Cairo for logos and PDF export

Built-in logos, uploaded SVG logos, PDF export and the all-formats ZIP need the Cairo system library in addition to the Python packages. Install it before using those features. Plain codes and PNG/JPEG/WebP uploads with raster exports work without it.

**Debian / Ubuntu:**

```bash
sudo apt-get update
sudo apt-get install libcairo2
```

**macOS (Homebrew):**

```bash
brew install cairo
```

**Windows (64-bit):**

1. Install [MSYS2](https://www.msys2.org/) using its default location, `C:\msys64`.
2. Open **MSYS2 UCRT64** from the Start menu and install [Cairo](https://packages.msys2.org/packages/mingw-w64-ucrt-x86_64-cairo):

   ```bash
   pacman -S --needed mingw-w64-ucrt-x86_64-cairo
   ```

3. Return to your activated Python environment in **Windows Command Prompt** and set the DLL directory before starting the server:

   ```cmd
   set "CAIROCFFI_DLL_DIRECTORIES=C:\msys64\ucrt64\bin"
   set "PATH=C:\msys64\ucrt64\bin;%PATH%"
   python -m uvicorn web_app:create_app --factory --reload
   ```

   In **PowerShell**, use:

   ```powershell
   $env:CAIROCFFI_DLL_DIRECTORIES = "C:\msys64\ucrt64\bin"
   $env:PATH = "C:\msys64\ucrt64\bin;$env:PATH"
   python -m uvicorn web_app:create_app --factory --reload
   ```

These environment settings apply to the current terminal; repeat them in a new terminal. Adjust the paths if MSYS2 is installed elsewhere. See the [CairoSVG installation documentation](https://cairosvg.org/documentation/) for other platforms.

## Deploy to Modal

After the shared setup above, install the Modal CLI, authenticate and deploy:

```bash
python -m pip install "modal>=1.0,<2"
modal setup
modal deploy app.py
```

Skip `modal setup` if already authenticated. Modal builds the container, installs Cairo and the Python dependencies, and prints the deployed web URL. Local Cairo installation and the local server are not needed for this route. No application API keys or database are needed. The deployed endpoint is publicly accessible by default.

For a temporary deployment that reloads code during development:

```bash
modal serve app.py
```

`app.py` defines the Modal image and endpoint. It includes `qr_engine.py`, `qr_exports.py`, `web_app.py` and the `static/` directory in the container automatically. Keep these files together.

## Use

Paste a URL, click a **built-in logo** (arXiv, GitHub, Hugging Face, Google Scholar, ORCID or YouTube), or upload your own image. Built-in assets are bundled with the app and need no remote image service. See [logo sources](THIRD_PARTY_LOGOS.md). Then choose a **Logo style**:

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

Under **Adjust logo**:

- **Logo size inside QR:** 8–28% of the QR pattern width, with aspect ratio preserved. Automatic scan protection may reduce the size and reports the size actually used.
- **Logo opacity:** 0–100%. Lower values fade the logo against the white center; 0% removes the logo and its reserved space entirely.
- **Make white pixels transparent:** removes white and near-white areas, including white details within the logo. Tolerance 0 removes only pure white; higher values include more near-white colors. Existing transparency is preserved. The QR's white center remains for contrast.
- **Space around logo:** adjusts the white padding around the artwork.

Black-and-white conversion normalizes brightness before thresholding so pale brand colors remain visible, and preserves transparent areas. At opacity below 100%, the logo appears in gray tones as it blends with the white center. All controls apply to uploaded and built-in logos, and the same processed artwork is used in every export format.

## Tests

```bash
pip install -r requirements-dev.txt
python -m pytest -q
```

Tests cover QR destinations, upload formats, different logo proportions, explicit logo-free output, built-in logo assets, opacity, white removal, black-and-white conversion, every QR style/canvas shape combination, all eight export types, custom dimensions and DPI, PDF page dimensions, ZIP contents, static assets, API error handling and the Modal entry point.

## API

`POST /api/generate` accepts multipart form data:

| Field | Default | Description |
| --- | --- | --- |
| `url` | Required | HTTP or HTTPS destination |
| `logo` | Omitted | PNG, JPEG, WebP or SVG file |
| `builtin_logo` | Omitted | `arxiv`, `github`, `huggingface`, `googlescholar`, `orcid` or `youtube`; use instead of `logo` |
| `logo_opacity` | 100 | 0–100%; 0 creates a plain QR code |
| `remove_white_background` | false | Make white and near-white pixels transparent, including white details |
| `white_tolerance` | 20 | White removal tolerance, 0–100 |
| `logo_mode` | with_logo | `none` ignores uploaded and built-in logos; `with_logo` uses the selected logo |
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

`GET /api/logos` returns the built-in logo IDs, labels and local asset URLs. An unknown ID or simultaneous upload and preset is rejected unless `logo_mode=none`.

Interactive API documentation is available at `/docs`; health status is at `/health`.
