"""Offline entry-page and icon responses, independent of application state."""

import os
from pathlib import Path

from fastapi.responses import FileResponse, HTMLResponse, JSONResponse


def set_no_cache_headers(response):
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response


def build_index_response(*, static_dir: Path, js_dir: Path, css_dir: Path,
                         local_token: str, server_instance_id: str):
    index_path = str(static_dir / "index.html")
    if os.path.exists(index_path):
        with open(index_path, "r", encoding="utf-8") as f:
            html_content = f.read()

        # Inject dynamic cache-busting version parameter based on file mtime
        js_files = ["api.js", "editor.js", "ocr.js", "import.js", "paper.js", "dashboard.js", "qa-data.js", "qa.js"]
        for js in js_files:
            js_path = str(js_dir / js)
            mtime = int(os.path.getmtime(js_path)) if os.path.exists(js_path) else 0
            # Replace template version parameter
            html_content = html_content.replace(f"/static/js/{js}?v=1.0.1", f"/static/js/{js}?v={mtime}")
            # Also handle plain scripts references if they exist
            html_content = html_content.replace(f'src="/static/js/{js}"', f'src="/static/js/{js}?v={mtime}"')

        # Inject dynamic cache-busting version parameter for app.css and favicon assets
        css_path = str(css_dir / "app.css")
        css_mtime = int(os.path.getmtime(css_path)) if os.path.exists(css_path) else 0
        html_content = html_content.replace('/static/css/app.css', f'/static/css/app.css?v={css_mtime}')

        fav_path = str(static_dir / "favicon.png")
        fav_mtime = int(os.path.getmtime(fav_path)) if os.path.exists(fav_path) else 0
        html_content = html_content.replace('/static/favicon.png', f'/static/favicon.png?v={fav_mtime}')

        # Inject the token and server_instance_id directly into index.html to bypass any cookie blocking policies
        token_script = f'<script>window.__localToken = "{local_token}"; window.__serverInstanceId = "{server_instance_id}";</script>'
        html_content = html_content.replace('<head>', f'<head>\n    {token_script}')

        res = HTMLResponse(content=html_content)
        set_no_cache_headers(res)

        res.set_cookie(
            key="local_token",
            value=local_token,
            httponly=False,  # JavaScript must be able to read this cookie to send it back via headers
            samesite="lax",
            secure=False
        )
        return res
    return JSONResponse(
        content={"status": "error", "message": "static/index.html not found. Please create it."},
        status_code=404
    )


def icon_response(static_dir: Path, candidates, missing_message: str):
    """Serve the first existing candidate with the same no-cache contract."""
    for name, media_type in candidates:
        path = static_dir / name
        if path.exists():
            return set_no_cache_headers(FileResponse(str(path), media_type=media_type))
    return JSONResponse(
        content={"status": "error", "message": missing_message}, status_code=404,
    )


def favicon_response(static_dir: Path):
    return icon_response(
        static_dir, (("favicon.ico", "image/x-icon"), ("favicon.png", "image/png")),
        "favicon not found.",
    )


def favicon_svg_response(static_dir: Path):
    return icon_response(
        static_dir, (("favicon.svg", "image/svg+xml"),), "favicon.svg not found.",
    )


def apple_touch_icon_response(static_dir: Path):
    return icon_response(
        static_dir, (("apple-touch-icon.png", "image/png"), ("favicon.png", "image/png")),
        "apple touch icon not found.",
    )
