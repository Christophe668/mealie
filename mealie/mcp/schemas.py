from datetime import datetime

from mealie.schema._mealie import MealieModel


class McpAuthorizeRequestOut(MealieModel):
    request_id: str
    client_name: str | None
    client_id: str
    scopes: list[str]
    redirect_host: str


class McpAuthorizeDecision(MealieModel):
    request_id: str
    approve: bool


class McpAuthorizeRedirect(MealieModel):
    redirect_url: str


class McpConnectionOut(MealieModel):
    grant_id: str
    client_id: str
    client_name: str | None
    scopes: list[str]
    created_at: datetime
    last_used_at: datetime | None
