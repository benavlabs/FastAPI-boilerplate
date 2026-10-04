"""Importing the model modules, so ``Base.metadata`` knows every table."""

import importlib
import pkgutil

MODELS_PACKAGE = "src.modules"


def import_models(package_name: str = MODELS_PACKAGE) -> None:
    """Import every module under ``package_name``, registering its models on ``Base``."""
    package = importlib.import_module(package_name)
    for _, module_name, _ in pkgutil.walk_packages(package.__path__, package.__name__ + "."):
        importlib.import_module(module_name)
