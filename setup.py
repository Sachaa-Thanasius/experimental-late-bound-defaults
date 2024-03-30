# This whole file is modified from future-fstrings.

import distutils
import os

from setuptools import setup
from setuptools.command.install import install as _install

PTH = (
    "try:\n"
    "    import experimental_late_bound_defaults\n"
    "except ImportError:\n"
    "    pass\n"
    "else:\n"
    "    experimental_late_bound_defaults.register()\n"
)


class install(_install):
    def initialize_options(self) -> None:
        super().initialize_options()

        contents = f"import sys; exec({PTH!r})\n"
        self.extra_path = (self.distribution.metadata.name, contents)

    def finalize_options(self) -> None:
        super().finalize_options()

        install_suffix = os.path.relpath(self.install_lib, self.install_libbase)
        if install_suffix == ".":
            distutils.log.info("skipping install of .pth during easy-install")
        elif install_suffix == self.extra_path[1]:
            self.install_lib = self.install_libbase
            distutils.log.info(
                "will install .pth to '%s.pth'",
                os.path.join(self.install_lib, self.extra_path[0]),  # noqa: PTH118
            )
        else:
            raise RuntimeError("unexpected install_suffix", self.install_lib, self.install_libbase, install_suffix)


setup(cmdclass={"install": install})
