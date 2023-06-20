
import typing
from typing import TypedDict, Any

T = typing.TypeVar("T")
normal = position = tuple[float, float, float]
edge = tuple[position, position]

class GltfJson(TypedDict):
    asset: dict[str, Any]
    buffers: list[dict[str, Any]]
    bufferViews: list[dict[str, Any]]
    accessors: list[dict[str, Any]]
    meshes: list[dict[str, Any]]
    nodes: list[dict[str, Any]]
    scenes: list[dict[str, Any]]
    scene: int

