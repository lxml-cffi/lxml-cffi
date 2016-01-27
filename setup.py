import os
import re
import sys
import fnmatch

# for command line options and supported environment variables, please
# see the end of 'setupinfo.py'

if sys.version_info < (2, 6) or sys.version_info[:2] in [(3, 0), (3, 1)]:
    print("This lxml version requires Python 2.6, 2.7, 3.2 or later.")
    sys.exit(1)

# When executing the setup.py, we need to be able to import ourselves, this
# means that we need to add the src/ directory to the sys.path.
base_dir = os.path.dirname(__file__)
src_dir = os.path.join(base_dir, "src")
sys.path.insert(0, src_dir)

from setuptools import setup, find_packages

import versioninfo
import setupinfo
import platform

# create lxml-version.h file
svn_version = versioninfo.svn_version()
versioninfo.create_version_h(svn_version)
print("Building lxml version %s." % svn_version)

extra_options = {}
if 'setuptools' in sys.modules:
    extra_options['zip_safe'] = False
    extra_options['extras_require'] = {
        'cssselect': 'cssselect>=0.7',
        'html5': 'html5lib',
        'htmlsoup': 'BeautifulSoup4',
    }

extra_options.update(setupinfo.extra_setup_args())

extra_options['package_data'] = {
    'lxml.isoschematron':  [
        'resources/rng/iso-schematron.rng',
        'resources/xsl/*.xsl',
        'resources/xsl/iso-schematron-xslt1/*.xsl',
        'resources/xsl/iso-schematron-xslt1/readme.txt'
        ],
    }

extra_options['package_dir'] = {
        '': 'src'
    }


def setup_extra_options():
    # Copy Global Extra Options
    extra_opts = dict(extra_options)
    extra_opts['packages'] = find_packages(
        where='src', exclude=['_cffi_src', '_cffi_src.*']) + [
            'lxml-cffi', 'lxml-cffi.includes']

    extra_opts['extras_require'][":platform_python_implementation != 'PyPy'"] = ["cffi>=1.4.1"]
    if platform.python_implementation() == 'PyPy':
        if sys.pypy_version_info < (2, 6):
            raise RuntimeError("Please upgrade to at least PyPy 2.6")
    else:
        extra_opts['setup_requires'] = ['cffi>=1.4.1']
    extra_opts['cffi_modules'] = ['src/_cffi_src/build_libxml.py:ffi']
    return extra_opts

setup(
    name = "lxml-cffi",
    version = versioninfo.version(),
    author="lxml-cffi maintainers",
    maintainer="lxml-cffi maintainers",
    url="https://github.com/lxml-cffi/lxml-cffi",

    description="Powerful and Pythonic XML processing library combining libxml2/libxslt with the ElementTree API.",

    long_description="""\
lxml is a Pythonic, mature binding for the libxml2 and libxslt libraries.  It
provides safe and convenient access to these libraries using the ElementTree
API.

It extends the ElementTree API significantly to offer support for XPath,
RelaxNG, XML Schema, XSLT, C14N and much more.

lxml-cffi is a fork of lxml that uses CFFI instead of Cython on PyPy, which
works more reliably.
""",
    classifiers = [
    versioninfo.dev_status(),
    'Intended Audience :: Developers',
    'Intended Audience :: Information Technology',
    'License :: OSI Approved :: BSD License',
    'Programming Language :: Python :: 2',
    'Programming Language :: Python :: 2.7',
    'Operating System :: OS Independent',
    'Topic :: Text Processing :: Markup :: HTML',
    'Topic :: Text Processing :: Markup :: XML',
    'Topic :: Software Development :: Libraries :: Python Modules'
    ],
    **setup_extra_options()
)
