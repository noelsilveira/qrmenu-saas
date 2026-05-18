from app.db.session import engine
from app.db.base_class import Base

async def startup_event():
    pass

async def shutdown_event():
    await engine.dispose()
