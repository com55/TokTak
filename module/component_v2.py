from dataclasses import dataclass, field, asdict
from typing import List, Any, Dict, Optional, Self, Union

# --- Core component classes ---

@dataclass
class ComponentBase:
    type: int
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

@dataclass
class ComponentV2:
    components: List[ComponentBase] = field(default_factory=list)
    def to_payload(self) -> Dict[str, Any]:
        return {
            "flags": 1 << 15,  # 32768
            "components": [comp.to_dict() for comp in self.components]
        }

@dataclass
class MediaItem:
    url: str
    description: Optional[str] = ""
    spoiler: Optional[bool] = False
    def to_dict(self) -> Dict[str, Any]:
        data = {"media": {"url": self.url}}
        if self.description:
            data["description"] = self.description
        if self.spoiler:
            data["spoiler"] = True
        return data

@dataclass
class TextDisplay(ComponentBase):
    content: str
    def __init__(self, content: str):
        super().__init__(type=10)
        self.content = content

class Button(ComponentBase):
    def __init__(
        self,
        style: int,
        label: Optional[str] = "",
        custom_id: Optional[str] = None,
        url: Optional[str] = None,
        emoji: Optional[Dict[str, Any]] = None,
        disabled: bool = False
    ):
        super().__init__(type=2)
        self.style = style
        self.label = label
        self.custom_id = custom_id
        self.url = url
        self.emoji = emoji
        self.disabled = disabled
    def to_dict(self) -> Dict[str, Any]:
        if self.style < 1 or self.style > 5:
            raise ValueError("Invalid button style. Must be between 1 and 5.")
        if self.style == 5 and not self.url:
            raise ValueError("Link buttons must have a URL.")
        if self.style != 5 and not self.custom_id:
            raise ValueError("Non-link buttons must have a custom ID.")
        d = {
            "type": self.type,
            "label": self.label,
            "style": self.style,
            "disabled": self.disabled
        }
        if self.custom_id:
            d["custom_id"] = self.custom_id
        if self.url:
            d["url"] = self.url
        if self.emoji:
            d["emoji"] = self.emoji
        return d

class ActionRow(ComponentBase):
    def __init__(self, components: List[Button]):
        super().__init__(type=1)
        self.components = components
    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": self.type,
            "components": [c.to_dict() for c in self.components]
        }

class Thumbnail(ComponentBase):
    def __init__(self, url: str, description: Optional[str] = "", spoiler: bool = False):
        super().__init__(type=11)
        self.url = url
        self.description = description
        self.spoiler = spoiler
    def to_dict(self) -> Dict[str, Any]:
        data = {
            "type": self.type,
            "media": {"url": self.url, "height":40, "width":40},
        }
        if self.description:
            data["description"] = self.description
        if self.spoiler:
            data["spoiler"] = True
        return data

class MediaGallery(ComponentBase):
    def __init__(self, items: List[MediaItem]):
        super().__init__(type=12)
        self.items = items
    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": self.type,
            "items": [item.to_dict() for item in self.items]
        }

class Separator(ComponentBase):
    def __init__(self, divider: bool = True, spacing: int = 1):
        super().__init__(type=14)
        if spacing not in (1, 2):
            raise ValueError("Spacing must be either 1 (small) or 2 (large).")
        self.divider = divider
        self.spacing = spacing
    def to_dict(self) -> Dict[str, Any]:
        data = {
            "type": self.type,
            "divider": self.divider,
            "spacing": self.spacing
        }
        return data

class Section(ComponentBase):
    def __init__(
        self,
        components: List[TextDisplay],
        accessory: Optional[List[Union[Thumbnail, Button]]] = None,
    ):
        super().__init__(type=9)
        if len(components) > 3:
            raise ValueError("Section can have a maximum of 3 components.")
        self.components = components
        self.accessory = accessory if accessory else None
    def to_dict(self) -> Dict[str, Any]:
        d = {
            "type": self.type,
            "components": [c.to_dict() for c in self.components]
        }
        if self.accessory:
            d["accessory"] = self.accessory
        return d

class Container(ComponentBase):
    def __init__(
        self,
        components: list[Union[ActionRow, TextDisplay, Section, MediaGallery, Separator]],
        accent_color: Optional[int] = None,
        spoiler: Optional[bool] = False
    ):
        super().__init__(type=17)
        self.components = components
        self.accent_color = accent_color
        self.spoiler = spoiler
    def to_dict(self) -> Dict[str, Any]:
        d = {
            "type": self.type,
            "components": [c.to_dict() for c in self.components],
        }
        if self.accent_color is not None:
            d["accent_color"] = self.accent_color
        if self.spoiler:
            d["spoiler"] = True
        return d

# --- Builder Pattern with Method Chaining ---

class ActionRowBuilder:
    def __init__(self, parent_builder):
        self.parent = parent_builder
        self.buttons: List[Button] = []
    def button(self, style: int, label: str, custom_id: Optional[str] = None, url: Optional[str] = None, emoji=None, disabled=False):
        self.buttons.append(Button(style, label, custom_id, url, emoji, disabled))
        return self
    def end_action_row(self):
        self.parent._add_component(ActionRow(self.buttons))
        return self.parent

class SectionBuilder:
    def __init__(self, parent_builder):
        self.parent = parent_builder
        self.components: List[TextDisplay] = []
        self.accessory: Dict[str, Union[Thumbnail, Button]] = {}
    def text(self, content: str):
        self.components.append(TextDisplay(content))
        return self
    def thumbnail(self, url: str, description="", spoiler=False) -> Self:
        self.accessory.update(Thumbnail(url, description, spoiler).to_dict())
        return self
    def button(self, style: int, label: str, custom_id: Optional[str] = None, url: Optional[str] = None, emoji=None, disabled=False):
        self.accessory.update(Button(style, label, custom_id, url, emoji, disabled).to_dict())
        return self
    def end_section(self):
        self.parent._add_component(Section(self.components, self.accessory))
        return self.parent

class MediaGalleryBuilder:
    def __init__(self, parent_builder):
        self.parent = parent_builder
        self.items: List[MediaItem] = []
    def media(self, url: str, description="", spoiler=False):
        self.items.append(MediaItem(url, description, spoiler))
        return self
    def end_gallery(self):
        self.parent._add_component(MediaGallery(self.items))
        return self.parent

class ContainerBuilder:
    def __init__(self, parent_builder, id=None, accent_color=None, spoiler=False):
        self.parent = parent_builder
        self.components: List[ComponentBase] = []
        self.id = id
        self.accent_color = accent_color
        self.spoiler = spoiler
    def text(self, content: str) -> Self:
        self.components.append(TextDisplay(content))
        return self
    def section(self):
        return SectionBuilder(parent_builder=self)
    def gallery(self):
        return MediaGalleryBuilder(parent_builder=self)
    def separator(self, divider=True, spacing=1) -> Self:
        self.components.append(Separator(divider, spacing))
        return self
    def action_row(self):
        return ActionRowBuilder(parent_builder=self)
    def _add_component(self, comp: ComponentBase) -> None:
        self.components.append(comp)
    def end_container(self):
        self.parent._add_component(Container(self.components, self.accent_color, self.spoiler))
        return self.parent

class ComponentV2Builder:
    def __init__(self):
        self.components: List[ComponentBase] = []
    def text(self, content: str):
        self.components.append(TextDisplay(content))
        return self
    def section(self):
        return SectionBuilder(self)
    def gallery(self):
        return MediaGalleryBuilder(self)
    def container(self, id=None, accent_color=None, spoiler=False):
        return ContainerBuilder(self, id, accent_color, spoiler)
    def separator(self, divider=True, spacing=1):
        self.components.append(Separator(divider, spacing))
        return self
    def _add_component(self, comp: ComponentBase):
        self.components.append(comp)
    def build(self):
        return ComponentV2(self.components)
    def to_payload(self) -> Dict[str, Any]:
        return ComponentV2(self.components).to_payload()