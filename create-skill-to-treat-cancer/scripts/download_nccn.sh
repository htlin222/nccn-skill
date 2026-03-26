#!/usr/bin/env bash
# Download NCCN guideline PDFs by identifier.
#
# Usage:
#   ./download_nccn.sh                          # Interactive fzf picker
#   ./download_nccn.sh b-cell                   # Download specific guideline
#   ./download_nccn.sh --list                   # List all available identifiers
#   ./download_nccn.sh --batch nccnlist.txt     # Batch download from file
#
# Prerequisites:
#   - A valid NCCN cookie in $COOKIE_FILE (default: cookie.txt in CWD)
#   - curl, fzf (for interactive mode)
#
# The cookie is NOT included in this repository. You must:
#   1. Log in to nccn.org with a valid account
#   2. Use a browser extension (e.g. cookie-cook) to export the cookie
#   3. Save the HTTP Header value to cookie.txt

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DICT_FILE="${SCRIPT_DIR}/../assets/nccn_dict.txt"
COOKIE_FILE="${COOKIE_FILE:-cookie.txt}"
OUTPUT_DIR="${OUTPUT_DIR:-.}"
TODAY=$(date +"%Y-%m-%d")
NCCN_BASE_URL="https://www.nccn.org/professionals/physician_gls/pdf"

GREEN="\033[32m"
RED="\033[31m"
RESET="\033[0m"

usage() {
    echo "Usage: $0 [OPTIONS] [IDENTIFIER]"
    echo ""
    echo "Options:"
    echo "  --list            List all available NCCN guideline identifiers"
    echo "  --batch FILE      Batch download from a file (one identifier per line)"
    echo "  --cookie FILE     Path to cookie file (default: cookie.txt)"
    echo "  --output-dir DIR  Output directory (default: current directory)"
    echo "  -h, --help        Show this help"
    echo ""
    echo "If no identifier is given, launches fzf for interactive selection."
    echo ""
    echo "Examples:"
    echo "  $0 b-cell          # Download B-Cell Lymphomas"
    echo "  $0 nscl             # Download Non-Small Cell Lung Cancer"
    echo "  $0 --batch list.txt # Download all in list.txt"
}

list_identifiers() {
    if [ ! -f "$DICT_FILE" ]; then
        echo "Error: Dictionary file not found: $DICT_FILE" >&2
        exit 1
    fi
    echo "Available NCCN guideline identifiers:"
    echo ""
    printf "  %-25s %s\n" "IDENTIFIER" "GUIDELINE"
    printf "  %-25s %s\n" "----------" "---------"
    while IFS= read -r line; do
        [ -z "$line" ] && continue
        id=$(echo "$line" | awk '{print $1}')
        name=$(echo "$line" | sed 's/^[^ ]* *//' | sed 's/^# *//')
        printf "  %-25s %s\n" "$id" "$name"
    done < "$DICT_FILE"
}

download_one() {
    local identifier="$1"
    # Strip comments and whitespace
    identifier=$(echo "$identifier" | cut -d '#' -f 1 | tr -d '[:space:]')
    [ -z "$identifier" ] && return

    if [ ! -f "$COOKIE_FILE" ]; then
        echo -e "${RED}Error: Cookie file not found: $COOKIE_FILE${RESET}" >&2
        echo "Please log in to nccn.org and export your cookie. See README for instructions." >&2
        exit 1
    fi

    local output_file="${OUTPUT_DIR}/NCCN-${identifier}-${TODAY}.pdf"
    echo -e "Downloading: ${GREEN}${identifier}${RESET} → ${output_file}"

    curl -s "${NCCN_BASE_URL}/${identifier}.pdf" \
        -H 'authority: www.nccn.org' \
        -H 'accept: text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8' \
        -H 'accept-language: en-US,en;q=0.9' \
        -H 'cache-control: max-age=0' \
        -H "Cookie: $(cat "$COOKIE_FILE")" \
        --compressed --output "$output_file"

    if [ -f "$output_file" ] && [ -s "$output_file" ]; then
        local size
        size=$(wc -c < "$output_file" | tr -d ' ')
        if [ "$size" -lt 10000 ]; then
            echo -e "  ${RED}Warning: File is only ${size} bytes — likely an auth error. Check your cookie.${RESET}" >&2
        else
            echo -e "  ${GREEN}OK${RESET} ($(numfmt --to=iec "$size" 2>/dev/null || echo "${size} bytes"))"
        fi
    else
        echo -e "  ${RED}Failed${RESET}" >&2
    fi

    sleep 2
}

# Parse arguments
BATCH_FILE=""
IDENTIFIER=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        --list)
            list_identifiers
            exit 0
            ;;
        --batch)
            BATCH_FILE="$2"
            shift 2
            ;;
        --cookie)
            COOKIE_FILE="$2"
            shift 2
            ;;
        --output-dir)
            OUTPUT_DIR="$2"
            shift 2
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            IDENTIFIER="$1"
            shift
            ;;
    esac
done

mkdir -p "$OUTPUT_DIR"

# Batch mode
if [ -n "$BATCH_FILE" ]; then
    if [ ! -f "$BATCH_FILE" ]; then
        echo "Error: Batch file not found: $BATCH_FILE" >&2
        exit 1
    fi
    count=0
    while IFS= read -r line; do
        [ -z "$line" ] && continue
        [[ "$line" =~ ^# ]] && continue
        download_one "$line"
        count=$((count + 1))
    done < "$BATCH_FILE"
    echo ""
    echo "Downloaded $count guidelines to $OUTPUT_DIR"
    exit 0
fi

# Single identifier mode
if [ -n "$IDENTIFIER" ]; then
    download_one "$IDENTIFIER"
    exit 0
fi

# Interactive fzf mode
if ! command -v fzf &>/dev/null; then
    echo "Error: fzf not installed. Install it or provide an identifier as argument." >&2
    echo "  brew install fzf" >&2
    usage
    exit 1
fi

if [ ! -f "$DICT_FILE" ]; then
    echo "Error: Dictionary file not found: $DICT_FILE" >&2
    exit 1
fi

selected=$(cat "$DICT_FILE" | fzf --prompt='Select NCCN guideline: ' --height=40%)
if [ -z "$selected" ]; then
    echo "No selection made."
    exit 1
fi

id=$(echo "$selected" | awk '{print $1}')
download_one "$id"
