VIM ?= vim

test:
	$(VIM) -u NONE -es -c "set rtp+=." -c "runtime plugin/demo.vim" -c "if exists(':Demo') && demo#greet() ==# 'hello' | quit | else | cquit 1 | endif"

.PHONY: test
