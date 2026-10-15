"""Modal entry point. Deploy with: modal deploy app.py"""
from pathlib import Path
import modal

ROOT = Path(__file__).resolve().parent
app = modal.App("qr-studio")
image = (
    modal.Image.debian_slim(python_version="3.12")
    .apt_install("libcairo2")
    .pip_install_from_requirements(str(ROOT / "requirements.txt"))
    .env({"QR_STATIC_DIR": "/app/static"})
    .add_local_python_source("qr_engine", "web_app")
    .add_local_dir(str(ROOT / "static"), remote_path="/app/static")
)


@app.function(image=image, cpu=2, memory=1024, timeout=120, scaledown_window=300)
@modal.concurrent(max_inputs=2)
@modal.asgi_app()
def web():
    from web_app import create_app
    return create_app()
