from __future__ import annotations

from gabriel.logging_config import get_logger
from gabriel.tool.models import ToolCategory
from gabriel.resource.grn import GRN

import importlib
import pkgutil
from types import ModuleType

logger = get_logger(__name__)

LIBRARY_PACKAGE = "gabriel.tool.library"

def search():
    library = importlib.import_module(LIBRARY_PACKAGE)

    for pkg_info in pkgutil.iter_modules(library.__path__, prefix=f"{LIBRARY_PACKAGE}."):
        namespace = pkg_info.name.rsplit(".", 1)[-1]
        if not pkg_info.ispkg or namespace.startswith("_"):
            continue

        library_pkg = importlib.import_module(pkg_info.name)
        
        for mod_info in pkgutil.iter_modules(library_pkg.__path__, prefix=f"{library_pkg.__name__}."):
            tool_name = mod_info.name.rsplit(".", 1)[-1]

            if mod_info.ispkg or tool_name.startswith("_"):
                continue

            logger.info(f"Discovered module: {mod_info.name} under category: {namespace}")

            try:
                module = importlib.import_module(mod_info.name)
            except ImportError:
                logger.warning(f"Skipping tool module {mod_info.name} (import failed)", exc_info=True)
                continue
                
            # Clean values for tool input
            org_id = ""  # FIXME: Determine how to get the org_id
            category = ToolCategory(namespace) if namespace in ToolCategory.__members__ else ToolCategory.CUSTOM
            binding = f"{namespace}.{tool_name}"
            grn = GRN(org_id=org_id, resource_id=tool_name, resource_type="tool")
            fn = getattr(module, tool_name, None)
        

if __name__ == "__main__":
    search()