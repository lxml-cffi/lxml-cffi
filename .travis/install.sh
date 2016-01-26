#!/bin/bash
set -e
set -x

case "${TRAVIS_PYTHON_VERSION}" in
  pypy)
    export PYENV_ROOT="${HOME}/.pyenv"
    export PATH="${PYENV_ROOT}/bin:${PATH}"
    if [ ! -d "${PYENV_ROOT}/bin" ]; then
        rm -rf ${PYENV_ROOT}
    fi
    curl -L https://raw.githubusercontent.com/yyuu/pyenv-installer/master/bin/pyenv-installer | bash
    eval "$(pyenv init -)"
    pyenv update
    pyenv install -f pypy-4.0.1
    pyenv global pypy-4.0.1
    pyenv rehash
    ;;
esac
pip install -U pip setuptools wheel
if [ "${TRAVIS_PYTHON_VERSION}" != "pypy" ]; then
  pip install cffi
fi
