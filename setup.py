import setuptools

with open("README.md", "r") as fh:
    long_description = fh.read()

setuptools.setup(
    name="mailsh", # Replace with your own username
    version="1.0.0",
    author="liberacore",
    author_email="info@liberacore.org",
    description="CLI for reading and writing email",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/liberacore/mail-shell",
    packages=setuptools.find_packages(),
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: GPLv3 License",
        "Operating System :: OS Independent",
    ],
    install_requires=[
          'bs4',
          'stem',
          'prompt_toolkit'
      ],
    python_requires='>=3.6',
)
