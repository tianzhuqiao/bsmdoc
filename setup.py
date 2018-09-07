from setuptools import setup

setup(name='bsmdoc',
      version='0.0.3',
      description='another technical html doc generator',
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
