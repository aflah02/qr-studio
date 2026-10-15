"""Local preview: uvicorn web_app:create_app --factory --reload"""
from __future__ import annotations
import base64
import io
import json
import os
import re
import zipfile
from dataclasses import asdict
from pathlib import Path
from typing import Annotated, Literal
from urllib.parse import urlsplit
from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool
from qr_engine import MAX_LOGO_BYTES, generate_qr
from qr_exports import FORMATS, export_bundle, export_file


def _generate_payload(**options) -> dict:
    result = generate_qr(**options)
    host = urlsplit(result.url).hostname or "code"
    stem = "qr_" + (re.sub(r"[^A-Za-z0-9_-]", "_", host)[:70] or "code")
    bundle = io.BytesIO()
    with zipfile.ZipFile(bundle, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(stem + ".png", result.png)
        archive.writestr(stem + ".svg", result.svg)
    return {
        "url": result.url, "filename": stem,
        "preview_base64": base64.b64encode(result.preview).decode("ascii"),
        "png_base64": base64.b64encode(result.png).decode("ascii"),
        "svg": result.svg,
        "zip_base64": base64.b64encode(bundle.getvalue()).decode("ascii"),
        "pixels": result.pixels, "dpi": result.dpi, "has_logo": result.has_logo,
        "width": result.width, "height": result.height,
        "module_style": result.module_style, "canvas_shape": result.canvas_shape,
        "formats": [{"value":key,"label":value[0]} for key,value in FORMATS.items()],
        "monochrome": result.monochrome,
        "logo_opacity": result.logo_opacity,
        "remove_white_background": result.remove_white_background,
        "verified": result.verified, "logo_reduced": result.logo_reduced,
        "requested_logo_percent": result.requested_logo_percent,
        "used_logo_percent": result.used_logo_percent,
        "checks": [asdict(check) for check in result.checks],
    }


def _export_payload(options: dict, kind: str):
    kind = {"jpeg":"jpg","tif":"tiff"}.get(kind.lower(),kind.lower())
    if kind not in FORMATS and kind != "zip":
        raise ValueError("Choose a supported export format.")
    result = generate_qr(**options)
    host = urlsplit(result.url).hostname or "code"
    stem = "qr_" + (re.sub(r"[^A-Za-z0-9_-]", "_", host)[:70] or "code")
    if kind == "zip":
        return export_bundle(result,stem), "application/zip", stem+".zip"
    return export_file(result,kind), FORMATS[kind][1], stem+"."+kind


def create_app() -> FastAPI:
    api = FastAPI(title="QR Studio", version="1.2.0", redoc_url=None)
    static = Path(os.environ.get("QR_STATIC_DIR", Path(__file__).parent / "static"))
    catalog = json.loads((static / "logos" / "catalog.json").read_text(encoding="utf-8"))
    presets = {item["id"]: item for item in catalog}

    @api.middleware("http")
    async def response_headers(request, call_next):
        length = request.headers.get("content-length")
        try:
            if length is not None and int(length) > MAX_LOGO_BYTES + 64 * 1024:
                return JSONResponse({"detail": "Choose a logo smaller than 5 MB."}, status_code=413)
        except ValueError:
            return JSONResponse({"detail": "Invalid request size."}, status_code=400)
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        return response

    @api.get("/", include_in_schema=False)
    def index():
        return FileResponse(static / "index.html")

    @api.get("/health", include_in_schema=False)
    def health():
        return {"status": "ok"}

    @api.get("/api/logos")
    def logos():
        return [{"id": item["id"], "label": item["label"],
                 "src": "/static/logos/" + item["file"]} for item in catalog]

    async def read_options(
        url: Annotated[str, Form(max_length=3000)],
        logo: Annotated[UploadFile | None, File()] = None,
        logo_percent: Annotated[int, Form(ge=8, le=28)] = 18,
        padding_percent: Annotated[int, Form(ge=0, le=30)] = 12,
        pixels: Annotated[int, Form(ge=512, le=8000)] = 4096,
        dpi: Annotated[int, Form(ge=72, le=1200)] = 600,
        auto_reduce: Annotated[bool, Form()] = True,
        logo_mode: Annotated[Literal["with_logo", "none"], Form()] = "with_logo",
        monochrome: Annotated[bool, Form()] = False,
        bw_threshold: Annotated[int, Form(ge=1, le=254)] = 170,
        width: Annotated[int | None, Form(ge=512, le=8000)] = None,
        height: Annotated[int | None, Form(ge=512, le=8000)] = None,
        module_style: Annotated[Literal["square","rounded","dots"], Form()] = "square",
        canvas_shape: Annotated[Literal["square","rounded","circle","hexagon","triangle"], Form()] = "square",
        builtin_logo: Annotated[str, Form(max_length=64)] = "",
        remove_white_background: Annotated[bool, Form()] = False,
        white_tolerance: Annotated[int, Form(ge=0, le=100)] = 20,
        logo_opacity: Annotated[int, Form(ge=0, le=100)] = 100,
    ):
        logo_bytes = None
        if logo is not None:
            try:
                if logo_mode != "none":
                    logo_bytes = await logo.read(MAX_LOGO_BYTES + 1)
                    if len(logo_bytes) > MAX_LOGO_BYTES:
                        raise HTTPException(status_code=413, detail="Choose a logo smaller than 5 MB.")
            finally:
                await logo.close()
        if builtin_logo and logo_mode != "none":
            if builtin_logo not in presets:
                raise HTTPException(status_code=422, detail="Choose a logo from the built-in picker.")
            if logo_bytes is not None:
                raise HTTPException(status_code=422, detail="Choose a built-in logo or upload a file, one at a time.")
            logo_bytes = (static / "logos" / presets[builtin_logo]["file"]).read_bytes()
        return dict(url=url, logo_bytes=logo_bytes, logo_percent=logo_percent,
                    padding_percent=padding_percent, pixels=pixels, dpi=dpi,
                    auto_reduce=auto_reduce, monochrome=monochrome, bw_threshold=bw_threshold,
                    width=width, height=height, module_style=module_style, canvas_shape=canvas_shape,
                    remove_white_background=remove_white_background,
                    white_tolerance=white_tolerance, logo_opacity=logo_opacity)

    @api.post("/api/generate")
    async def generate(options: dict = Depends(read_options)):
        try:
            return await run_in_threadpool(_generate_payload, **options)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @api.post("/api/export")
    async def export(format: str = Form("png"), options: dict = Depends(read_options)):
        try:
            content, mime, filename = await run_in_threadpool(_export_payload, options, format)
            return Response(content,media_type=mime,headers={"Content-Disposition":f'attachment; filename="{filename}"'})
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    api.mount("/static", StaticFiles(directory=static), name="static")
    return api
