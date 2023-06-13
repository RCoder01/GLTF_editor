from __future__ import annotations

from enum import Enum
import struct
import tkinter
from tkinter import filedialog
from typing import Any, Collection, Iterator
import json
import os
import sys
from pathlib import Path
import itertools
import typing


T = typing.TypeVar("T")
position = tuple[float, float, float]
edge = tuple[position, position]

class Component(typing.NamedTuple):
    points: set[position]
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

def find(item: T, items: list[T]) -> int:
    for i, x in enumerate(items):
        if x is item:
            return i
    raise ValueError(f"{item} not found in {items}")

class Gltf:
    # class Mode(Enum):
    #     REFERENCE = True
    #     INDEX = False

    def __init__(self, fpath: Path) -> None:
        self.inpath = fpath
        with open(self.inpath, mode="r", encoding="UTF-8") as f:
            self.json = json.load(f)

        self._node_mesh_reference = False
        self._accessor_data = False

    def write(self, fpath: Path) -> None:
        self.node_mesh_reference = False
        self.accessor_data = False
        for buffer in self.json["buffers"]:
            if not 'data' in buffer:
                continue
            with open(fpath.parent / buffer["uri"], mode="wb") as f:
                f.write(buffer["data"])
            del buffer["data"]
        with open(fpath, mode="w", encoding="UTF-8") as f:
            json.dump(self.json, f, indent=None, separators=(",", ":"))

    @property
    def node_mesh_reference(self) -> bool:
        return self._node_mesh_reference

    @node_mesh_reference.setter
    def node_mesh_reference(self, mode: bool) -> None:
        if mode == self._node_mesh_reference:
            return
        self._node_mesh_reference = mode
        if mode:
            self._set_node_mesh_references()
        else:
            self._set_node_mesh_indices()

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
                node["mesh"] = find(node["mesh"], meshes)
                assert node["mesh"] != -1
            if "children" in node:
                for i in range(len(node["children"])):
                    node["children"][i] = find(node["children"][i], nodes)
                    assert node["children"][i] != -1

    @property
    def accessor_data(self) -> bool:
        return self._accessor_data

    @accessor_data.setter
    def accessor_data(self, data: bool) -> None:
        if data == self._accessor_data:
            return
        self._accessor_data = data
        if data:
            self._add_accessor_data()
        else:
            self._remove_accessor_data()

    def _add_accessor_data(self):
        for buffer in self.json["buffers"]:
            buffer_path = self.inpath.parent / buffer["uri"]
            with open(buffer_path, mode="rb") as f:
                buffer["data"] = bytearray(f.read())

        for buffer_view in self.json["bufferViews"]:
            buffer = self.json["buffers"][buffer_view["buffer"]]
            buffer_view["data"] = buffer["data"][
                buffer_view["byteOffset"] : 
                buffer_view["byteOffset"] + buffer_view["byteLength"]
            ]

        for accessor in self.json["accessors"]:
            buffer_view = self.json["bufferViews"][accessor["bufferView"]]

            multiplier = ACCESSOR_TYPE_MULTIPLIER[accessor["type"]]
            struct_format = COMPONENT_FORMAT[COMPONENT_TYPE[accessor["componentType"]]] * multiplier
            size = struct.calcsize(struct_format)

            accessor["data"] = buffer_view["data"][
                accessor["byteOffset"] : 
                accessor["byteOffset"] + accessor["count"] * size
            ]

        for mesh in self.json["meshes"]:
            for primitive in mesh["primitives"]:
                for attribute in primitive["attributes"]:
                    primitive["attributes"][attribute] = self.json["accessors"][primitive["attributes"][attribute]]
                if "indices" in primitive:
                    primitive["indices"] = self.json["accessors"][primitive["indices"]]

    def _remove_accessor_data(self):
        for mesh in self.json["meshes"]:
            for primitive in mesh["primitives"]:
                for attribute in primitive["attributes"]:
                    primitive["attributes"][attribute] = find(primitive["attributes"][attribute], self.json["accessors"])
                if "indices" in primitive:
                    primitive["indices"] = find(primitive["indices"], self.json["accessors"])

        for bufferView in self.json["bufferViews"]:
            bufferView["newData"] = bytearray()

        for accessor in sorted(self.json["accessors"], key=lambda x: (x["bufferView"], x["byteOffset"])):
            bufferView = self.json["bufferViews"][accessor["bufferView"]]

            accessor["byteOffset"] = len(bufferView["newData"])
            bufferView["newData"] += accessor["data"]
            del accessor["data"]

        for bufferView in self.json["bufferViews"]:
            bufferView["data"][:len(bufferView["newData"])] = bufferView["newData"]
            bufferView["data"] = bufferView["data"][:len(bufferView["newData"])]
            bufferView["byteLength"] = len(bufferView["data"])
            del bufferView["newData"]

        for buffer in self.json["buffers"]:
            buffer["data"] = bytearray()

        for bufferView in sorted(self.json["bufferViews"], key=lambda x: (x["buffer"], x["byteOffset"])):
            buffer = self.json["buffers"][bufferView["buffer"]]
            bufferView["byteOffset"] = len(buffer["data"])
            buffer["data"] += bufferView["data"]
            del bufferView["data"]

    def expand_multiprimitive_meshes(self):
        self.node_mesh_reference = True

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
        # buffer_view = self.json["bufferViews"][accessor["bufferView"]]
        # buffer = self.json["buffers"][buffer_view["buffer"]]
        # buffer_path = self.inpath.parent / buffer["uri"]

        multiplier = ACCESSOR_TYPE_MULTIPLIER[accessor["type"]]
        struct_format = COMPONENT_FORMAT[COMPONENT_TYPE[accessor["componentType"]]] * multiplier

        # with open(buffer_path, mode="rb") as f:
        #     f.seek(buffer_view["byteOffset"] + accessor["byteOffset"])
        #     data = f.read(size * accessor["count"])
        self.accessor_data = True

        return struct.iter_unpack(struct_format, accessor["data"])

    def split_disconnected_meshes(self):
        pass

    def _find_connected_components(self, mesh_index: int, primitive_index: int = 0) -> list[Component]:
        primitive = self.json["meshes"][mesh_index]["primitives"][primitive_index]
        # normal_accessor_index = primitive["attributes"]["NORMAL"]
        position_accessor_index = primitive["attributes"]["POSITION"]
        index_accessor_index = primitive["indices"]

        # normals = list(self.get_accessor(normal_accessor_index))
        positions = typing.cast(list[position], list(self.get_accessor(position_accessor_index)))
        indices = map(lambda x: typing.cast(int, x[0]), self.get_accessor(index_accessor_index))
        if primitive['mode'] == 4:
            def triangles(verticies: Iterator[int]):
                try:
                    while True:
                        yield next(verticies), next(verticies), next(verticies)
                except StopIteration:
                    pass
            indices = list(triangles(indices))
        else:
            raise NotImplementedError()

        def get_points(triangle: Collection[int]) -> list[position]:
            return [positions[i] for i in triangle]

        components: list[Component] = []
        for i, triangle in enumerate(indices):
            points = set(get_points(triangle))
            components.append(Component(points, [i]))
            connected_components = [component for component in components if component.points & points]
            for component in connected_components[1:]:
                connected_components[0].points.update(component.points)
                connected_components[0].indices.extend(component.indices)
                components.remove(component)

        return components


def main():
    if len(sys.argv) > 1:
        inpath = Path(sys.argv[1])
    else:
        inpath = get_filepath()

    gltf = Gltf(inpath)
    process(gltf)

    if len(sys.argv) > 2:
        outpath = Path(sys.argv[2])
    else:
        outpath = get_filepath()

    gltf.node_mesh_reference = True
    gltf.accessor_data = True
    gltf.write(outpath)



def process(gltf: Gltf) -> None:
    # gltf.expand_multiprimitive_meshes()
    print(len(gltf._find_connected_components(1088)))

if __name__ == "__main__":
    main()
    # with open("temp.gltf", mode="r") as f1, open(r"D:\Documents - Hard Drive\CADAssistant\2910, 2023 Top Level Robot.gltf", mode='r') as f2:
    #     json1 = json.load(f1)
    #     json2 = json.load(f2)
    #     print(len([i for i, val in enumerate([comp1 != comp2 for comp1, comp2 in zip(json1['accessors'], json2['accessors'])]) if val]))
