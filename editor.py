from __future__ import annotations

from enum import Enum
import struct
import tkinter
from tkinter import filedialog
from typing import Any, Iterator
import json
import os
import sys
from pathlib import Path
import itertools
from typing import NamedTuple


position = tuple[float, float, float]
edge = tuple[position, position]

class Component(NamedTuple):
    edges: set[edge]
    indices: list[int]

def get_filepath() -> Path:
    m = tkinter.Tk()
    m.withdraw()
    filepath = filedialog.askopenfilename(
        initialdir=os.getcwd() + "\\",
        title="Select a GLTF File",
        filetypes=(
            ("GLTF files", "*.gltf"),
            ("JSON files", "*.json"),
            ("All files", "*.*"),
        ),
        master=m, #type: ignore
    )
    m.destroy()
    return Path(filepath)


ACCESSOR_TYPE_MULTIPLIER = {
    "SCALAR": 1,
    "VEC2": 2,
    "VEC3": 3,
    "VEC4": 4,
    "MAT2": 4,
    "MAT3": 9,
    "MAT4": 16,
}

COMPONENT_TYPE = {
    5120: "BYTE",
    5121: "UNSIGNED_BYTE",
    5122: "SHORT",
    5123: "UNSIGNED_SHORT",
    5125: "UNSIGNED_INT",
    5126: "FLOAT",
}

COMPONENT_FORMAT = {
    "BYTE": "b",
    "UNSIGNED_BYTE": "B",
    "SHORT": "h",
    "UNSIGNED_SHORT": "H",
    "UNSIGNED_INT": "I",
    "FLOAT": "f",
}

class Gltf:
    class Mode(Enum):
        REFERENCE = True
        INDEX = False

    def __init__(self, fpath: Path) -> None:
        self.inpath = fpath
        with open(self.inpath, mode="r", encoding="UTF-8") as f:
            self.json = json.load(f)

        self._node_mesh_reference_mode = self.Mode.INDEX

    def write(self, fpath: Path) -> None:
        with open(fpath, mode="w", encoding="UTF-8") as f:
            json.dump(self.json, f, indent=None)

    @property
    def node_mesh_reference_mode(self) -> Mode:
        return self._node_mesh_reference_mode
    
    @node_mesh_reference_mode.setter
    def node_mesh_reference_mode(self, mode: Mode) -> None:
        if mode == self._node_mesh_reference_mode:
            return
        if mode == self.Mode.INDEX:
            self._node_mesh_reference_mode = mode
            self._set_node_mesh_indices()
        elif mode == self.Mode.REFERENCE:
            self._node_mesh_reference_mode = mode
            self._set_node_mesh_references()

    def _set_node_mesh_references(self):
        nodes: list[dict[str, Any]] = self.json["nodes"]
        meshes: list[dict[str, Any]] = self.json["meshes"]
        for node in nodes:
            for i in range(len(node.get("children", []))):
                node["children"][i] = nodes[node["children"][i]]
            if "mesh" in node:
                node["mesh"] = meshes[node["mesh"]]


    def _set_node_mesh_indices(self):
        nodes: list[dict[str, Any]] = self.json["nodes"]
        meshes: list[dict[str, Any]] = self.json["meshes"]
        for node in nodes:
            if "mesh" in node:
                node["mesh"] = [mesh is node["mesh"] for mesh in meshes].index(True)
                assert node["mesh"] != -1
            if "children" in node:
                for i in range(len(node["children"])):
                    node["children"][i] = [
                        child is node["children"][i] for child in nodes
                    ].index(True)
                    assert node["children"][i] != -1

    def expand_multiprimitive_meshes(self):
        self.node_mesh_reference_mode = self.Mode.REFERENCE

        mesh_index = 0
        while mesh_index < len(self.json["meshes"]):
            mesh = self.json["meshes"][mesh_index]
            mesh_index += 1

            if len(mesh.get("primitives", [])) <= 1:
                continue

            added = []
            for i, primitive in enumerate(mesh["primitives"][1:]):
                added.append({"primitives": [primitive], "name": f'{mesh["name"]} ({i})'})
            self.json["meshes"] += added
            del mesh["primitives"][1:]

            node_index = 0
            num_original_nodes = len(self.json["nodes"])
            while node_index < num_original_nodes:
                node = self.json["nodes"][node_index]
                if node.get("mesh", None) is mesh and len(mesh) > 1:
                    children = []
                    for i, mesh in enumerate([node["mesh"]] + added):
                        self.json["nodes"].append(
                            {"mesh": mesh, "name": f'{node["name"]} ({i})'}
                        )
                        children.append(self.json["nodes"][-1])
                    del node["mesh"]
                    node["children"] = children
                node_index += 1

    def get_accessor(self, accessor_index: int) -> Iterator[tuple[Any, int | float]]:
        accessor = self.json["accessors"][accessor_index]
        buffer_view = self.json["bufferViews"][accessor["bufferView"]]
        buffer = self.json["buffers"][buffer_view["buffer"]]
        buffer_path = self.inpath.parent / buffer["uri"]

        multiplier = ACCESSOR_TYPE_MULTIPLIER[accessor["type"]]
        struct_format = COMPONENT_FORMAT[COMPONENT_TYPE[accessor["componentType"]]] * multiplier
        size = struct.calcsize(struct_format)

        with open(buffer_path, mode="rb") as f:
            f.seek(buffer_view["byteOffset"] + accessor["byteOffset"])
            data = f.read(size * accessor["count"])

        return struct.iter_unpack(struct_format, data)

    def split_disjoint_meshes(self):
        pass

    def _find_connected_components(self, mesh_index: int, primitive_index: int = 0) -> list[Component]:
        primitive = self.json["meshes"][mesh_index]["primitives"][primitive_index]
        normal_accessor_index = primitive["attributes"]["NORMAL"]
        position_accessor_index = primitive["attributes"]["POSITION"]
        index_accessor_index = primitive["indices"]

        normals = list(self.get_accessor(normal_accessor_index))
        positions = list(self.get_accessor(position_accessor_index))
        indices = map(lambda x: x[0], self.get_accessor(index_accessor_index))
        if primitive['mode'] == 4:
            def triangles(verticies):
                try:
                    while True:
                        yield next(verticies), next(verticies), next(verticies)
                except StopIteration:
                    pass
            indices = list(triangles(indices))
        else:
            raise NotImplementedError

        def get_edges(triangle):
            return [tuple(sorted([positions[triangle[0]], positions[triangle[1]]])),
                    tuple(sorted([positions[triangle[1]], positions[triangle[2]]])),
                    tuple(sorted([positions[triangle[2]], positions[triangle[0]]]))]

        components: list[Component] = []
        for i, triangle in enumerate(indices):
            edges = set(get_edges(triangle))
            components.append(Component(edges, [i]))
            connected_components = [component for component in components if component.edges & edges]
            for component in connected_components[1:]:
                connected_components[0].edges.update(component.edges)
                connected_components[0].indices.extend(component.indices)
                components.remove(component)

        return components


def main():
    if len(sys.argv) > 1:
        inpath = Path(sys.argv[1])
    else:
        inpath = get_filepath()

    gltf = Gltf(inpath)
    gltf.expand_multiprimitive_meshes()
    print(gltf._find_connected_components(int(input())))

    if len(sys.argv) > 2:
        outpath = Path(sys.argv[2])
    else:
        outpath = get_filepath()

    gltf.write(outpath)


if __name__ == "__main__":
    main()
