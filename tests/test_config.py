from backend.app.core.config import Settings


def test_web_origins_accepts_documented_comma_separated_value() -> None:
    settings = Settings(web_origins="http://127.0.0.1:3000, http://localhost:3000")

    assert settings.web_origins == [
        "http://127.0.0.1:3000",
        "http://localhost:3000",
    ]
