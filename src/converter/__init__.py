"""Universal file -> embedding package converter (UEP).

    from converter import convert_file
    manifest = convert_file("site_model.3dm", "converter_output")
"""
from .engine import convert_file, supported_extensions  # noqa: F401
from .core import SCHEMA_VERSION  # noqa: F401
