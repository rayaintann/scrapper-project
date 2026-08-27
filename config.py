"""Konfigurasi pipeline, dibaca dari file .env di root project."""

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent

load_dotenv(PROJECT_ROOT / ".env")

# Actor default. Bisa dioverride lewat APIFY_ACTOR_ID / TIKTOK_ACTOR_ID di .env.
DEFAULT_ACTOR_ID = "apify/instagram-profile-scraper"
DEFAULT_TIKTOK_ACTOR_ID = "clockworks/tiktok-scraper"

# Harga per profil (USD) untuk plan FREE di Apify Store, dipakai hanya untuk
# estimasi biaya sebelum run. Plan berbayar lebih murah, jadi angka ini
# adalah batas atas.
PRICE_PER_PROFILE_USD = 0.0026

# TikTok ditagih per hasil ($0.0037) ditambah biaya residential proxy per
# permintaan ($0.0013) saat proxyCountryCode diisi. Tanpa proxy itu TikTok
# memblokir request dan run selesai tanpa satu pun profil.
PRICE_PER_TIKTOK_PROFILE_USD = 0.0050


class ConfigError(RuntimeError):
    """Ada variabel .env yang wajib tapi belum diisi."""


@dataclass(frozen=True)
class PostgresConfig:
    host: str
    port: str
    database: str
    user: str
    password: str

    def as_connect_kwargs(self) -> dict:
        return {
            "host": self.host,
            "port": self.port,
            "database": self.database,
            "user": self.user,
            "password": self.password,
        }


@dataclass(frozen=True)
class ApifyConfig:
    token: str
    actor_id: str
    include_about_section: bool


@dataclass(frozen=True)
class TikTokConfig:
    token: str
    actor_id: str
    # Kode negara untuk residential proxy. Wajib diisi supaya TikTok tidak
    # memblokir; 'None' berarti pakai proxy datacenter dan hampir pasti gagal.
    proxy_country: str
    # Jumlah video per profil. 1 sudah cukup karena data profil menempel di
    # authorMeta setiap video, dan tiap video dihitung sebagai satu hasil berbayar.
    results_per_page: int


@dataclass(frozen=True)
class Config:
    postgres: PostgresConfig
    apify: ApifyConfig
    tiktok: TikTokConfig
    output_dir: Path


def _require(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise ConfigError(
            f"{name} belum diset. Tambahkan ke {PROJECT_ROOT / '.env'} "
            f"(contoh formatnya ada di .env.example)."
        )
    return value


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None or raw == "":
        return default
    return raw.strip().lower() in {"1", "true", "yes", "y", "on"}


def load_config() -> Config:
    postgres = PostgresConfig(
        host=_require("PG_HOST"),
        port=os.getenv("PG_PORT", "5432"),
        database=_require("PG_DB"),
        user=_require("PG_USER"),
        password=_require("PG_PASSWORD"),
    )
    apify = ApifyConfig(
        token=_require("APIFY_API_TOKEN"),
        actor_id=os.getenv("APIFY_ACTOR_ID") or DEFAULT_ACTOR_ID,
        # includeAboutSection hanya untuk akun berbayar, jadi default-nya mati.
        include_about_section=_env_bool("APIFY_INCLUDE_ABOUT_SECTION", False),
    )
    tiktok = TikTokConfig(
        # Token Apify sama; yang berbeda hanya actor dan opsinya.
        token=_require("APIFY_API_TOKEN"),
        actor_id=os.getenv("TIKTOK_ACTOR_ID") or DEFAULT_TIKTOK_ACTOR_ID,
        proxy_country=os.getenv("TIKTOK_PROXY_COUNTRY") or "ID",
        results_per_page=int(os.getenv("TIKTOK_RESULTS_PER_PAGE") or 1),
    )
    output_dir = Path(os.getenv("OUTPUT_DIR") or (PROJECT_ROOT / "output"))
    if not output_dir.is_absolute():
        output_dir = PROJECT_ROOT / output_dir
    return Config(postgres=postgres, apify=apify, tiktok=tiktok, output_dir=output_dir)
