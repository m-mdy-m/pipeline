.PHONY: build clean

build:
	rm -f build/*.pdf
	mkdir -p build
	latexmk -pdf -interaction=nonstopmode -halt-on-error -file-line-error -outdir=build main-en.tex
	latexmk -xelatex -interaction=nonstopmode -halt-on-error -file-line-error -outdir=build main-fa.tex

clean:
	latexmk -C -outdir=build main-en.tex
	latexmk -C -outdir=build main-fa.tex
