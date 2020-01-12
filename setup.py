from setuptools import setup

with open("README.md", "r") as fh:
    long_description = fh.read()

setup(name='bsmdoc',
      version='0.0.4',
      description='another technical html doc generator',
      long_description=long_description,
      long_description_content_type="text/markdown",
      author='Tianzhu Qiao',
      author_email='tq@feiyilin.com',
      url='http://bsmdoc.feiyilin.com',
      license="MIT",
      platforms=["any"],
      py_modules=['bsmdoc'],
      install_requires=['ply', 'pygments', 'click', 'chardet', 'six'],
      entry_points='''
        [console_scripts]
        bsmdoc=bsmdoc:cli
      '''
     )
