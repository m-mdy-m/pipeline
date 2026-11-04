# LaTeX toolchain fixture

This fixture builds an English pdfLaTeX document and a Persian XeLaTeX
document through a project-owned Makefile. The English fixture deliberately
uses BibLaTeX Chicago Notes with Biber and the `algorithm` / `algpseudocode`
environments. It exercises bibliography and algorithm packages used by
academic publications.

Run `make build` after installing TeX Live, latexmk, Biber, the TeX Live
BibTeX extra and science collections, the xepersian package (for example,
TeX Live's Arabic language collection), and the Vazirmatn font. The Pipeline
GitHub action provisions these dependencies on Ubuntu and checks the package
entry points before building.
