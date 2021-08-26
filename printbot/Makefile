.PHONY: all format

all: format printbot

format:
	python3 -m isort .
	black *.py

printbot: main.py  __main__.py
	pyre
