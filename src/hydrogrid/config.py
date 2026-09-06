"""Fail-fast settings loader for HydroGrid Sarawak."""

from __future__ import annotations
import os
from dataclasses import dataclass
from typing import Mapping, Optional

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

DEFAULT_ENV = {
    "HYDROGRID_ENV": "development",
    "POSTGRES_HOST": "localhost",
    "POSTGRES_PORT": "5432",
    "POSTGRES_DB": "hydrogrid_warehouse",
    "POSTGRES_USER": "hydrogrid",
    "POSTGRES_PASSWORD": "change_me",
    "OPEN_METEO_BASE_URL": "https://api.open-meteo.com",
    "LLM_BASE_URL": "https://llm.example.com/v1",
    "LLM_API_KEY": "test-key",
}


@dataclass(frozen=True)
class Settings:
    environment: str
    postgres_host: str
    postgres_port: int
    postgres_db: str
    postgres_user: str
    postgres_password: str
    openmeteo_base_url: str
    llm_base_url: str
    llm_api_key: str


def load_settings(env: Optional[Mapping[str, str]] = None) -> Settings:
    """Loads and validates settings from environment mapping, .env, or defaults."""
    source = env if env is not None else {**DEFAULT_ENV, **os.environ}
    return Settings(
        environment=source["HYDROGRID_ENV"],
        postgres_host=source["POSTGRES_HOST"],
        postgres_port=int(source["POSTGRES_PORT"]),
        postgres_db=source["POSTGRES_DB"],
        postgres_user=source["POSTGRES_USER"],
        postgres_password=source["POSTGRES_PASSWORD"],
        openmeteo_base_url=source["OPEN_METEO_BASE_URL"],
        llm_base_url=source["LLM_BASE_URL"],
        llm_api_key=source["LLM_API_KEY"],
    )