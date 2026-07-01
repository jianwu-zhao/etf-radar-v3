from functools import lru_cache

from alpaca.data.historical import StockHistoricalDataClient

from config.settings import settings


@lru_cache(maxsize=1)
def get_data_client() -> StockHistoricalDataClient:
    return StockHistoricalDataClient(
        api_key=settings.alpaca_api_key,
        secret_key=settings.alpaca_secret_key,
    )
