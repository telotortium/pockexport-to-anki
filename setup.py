from setuptools import setup, find_packages

setup(
    name='pockexport-to-anki',
    version='0.1.0',
    author='Robert Irelan',
    author_email='rirelan@gmail.com',
    description='Creates Anki cards from output of pockexport',
    packages=find_packages(),
    install_requires=[
        'requests', 'pocket'
    ],
    entry_points={
        'console_scripts': [
            'pockexport-to-anki=pockexport_to_anki.__init__:main',
        ],
    },
)
