from .upload import router
from .document_tools import router as document_router

router.include_router(document_router)

__all__ = ["router"]
