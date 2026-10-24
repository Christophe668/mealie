from pydantic_settings import BaseSettings, SettingsConfigDict


class Theme(BaseSettings):
    light_primary: str = "#F2B01E"
    light_accent: str = "#17201B"
    light_secondary: str = "#5B655F"
    light_success: str = "#489B4B"  # #43A047 at 90% HSL saturation
    light_info: str = "#2276C9"  # #1976D2 at 90% HSL saturation
    light_warning: str = "#F26F0D"  # #FF6D00 at 90% HSL saturation
    light_error: str = "#E75B58"  # #EF5350 at 90% HSL saturation

    dark_primary: str = "#F2B01E"
    dark_accent: str = "#ECEEEA"
    dark_secondary: str = "#9AA49E"
    dark_success: str = "#489B4B"  # #43A047 at 90% HSL saturation
    dark_info: str = "#2276C9"  # #1976D2 at 90% HSL saturation
    dark_warning: str = "#F26F0D"  # #FF6D00 at 90% HSL saturation
    dark_error: str = "#E75B58"  # #EF5350 at 90% HSL saturation
    model_config = SettingsConfigDict(env_prefix="theme_", extra="allow")
