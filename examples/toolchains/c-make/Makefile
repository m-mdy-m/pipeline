CC ?= cc

all: demo

demo: demo.c
	$(CC) -Wall -Werror -o demo demo.c

test: demo
	./demo

clean:
	rm -f demo

.PHONY: all test clean
