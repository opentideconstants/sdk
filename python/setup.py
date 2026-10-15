"""Build hook: put supported-formats.json (SDK spec §7.4) inside the package at build time.

The one source file is python/supported-formats.json (the CI check reads it there). build_py copies it to
opentideconstants/supported-formats.json in the wheel; MANIFEST.in puts it at the root of the sdist, so a
wheel built from the sdist gets it the same way. No symbolic link, so a Windows checkout works too.
"""
from pathlib import Path

from setuptools import setup
from setuptools.command.build_py import build_py

HERE = Path(__file__).resolve().parent


class BuildPyWithSupportedFormats(build_py):
    def run(self):
        super().run()
        dest = Path(self.build_lib) / "opentideconstants"
        self.mkpath(str(dest))
        self.copy_file(str(HERE / "supported-formats.json"), str(dest / "supported-formats.json"))


setup(cmdclass={"build_py": BuildPyWithSupportedFormats})
