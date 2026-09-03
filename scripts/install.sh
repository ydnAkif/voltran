#!/usr/bin/env bash
# ==============================================================================
# VOLTRAN macOS Tek Komutluk Kurulum Betiği
# ==============================================================================

set -euo pipefail

BOLD="\033[1m"
GREEN="\033[0;32m"
CYAN="\033[0;36m"
YELLOW="\033[0;33m"
RED="\033[0;31m"
NC="\033[0m"

echo -e "${BOLD}${CYAN}"
echo "  __     ______  _   _______ _____            _   _ "
echo "  \ \   / / __ \| | |__   __|  __ \     /\   | \ | |"
echo "   \ \_/ / |  | | |    | |  | |__) |   /  \  |  \| |"
echo "    \   /| |  | | |    | |  |  _  /   / /\ \ | . \` |"
echo "     | | | |__| | |____| |  | | \ \  / ____ \| |\  |"
echo "     |_|  \____/|______|_|  |_|  \_\/_/    \_\_| \_|"
echo -e "${NC}"
echo -e "${BOLD}VOLTRAN macOS Kurulumuna Hoş Geldiniz!${NC}\n"

# 1. Platform Kontrolü
OS="$(uname -s)"
if [ "$OS" != "Darwin" ]; then
    echo -e "${RED}Hata: Bu kurulum betiği yalnızca macOS içindir.${NC}"
    exit 1
fi

ARCH="$(uname -m)"
echo -e "Platform: ${GREEN}macOS ($ARCH)${NC}"

# 2. uv Paket Yöneticisi Kontrolü
if ! command -v uv >/dev/null 2>&1; then
    echo -e "${YELLOW}uv bulunamadı, kuruluyor...${NC}"
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.local/bin:$PATH"
fi
echo -e "uv: ${GREEN}$(uv --version)${NC}"

# 3. hcom İşbirliği Motoru Kontrolü
if ! command -v hcom >/dev/null 2>&1; then
    echo -e "${YELLOW}hcom çoklu ajan motoru kuruluyor...${NC}"
    if command -v brew >/dev/null 2>&1; then
        brew install aannoo/hcom/hcom || uv tool install hcom
    else
        uv tool install hcom
    fi
fi
echo -e "hcom: ${GREEN}$(hcom --version 2>/dev/null || echo 'kuruldu')${NC}"

# 4. Voltran'ı Global Olarak Kur
echo -e "${CYAN}Voltran paketi kuruluyor...${NC}"
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

uv tool install --force "$REPO_DIR"

echo -e "\n${GREEN}${BOLD}✓ VOLTRAN başarıyla kuruldu!${NC}\n"

# 5. Teşhis Çalıştır
echo -e "${CYAN}Sistem teşhisi çalıştırılıyor...${NC}"
voltran doctor || true

echo -e "\n${BOLD}Hemen başlamak için örnek komutlar:${NC}"
echo -e "  ${YELLOW}voltran run \"Sistem mimarisini karşılaştır\" -m council${NC}"
echo -e "  ${YELLOW}voltran bench --dry-run${NC}"
echo -e "  ${YELLOW}voltran doctor${NC}"
echo -e "  ${YELLOW}voltran history${NC}\n"
