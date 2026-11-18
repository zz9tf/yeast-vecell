#!/usr/bin/env bash
# 快速预览:改完某张表/某段文字后单次 pdflatex,不跑 bibtex、不清 aux/bbl。
# 引用页码可能没更新,但表格/文字改动秒出。全量正式编译用 build.sh。
set -e
export PATH="$HOME/texlive/2026/bin/x86_64-linux:$PATH"
cd "$(dirname "$0")"
pdflatex -interaction=nonstopmode -halt-on-error main.tex | tail -30
echo "OK -> $(pwd)/main.pdf ($(pdfinfo main.pdf 2>/dev/null | awk '/Pages/{print $2}') pages)"
