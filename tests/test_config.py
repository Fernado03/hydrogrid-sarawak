"""Verification tests for HydroGrid Sarawak Phase 0 configuration loader."""

from __future__ import annotations

import copy

import pytest

from hydrogrid.config import Settings, load_settings


BASE_ENV = {
    "HYDROGRID_ENV": "local",
    "POSTGRES_HOST": "localhost",
    "POSTGRES_PORT": "5432",
    "POSTGRES_DB": "hydrogrid_warehouse",
    "POSTGRES_USER": "hydrogrid",
    "POSTGRES_PASSWORD": "local-only-password",
    "OPEN_METEO_BASE_URL": "https://api.open-meteo.com",
    "LLM_BASE_URL": "https://llm.example.com/v1",
    "LLM_API_KEY": "",
}


def env_with(**overrides: str) -> dict[str, str]:
    """Return a fresh copy of BASE_ENV with selected overrides."""
    env = copy.deepcopy(BASE_ENV)
    env.update(overrides)
    return env


def test_load_settings_happy_path() -> None:
    settings = load_settings(BASE_ENV)

    assert isinstance(settings, Settings)
    assert settings.environment == "local"
    assert settings.postgres_host == "localhost"
    assert settings.postgres_port == 5432
    assert settings.postgres_db == "hydrogrid_warehouse"
    assert settings.openmeteo_base_url == "https://api.open-meteo.com"
    assert settings.llm_base_url == "https://llm.example.com/v1"


def test_environment_is_normalized_to_lowercase() -> None:
    settings = load_settings(env_with(HYDROGRID_ENV="LOCAL"))

    assert settings.environment == "local"


@pytest.mark.parametrize("environment", ["local", "dev", "test", "prod"])
def test_allowed_environments(environment: str) -> None:
    env = env_with(HYDROGRID_ENV=environment)

    if environment == "prod":
        env["LLM_API_KEY"] = "test-key"

    settings = load_settings(env)

    assert settings.environment == environment


def test_invalid_environment_raises_value_error() -> None:
    with pytest.raises(ValueError):
        load_settings(env_with(HYDROGRID_ENV="staging"))


@pytest.mark.parametrize("port", ["1", "65535"])
def test_valid_postgres_port_boundaries(port: str) -> None:
    settings = load_settings(env_with(POSTGRES_PORT=port))

    assert settings.postgres_port == int(port)


@pytest.mark.parametrize("port", ["", "0", "65536", "abc", "-1"])
def test_invalid_postgres_port_raises_value_error(port: str) -> None:
    with pytest.raises(ValueError):
        load_settings(env_with(POSTGRES_PORT=port))


@pytest.mark.parametrize(
    "missing_key",
    [
        "HYDROGRID_ENV",
        "POSTGRES_HOST",
        "POSTGRES_PORT",
        "POSTGRES_DB",
        "POSTGRES_USER",
        "POSTGRES_PASSWORD",
        "OPEN_METEO_BASE_URL",
        "LLM_BASE_URL",
        "LLM_API_KEY",
    ],
)
def test_missing_key_raises_value_error(missing_key: str) -> None:
    env = copy.deepcopy(BASE_ENV)
    env.pop(missing_key)

    with pytest.raises(ValueError):
        load_settings(env)


@pytest.mark.parametrize(
    "field",
    [
        "OPEN_METEO_BASE_URL",
        "LLM_BASE_URL",
    ],
)
@pytest.mark.parametrize(
    "bad_url",
    [
        "",
        "api.open-meteo.com",
        "ftp://example.com",
        "localhost:8000",
    ],
)
def test_invalid_urls_raise_value_error(field: str, bad_url: str) -> None:
    with pytest.raises(ValueError):
        load_settings(env_with(**{field: bad_url}))


def test_prod_environment_requires_llm_api_key() -> None:
    with pytest.raises(ValueError):
        load_settings(
            env_with(
                HYDROGRID_ENV="prod",
                LLM_API_KEY="",
            )
        )


def test_prod_environment_accepts_non_empty_llm_api_key() -> None:
    settings = load_settings(
        env_with(
            HYDROGRID_ENV="prod",
            LLM_API_KEY="test-key",
        )
    )

    assert settings.environment == "prod"