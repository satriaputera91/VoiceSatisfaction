from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    REDIS_URL: str = "redis://localhost:6379"
    STREAM_MAXLEN: int = 10000

    VAD_WORKER_COUNT: int = 2
    TRANSCRIBER_WORKER_COUNT: int = 2
    VAD_THRESHOLD: float = 0.5
    VAD_MIN_SILENCE_MS: int = 300
    WHISPER_MODEL: str = "tiny"
    WHISPER_DEVICE: str = "cpu"
    WHISPER_COMPUTE_TYPE: str = "int8"
    WHISPER_LANGUAGE: str = ""

    COMMAND_WORKER_COUNT: int = 2
    COMMAND_MATCH_THRESHOLD: float = 75.0

    SESSION_TTL_SECONDS: int = 1800
    SAMPLE_RATE: int = 16000

    HOST: str = "0.0.0.0"
    PORT: int = 8000

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
