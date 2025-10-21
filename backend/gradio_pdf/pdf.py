from __future__ import annotations
from typing import Any, Callable

from gradio.components.base import Component
from gradio.data_classes import FileData
from gradio import processing_utils


class PDF(Component):
    """PDF COMPONENT"""

    EVENTS = ["change", "upload"]

    data_model = FileData

    def __init__(
        self,
        value: Any = None,
        *,
        height: int | None = None,
        label: str | None = None,
        info: str | None = None,
        show_label: bool | None = None,
        container: bool = True,
        scale: int | None = None,
        min_width: int | None = None,
        interactive: bool | None = None,
        visible: bool = True,
        elem_id: str | None = None,
        elem_classes: list[str] | str | None = None,
        render: bool = True,
        load_fn: Callable[..., Any] | None = None,
        every: float | None = None,
        starting_page: int | None = 1,
        enable_zoom: bool = False,
        min_zoom: float = 1.0,
        max_zoom: float = 3.0,
    ):
        super().__init__(
            value,
            label=label,
            info=info,
            show_label=show_label,
            container=container,
            scale=scale,
            min_width=min_width,
            interactive=interactive,
            visible=visible,
            elem_id=elem_id,
            elem_classes=elem_classes,
            render=render,
            load_fn=load_fn,
            every=every,
        )
        self.height = height
        self.starting_page = starting_page
        self.enable_zoom = enable_zoom
        self.min_zoom = min_zoom
        self.max_zoom = max_zoom

    def preprocess(self, payload: FileData) -> str:
        if payload:
          return payload.path
        else:
          return None

    def postprocess(self, value: str | None) -> FileData | None:
        if not value:
            return None
        return FileData(path=value)

    def example_inputs(self):
        return "https://gradio-builds.s3.amazonaws.com/assets/pdf-guide/fw9.pdf"
