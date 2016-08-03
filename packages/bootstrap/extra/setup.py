from setuptools import setup


requires = [
    'cryptography',
    'kazoo',
    'retrying'
]


setup(
    name="dcos-internal-utils",
    install_requires=requires,
    packages=[
        'dcos_internal_utils',
    ],
    scripts=['bin/bootstrap'],
    version='0.0.1',
    description='DC/OS Internal Utilities Library',
    author='Mesosphere, Inc.',
    author_email='support@mesosphere.io',
    classifiers=[
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.4',
    ],
)
