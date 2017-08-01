from setuptools import setup

setup(name='bsmdoc',
      version='0.0.1',
      description='another technical html doc generator',
      author='Tianzhu Qiao',
      author_email='tq@feiyilin.com',
      url='http://bsmdoc.feiyilin.com',
      license="MIT",
      platforms=["any"],
      scripts=['bsmdoc.py'],
      install_requires=['ply', 'pygments'],
     )
