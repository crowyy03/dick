from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from app.core.config import Settings, get_settings
from app.db.session import create_engine, get_session_factory
from app.integrations.three_x_ui.client import ThreeXUiAdapter
from app.services.rate_limit import RegenerateRateLimiter


class AppContainer:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.engine: AsyncEngine = create_engine(self.settings)
        self.session_factory: async_sessionmaker = get_session_factory(self.engine)
        self.panel = ThreeXUiAdapter(self.settings)
        self.regenerate_limiter = RegenerateRateLimiter()

    async def shutdown(self) -> None:
        await self.panel.aclose()
        await self.engine.dispose()
