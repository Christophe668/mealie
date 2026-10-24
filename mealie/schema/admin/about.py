from mealie.schema._mealie import MealieModel


class AppStatistics(MealieModel):
    total_recipes: int
    total_users: int
    total_households: int
    total_groups: int
    uncategorized_recipes: int
    untagged_recipes: int


class AppInfo(MealieModel):
    production: bool
    version: str
    demo_status: bool
    allow_signup: bool
    allow_password_login: bool
    default_group_slug: str | None = None
    default_household_slug: str | None = None
    enable_oidc: bool
    oidc_redirect: bool
    oidc_provider_name: str
    enable_reverse_proxy_auth: bool
    token_time: int
    allowed_iframe_hosts: list[str] = []
    branding_name: str = "Mealie"
    branding_logo_url: str | None = None


class AppTheme(MealieModel):
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


class AppStartupInfo(MealieModel):
    is_first_login: bool
    """
    The applications best guess that a user hasn't logged in. Currently, it really
    on indicates that the 'changeme@example.com' user is still in the database. Once
    it is removed, this will always return False.
    """

    is_demo: bool


class AdminAboutInfo(AppInfo):
    versionLatest: str
    api_port: int
    api_docs: bool
    db_type: str
    db_url: str | None = None
    default_group: str
    default_household: str
    build_id: str
    recipe_scraper_version: str


class CheckAppConfig(MealieModel):
    email_ready: bool
    ldap_ready: bool
    ldap_disabled: bool
    oidc_ready: bool
    oidc_disabled: bool
    reverse_proxy_auth_ready: bool
    reverse_proxy_auth_disabled: bool
    base_url_set: bool
    is_up_to_date: bool
