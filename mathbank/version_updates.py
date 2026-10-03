"""Release lookup and version comparison; network access is supplied explicitly."""

import re
from pathlib import Path
from typing import Callable


def parse_version_tuple(v_str: str):
    """Parse version string like 'v2.0.1' or '2.0.1' into integer tuple for comparison."""
    if not v_str:
        return (0, 0, 0)
    cleaned = v_str.strip().lstrip("vV").split("-")[0].split("+")[0]
    parts = []
    for p in cleaned.split("."):
        try:
            parts.append(int(re.sub(r"\D", "", p) or "0"))
        except Exception:
            parts.append(0)
    while len(parts) < 3:
        parts.append(0)
    return tuple(parts[:3])


def check_release_update(*, current_version: str, repo: str,
                         project_root: Path, request_get: Callable):
    """Check for latest release on GitHub."""

    is_git_repo = (project_root / ".git").exists()
    current_ver = current_version

    result = {
        "status": "success",
        "current_version": current_ver,
        "latest_version": current_ver,
        "has_update": False,
        "release_title": "",
        "release_body": "",
        "release_url": f"https://github.com/{repo}/releases/latest",
        "published_at": "",
        "assets": {},
        "is_git_repo": is_git_repo
    }

    try:
        url = f"https://api.github.com/repos/{repo}/releases/latest"
        headers = {
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "PhysicsBank-Question-Bank-App"
        }
        resp = request_get(url, headers=headers, timeout=5)
        if resp.status_code == 200:
            data = resp.json()
            latest_tag = data.get("tag_name", "").strip()
            latest_ver = latest_tag.lstrip("vV")

            # Compare versions
            current_tuple = parse_version_tuple(current_ver)
            latest_tuple = parse_version_tuple(latest_ver)

            has_update = latest_tuple > current_tuple

            assets_map = {}
            for asset in data.get("assets", []):
                name = asset.get("name", "")
                download_url = asset.get("browser_download_url", "")
                size_mb = round(asset.get("size", 0) / (1024 * 1024), 1)
                download_count = asset.get("download_count", 0)
                if "macOS" in name or "mac" in name.lower() or "darwin" in name.lower():
                    assets_map["macOS"] = {"name": name, "url": download_url, "size_mb": size_mb, "downloads": download_count}
                elif "Windows" in name or "win" in name.lower():
                    assets_map["Windows"] = {"name": name, "url": download_url, "size_mb": size_mb, "downloads": download_count}

            result.update({
                "latest_version": latest_tag,
                "has_update": has_update,
                "release_title": data.get("name", "") or latest_tag,
                "release_body": data.get("body", ""),
                "release_url": data.get("html_url", result["release_url"]),
                "published_at": data.get("published_at", ""),
                "assets": assets_map
            })
        else:
            result["status"] = "warning"
            result["message"] = f"GitHub API 返回状态码: {resp.status_code}"
    except Exception as e:
        result["status"] = "warning"
        result["message"] = f"检查更新超时或失败: {str(e)}"

    return result
