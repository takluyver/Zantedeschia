from distutils.core import setup

with open("README.rst", "r") as f:
    readme = f.read()

setup(name='Zantedeschia',
      version='0.1',
      description='ZeroMQ sockets integrated with the AsyncIO event loop',
      long_description = readme,
      author='Thomas Kluyver',
      author_email='thomas@kluyver.me.uk',
      url='https://github.com/takluyver/Zantedeschia',
      py_modules=['zantedeschia'],
      classifiers=[
          'Intended Audience :: Developers',
          'License :: OSI Approved :: BSD License',
          'Programming Language :: Python',
          'Programming Language :: Python :: 3',
      ],
)
