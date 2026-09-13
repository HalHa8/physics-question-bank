#!/bin/bash
# Locate Python; the shared local launcher prepares the environment and opens PhysicsBank.
SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P) || exit 1
cd "$SCRIPT_DIR" || exit 1

python_is_supported() {
    "$1" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)' \
        >/dev/null 2>&1
}

find_supported_python() {
    for candidate in "$SCRIPT_DIR/venv/bin/python" python3 python3.14 python3.13 python3.12 python3.11 python3.10; do
        candidate_path=$(command -v "$candidate" 2>/dev/null || true)
        if [ -n "$candidate_path" ] && python_is_supported "$candidate_path"; then
            printf '%s\n' "$candidate_path"
            return 0
        fi
    done
    return 1
}

PYTHON_BIN=$(find_supported_python)
if [ -z "$PYTHON_BIN" ]; then
    echo "未找到 Python 3.10 或更高版本，请安装 Python 后再启动题库。"
    LAUNCHER_EXIT=1
else
    "$PYTHON_BIN" -B -m scripts.local_launcher
    LAUNCHER_EXIT=$?
fi
if [ "$LAUNCHER_EXIT" -ne 0 ] && [ -t 0 ] && [ "$MATHBANK_NO_PAUSE" != "1" ]; then
    read -r -n 1 -p "按任意键退出..." _unused
    echo ""
fi
exit "$LAUNCHER_EXIT"
