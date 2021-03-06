import codecs
import os.path
from setuptools import setup, find_packages

def read(rel_path):
    here = os.path.abspath(os.path.dirname(__file__))
    with codecs.open(os.path.join(here, rel_path), 'r') as fp:
        return fp.read()
    raise RuntimeError("Unable to open file %s"%rel_path)

def get_version(rel_path):
    for line in read(rel_path).splitlines():
        if line.startswith('__version__'):
            delim = '"' if '"' in line else "'"
            return line.split(delim)[1]
    else:
        raise RuntimeError("Unable to find version string.")

setup(name='bsmdoc',
      version=get_version('./bsmdoc/bsmdoc.py'),
      description='another technical html doc generator',
      long_description=read("README.md"),
      long_description_content_type="text/markdown",
      author='Tianzhu Qiao',
      author_email='tq@feiyilin.com',
      url='http://bsmdoc.feiyilin.com',
      license="MIT",
      python_requires='>=3.2',
      platforms=["any"],
      packages=find_packages(),
      package_data={'bsmdoc': ['template/*.bsmdoc', 'template/css/*.css', 'template/js/*.js']},
      include_package_data=True,
      install_requires=['ply', 'pygments', 'click', 'click_default_group', 'cchardet', 'six'],
      entry_points='''
        [console_scripts]
        bsmdoc=bsmdoc.__main__:cli
      '''
     )
