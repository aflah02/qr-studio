"""Local preview: uvicorn web_app:create_app --factory --reload"""
from __future__ import annotations
import base64
import io
import os
import re
import zipfile
from dataclasses import asdict
from pathlib import Path
from typing import Annotated, Literal
from urllib.parse import urlsplit
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool
from qr_engine import MAX_LOGO_BYTES, generate_qr


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
        "monochrome": result.monochrome,
        "verified": result.verified, "logo_reduced": result.logo_reduced,
        "requested_logo_percent": result.requested_logo_percent,
        "used_logo_percent": result.used_logo_percent,
        "checks": [asdict(check) for check in result.checks],
    }


def create_app() -> FastAPI:
    api = FastAPI(title="QR Studio", version="1.0.0", redoc_url=None)
    static = Path(os.environ.get("QR_STATIC_DIR", Path(__file__).parent / "static"))

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

    @api.post("/api/generate")
    async def generate(
        url: Annotated[str, Form(max_length=3000)],
        logo: Annotated[UploadFile | None, File()] = None,
        logo_percent: Annotated[int, Form(ge=8, le=28)] = 18,
        padding_percent: Annotated[int, Form(ge=0, le=30)] = 12,
        pixels: Annotated[int, Form(ge=512, le=6000)] = 4096,
        dpi: Annotated[int, Form(ge=72, le=1200)] = 600,
        auto_reduce: Annotated[bool, Form()] = True,
        logo_mode: Annotated[Literal["with_logo", "none"], Form()] = "with_logo",
        monochrome: Annotated[bool, Form()] = False,
        bw_threshold: Annotated[int, Form(ge=1, le=254)] = 170,
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
        try:
            return await run_in_threadpool(
                _generate_payload, url=url, logo_bytes=logo_bytes,
                logo_percent=logo_percent, padding_percent=padding_percent,
                pixels=pixels, dpi=dpi, auto_reduce=auto_reduce,
                monochrome=monochrome, bw_threshold=bw_threshold,
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    api.mount("/static", StaticFiles(directory=static), name="static")
    return api
