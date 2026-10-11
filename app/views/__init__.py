from flask import Flask

from .claims import ClaimActionView, ClaimDetailView, ClaimListView, ClaimStatsView
from .events import EventListView
from .health import HealthView
from .policies import PolicyDetailView, PolicyListView


def register_routes(app: Flask) -> None:
    app.add_url_rule("/health", view_func=HealthView.as_view("health"))
    # project-specific routes are added below this line
    app.add_url_rule("/policies", view_func=PolicyListView.as_view("policies"))
    app.add_url_rule("/policies/<uuid:policy_id>", view_func=PolicyDetailView.as_view("policy_detail"))
    app.add_url_rule("/claims", view_func=ClaimListView.as_view("claims"))
    app.add_url_rule("/claims/stats", view_func=ClaimStatsView.as_view("claim_stats"))
    app.add_url_rule("/claims/<uuid:claim_id>", view_func=ClaimDetailView.as_view("claim_detail"))
    app.add_url_rule("/claims/<uuid:claim_id>/<action>", view_func=ClaimActionView.as_view("claim_action"))
    app.add_url_rule("/events", view_func=EventListView.as_view("events"))
