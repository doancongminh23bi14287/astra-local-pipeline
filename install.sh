#!/usr/bin/env bash
set -euo pipefail
project_path="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
install_path="${ASTRA_BIN_DIR:-$HOME/.local/bin}"
python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else "Cần Python 3.10+")'
mkdir -p -- "$install_path"
chmod +x -- "$project_path/bin/astra"
if [[ -e "$install_path/astra" || -L "$install_path/astra" ]]; then
    if [[ "$(readlink -f -- "$install_path/astra")" != "$project_path/bin/astra" ]]; then
        printf 'Đã có lệnh khác tại %s/astra; đặt ASTRA_BIN_DIR để chọn vị trí khác.\n' "$install_path" >&2
        exit 1
    fi
else
    ln -s -- "$project_path/bin/astra" "$install_path/astra"
fi
printf 'Đã cài %s/astra (không cần pip hoặc sudo).\n' "$install_path"
case ":$PATH:" in
    *":$install_path:"*) ;;
    *) printf 'Thêm vào PATH trong terminal: export PATH=%q:"$PATH"\n' "$install_path" ;;
esac
"$install_path/astra" doctor
