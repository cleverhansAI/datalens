from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "DataLens API"
    app_env: str = "dev"
    data_dir: str = "data"
    metadata_db_url: str = "sqlite:///data/datalens.db"
    embedding_dir: str = "embeddings"
    max_page_size: int = 500

    model_config = SettingsConfigDict(env_prefix="DATALENS_", extra="ignore")


settings = Settings()
