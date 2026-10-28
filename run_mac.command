#!/usr/bin/env bash
# Chạy ứng dụng trên macOS — CHỈ CẦN NHẤN ĐÚP (double-click) vào file này.
# Lần đầu chạy sẽ tự tạo môi trường ảo (.venv) và cài thư viện cần thiết
# (có thể mất khoảng 1 phút); các lần sau chạy gần như ngay lập tức.
set -euo pipefail
cd "$(dirname "$0")"

if [ ! -d ".venv" ]; then
    echo "Lần đầu chạy: đang thiết lập môi trường, vui lòng đợi..."
    python3 -m venv .venv
    ./.venv/bin/python3 -m pip install --quiet --upgrade pip
    ./.venv/bin/python3 -m pip install --quiet -r requirements.txt
fi

./.venv/bin/python3 main.py
