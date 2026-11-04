# LaTeX toolchain fixture

This fixture builds an English pdfLaTeX document and a Persian XeLaTeX
document through a project-owned Makefile. The English fixture deliberately
uses `biblatex` with the `chicago-notes` style and Biber, ensuring that the
CI runtime includes the bibliography packages required by real academic
publications.

Run `make build` after installing TeX Live, latexmk, Biber, the TeX Live
BibTeX extra collection, the xepersian package (for example, TeX Live's Arabic
language collection), and the Vazirmatn font. The Pipeline GitHub action
provisions these dependencies on Ubuntu runners and explicitly checks the
Chicago Notes style files before starting a project build.
