import reflex as rx

from web.state._improve import ImproveMixin
from web.state._library import LibraryMixin
from web.state._mapping import MappingMixin
from web.state._navigation import NavigationMixin
from web.state._preview import PreviewMixin
from web.state._upload import UploadMixin


class State(UploadMixin, MappingMixin, PreviewMixin, ImproveMixin, NavigationMixin, LibraryMixin, rx.State):
    """Combined application state."""

    pass
