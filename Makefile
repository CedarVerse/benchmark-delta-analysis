.PHONY: all dist d clean c version v install i test t build b

ci: clean install test
all: ci build version

dist d: all
	scripts/check-version.sh
	# Win MSYS2 support: force config file location
	twine upload --verbose $$(test -e ~/.pypirc && echo '--config-file ~/.pypirc') dist/*

clean c:
	rm -rfv out dist build/bdist.* src/*.egg-info

version v:
	git describe --tags ||:
	python -m setuptools_scm

install i:
	pip install --upgrade -e . \
	&& pip show cedarverse-bda

test t:
	echo TODO pytest --cov=src/bda tests/ --cov-report term-missing

build b:
	# SETUPTOOLS_SCM_PRETEND_VERSION=0.0.1
	python -m build
