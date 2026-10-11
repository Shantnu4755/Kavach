from ..schemas.event import EventFilter
from ..services.outbox_service import OutboxService
from .base import BaseView


class EventListView(BaseView):
    def __init__(self) -> None:
        self.service = OutboxService()

    def get(self):
        events = self.service.recent(self.parse_query(EventFilter))
        return {"data": [e.model_dump(mode="json") for e in events]}, 200
