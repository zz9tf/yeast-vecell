#!/usr/bin/env bash
# 用真 pdflatex 编译 AAAI-2027 稿件(官方 sty 强制 pdfTeX)。
# TeX Live 装在 $HOME/texlive/2026(本机 install-tl 网络安装的 scheme-basic + 补装依赖)。
set -e
export PATH="$HOME/texlive/2026/bin/x86_64-linux:$PATH"
cd "$(dirname "$0")"
rm -f main.aux main.bbl main.blg main.out
pdflatex -interaction=nonstopmode main.tex
bibtex main
pdflatex -interaction=nonstopmode main.tex
pdflatex -interaction=nonstopmode main.tex
rm -f main.aux main.blg main.out
echo "OK -> $(pwd)/main.pdf ($(pdfinfo main.pdf 2>/dev/null | awk '/Pages/{print $2}') pages)"
