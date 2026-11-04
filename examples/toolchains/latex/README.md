# LaTeX toolchain fixture

This fixture verifies one English pdfLaTeX document and one Persian XeLaTeX
document through a project-owned build target. Real projects should use the
same pattern when the two language editions need different engines.

Run `make build` after installing TeX Live, latexmk, the xepersian package (for example, TeX Live's Arabic language collection), and the Vazirmatn font. The Pipeline GitHub action provisions these dependencies on Ubuntu runners.
