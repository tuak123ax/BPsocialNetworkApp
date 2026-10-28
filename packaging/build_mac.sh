#!/usr/bin/env bash
# Build a standalone macOS .app using PyInstaller.
# Usage: ./packaging/build_mac.sh  (chạy từ thư mục gốc dự án, hoặc chạy trực tiếp file này)
set -euo pipefail
cd "$(dirname "$0")/.."

python3 -m pip install --quiet -r requirements.txt

pyinstaller --noconfirm --windowed --name "HieuSuatNhanVien" \
    --add-data "sample_data:sample_data" \
    --distpath dist --workpath build --specpath packaging \
    main.py

echo
echo "Done. App bundle at: dist/HieuSuatNhanVien.app"
