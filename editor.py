from __future__ import annotations

from enum import Enum
import struct
import tkinter
from tkinter import filedialog
from typing import Any, Sequence, Collection, Iterator, Generator, Iterable
import json
import os
import sys
from pathlib import Path
from itertools import chain
import typing
from typing import TYPE_CHECKING

from union_find import UnionFind #type: ignore

if TYPE_CHECKING:
    from _typeshed import SupportsRichComparisonT


T = typing.TypeVar("T")
normal = position = tuple[float, float, float]
edge = tuple[position, position]


class Component(typing.NamedTuple):
    points: set[position]
    tri_indices: list[int]


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
        master=m,  # type: ignore
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


def align(n: int, alignment: int) -> int:
    return ((n + alignment - 1) // alignment) * alignment


def groupby(iterator: Iterator[T], n: int) -> Generator[list[T], None, None]:
    try:
        while True:
            yield [next(iterator) for _ in range(n)]
    except StopIteration:
        pass


def pack_all(
    struct: struct.Struct, buffer: bytearray, data: Iterable[Iterable[Any]]
) -> None:
    for i, datum in enumerate(data):
        struct.pack_into(buffer, i * struct.size, *datum)


def component_max(
    vec2d: Sequence[Sequence[SupportsRichComparisonT]],
) -> list[SupportsRichComparisonT]:
    return [max(vec[axis] for vec in vec2d) for axis in range(len(vec2d[0]))]


def component_min(
    vec2d: Sequence[Sequence[SupportsRichComparisonT]],
) -> list[SupportsRichComparisonT]:
    return [min(vec[axis] for vec in vec2d) for axis in range(len(vec2d[0]))]


class Gltf:
    def __init__(self, fpath: Path) -> None:
        self.inpath = fpath
        with open(self.inpath, mode="r", encoding="UTF-8") as f:
            self.json = json.load(f)

        self._node_mesh_reference = False
        self._accessor_data = False
        self._accessor_reference = False

    def write(self, fpath: Path) -> None:
        self.node_mesh_reference = False
        self.accessor_data = False
        self.accessor_reference = False
        for buffer in self.json["buffers"]:
            if not "data" in buffer:
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
        mesh_ids = {id(mesh): i for i, mesh in enumerate(meshes)}
        node_ids = {id(node): i for i, node in enumerate(nodes)}
        # accessors: list[dict[str, Any]] = self.json["accessors"]
        for node in nodes:
            if "mesh" in node:
                node["mesh"] = mesh_ids[id(node["mesh"])]
                assert node["mesh"] != -1
            if "children" in node:
                for i in range(len(node["children"])):
                    node["children"][i] = node_ids[id(node["children"][i])]
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
                buffer_view["byteOffset"] : buffer_view["byteOffset"]
                + buffer_view["byteLength"]
            ]

        for index, accessor in enumerate(self.json["accessors"]):
            buffer_view = self.json["bufferViews"][accessor["bufferView"]]

            accessor["data"] = buffer_view["data"][
                accessor["byteOffset"] : accessor["byteOffset"]
                + accessor["count"] * self.accessor_struct_index(index).size
            ]

    def _remove_accessor_data(self):
        for bufferView in self.json["bufferViews"]:
            bufferView["data"] = bytearray()

        for accessor in sorted(
            self.json["accessors"], key=lambda x: (x["bufferView"], x["byteOffset"])
        ):
            bufferView = self.json["bufferViews"][accessor["bufferView"]]

            accessor["byteOffset"] = align(len(bufferView["data"]), 4)
            padding = accessor["byteOffset"] - len(bufferView["data"])
            bufferView["data"] += bytearray(padding)
            bufferView["data"] += accessor["data"]
            del accessor["data"]

        for bufferView in self.json["bufferViews"]:
            bufferView["byteLength"] = len(bufferView["data"])

        for buffer in self.json["buffers"]:
            buffer["data"] = bytearray()

        for bufferView in sorted(
            self.json["bufferViews"], key=lambda x: (x["buffer"], x["byteOffset"])
        ):
            buffer = self.json["buffers"][bufferView["buffer"]]
            bufferView["byteOffset"] = align(len(buffer["data"]), 4)
            padding = len(buffer["data"]) - bufferView["byteOffset"]
            bufferView["data"] += bytearray(padding)
            buffer["data"] += bufferView["data"]
            del bufferView["data"]

    @property
    def accessor_reference(self) -> bool:
        return self._accessor_reference

    @accessor_reference.setter
    def accessor_reference(self, reference: bool) -> None:
        if reference == self._accessor_reference:
            return
        self._accessor_reference = reference
        if reference:
            self._add_accessor_reference()
        else:
            self._remove_accessor_reference()

    def _add_accessor_reference(self):
        for mesh in self.json["meshes"]:
            for primitive in mesh["primitives"]:
                for attribute in primitive["attributes"]:
                    primitive["attributes"][attribute] = self.json["accessors"][
                        primitive["attributes"][attribute]
                    ]
                if "indices" in primitive:
                    primitive["indices"] = self.json["accessors"][primitive["indices"]]

    def _remove_accessor_reference(self):
        accessor_ids = {
            id(accessor): i for i, accessor in enumerate(self.json["accessors"])
        }
        for mesh in self.json["meshes"]:
            for primitive in mesh["primitives"]:
                for attribute in primitive["attributes"]:
                    primitive["attributes"][attribute] = accessor_ids[
                        id(primitive["attributes"][attribute])
                    ]
                if "indices" in primitive:
                    primitive["indices"] = accessor_ids[id(primitive["indices"])]

    def accessor_struct(self, accessor: dict[str, Any]) -> struct.Struct:
        multiplier = ACCESSOR_TYPE_MULTIPLIER[accessor["type"]]
        return struct.Struct(
            f'<{multiplier}{COMPONENT_FORMAT[COMPONENT_TYPE[accessor["componentType"]]]}'
        )

    def accessor_struct_index(self, accessor_index: int) -> struct.Struct:
        return self.accessor_struct(self.json["accessors"][accessor_index])

    def get_accessor_data(
        self, accessor: dict[str, Any]
    ) -> Iterator[tuple[int | float, ...]]:
        self.accessor_data = True
        return self.accessor_struct(accessor).iter_unpack(accessor["data"])

    def get_accessor_data_index(
        self, accessor_index: int
    ) -> Iterator[tuple[int | float, ...]]:
        accessor = self.json["accessors"][accessor_index]
        return self.get_accessor_data(accessor)

    def expand_multiprimitive_meshes(self):
        for mesh_index in range(len(self.json["meshes"])):
            self.expand_multiprimitive_mesh(mesh_index)

    def expand_multiprimitive_mesh(self, mesh_index: int) -> list[dict[str, Any]]:
        self.node_mesh_reference = True
        mesh = self.json["meshes"][mesh_index]

        if len(mesh.get("primitives", [])) <= 1:
            return []

        added = []
        for i, primitive in enumerate(mesh["primitives"][1:]):
            added.append({"primitives": [primitive], "name": f'{mesh["name"]} ({i})'})
        self.json["meshes"] += added
        del mesh["primitives"][1:]

        for node_index in range(len(self.json["nodes"])):
            node = self.json["nodes"][node_index]
            if node.get("mesh", None) is not mesh or len(mesh) <= 1:
                continue
            children = []
            for i, mesh in enumerate([node["mesh"]] + added):
                self.json["nodes"].append(
                    {"mesh": mesh, "name": f'{node["name"]} ({i})'}
                )
                children.append(self.json["nodes"][-1])
            del node["mesh"]
            node["children"] = children
        return added

    def split_disconnected_meshes(self):
        self.expand_multiprimitive_meshes()

        for mesh_index in range(len(self.json["meshes"])):
            self.split_disconnected_mesh(mesh_index)

    def split_disconnected_mesh(self, mesh_index: int):
        mesh = self.json["meshes"][mesh_index]
        if len(mesh["primitives"]) > 1:
            for added in self.expand_multiprimitive_mesh(mesh_index):
                self.split_disconnected_mesh(find(added, self.json["meshes"]))

        components = self._find_connected_components(mesh_index)

        self.node_mesh_reference = True
        self.accessor_data = True
        self.accessor_reference = True

        primitive = mesh["primitives"][0]

        indices_accessor = primitive["indices"]
        indices_struct = self.accessor_struct(indices_accessor)

        attribute_accessors: dict[str, Any] = {}
        attribute_values: dict[str, list[tuple[int | float, ...]]] = {}
        attribute_structs: dict[str, struct.Struct] = {}
        for attribute in primitive["attributes"]:
            attribute_accessors[attribute] = primitive["attributes"][attribute]
            attribute_values[attribute] = list(
                self.get_accessor_data(attribute_accessors[attribute])
            )
            attribute_structs[attribute] = self.accessor_struct(
                attribute_accessors[attribute]
            )

        indices_data_iter = (
            index for (index,) in self.get_accessor_data(indices_accessor)
        )
        if primitive["mode"] == 4:
            indices_data = list(groupby(indices_data_iter, 3))
        else:
            raise NotImplementedError()

        for component in components:
            new_primitive = primitive.copy()
            new_primitive["attributes"] = {}

            component_indices_map: dict[int, int] = {}
            component_indices_list: list[int] = []
            component_attribute_values: dict[str, list[tuple[int | float, ...]]] = {
                attribute: [] for attribute in primitive["attributes"]
            }
            for tri_index in component.tri_indices:
                indices = typing.cast(list[int], indices_data[tri_index])
                for index in indices:
                    if index not in component_indices_map:
                        component_indices_map[index] = len(component_indices_map)
                        for attribute in primitive["attributes"]:
                            component_attribute_values[attribute].append(
                                attribute_values[attribute][index]
                            )
                    component_indices_list.append(component_indices_map[index])

            new_indices_accessor = indices_accessor.copy()
            new_indices_accessor["count"] = len(component_indices_list)
            new_indices_accessor["data"] = bytearray(
                new_indices_accessor["count"] * indices_struct.size
            )

            pack_all(
                indices_struct,
                new_indices_accessor["data"],
                ((index,) for index in component_indices_list),
            )
            new_primitive["indices"] = new_indices_accessor
            self.json["accessors"].append(new_indices_accessor)

            for attribute in primitive["attributes"]:
                new_attribute_accessor = attribute_accessors[attribute].copy()
                attribute_data = component_attribute_values[attribute]
                if "max" in new_attribute_accessor:
                    new_attribute_accessor["max"] = component_max(attribute_data)
                if "min" in new_attribute_accessor:
                    new_attribute_accessor["min"] = component_min(attribute_data)
                new_attribute_accessor["count"] = len(attribute_data)
                size = (
                    new_attribute_accessor["count"] * attribute_structs[attribute].size
                )
                new_attribute_accessor["data"] = bytearray(size)
                pack_all(
                    attribute_structs[attribute],
                    new_attribute_accessor["data"],
                    attribute_data,
                )
                new_primitive["attributes"][attribute] = new_attribute_accessor
                self.json["accessors"].append(new_attribute_accessor)

            mesh["primitives"].append(new_primitive)

        mesh["primitives"].pop(0)
        # self.json["accessors"].remove(indices_accessor)
        # for accessor in attribute_accessors.values():
        #     self.json["accessors"].remove(accessor)
        self.expand_multiprimitive_mesh(mesh_index)

    def _find_connected_components(
        self, mesh_index: int, primitive_index: int = 0
    ) -> list[Component]:
        self.node_mesh_reference = True
        self.accessor_reference = False
        primitive = self.json["meshes"][mesh_index]["primitives"][primitive_index]
        # normal_accessor_index = primitive["attributes"]["NORMAL"]
        position_accessor_index = primitive["attributes"]["POSITION"]
        index_accessor_index = primitive["indices"]

        # normals = list(self.get_accessor(normal_accessor_index))
        positions = typing.cast(
            list[position], list(self.get_accessor_data_index(position_accessor_index))
        )
        indices = map(
            lambda x: typing.cast(int, x[0]),
            self.get_accessor_data_index(index_accessor_index),
        )
        if primitive["mode"] == 4:
            indices = groupby(indices, 3)
        else:
            raise NotImplementedError()

        def get_points(triangle: Collection[int]) -> list[position]:
            return [positions[i] for i in triangle]

        # return find_with_sets(indices, get_points)
        return find_with_union(indices, get_points)


def find_with_sets(indices, get_points):
    components: list[Component] = []
    for i, triangle in enumerate(indices):
        points = set(get_points(triangle))
        components.append(Component(points, [i]))
        connected_components = [
            component for component in components if component.points & points
        ]
        for component in connected_components[1:]:
            connected_components[0].points.update(component.points)
            connected_components[0].tri_indices.extend(component.tri_indices)
            components.remove(component)

    return components


def find_with_union(indices, get_points):
    point_map = {}
    tri_set = UnionFind()
    for i, triangle in enumerate(indices):
        tri_set.add()
        for point in get_points(triangle):
            if point in point_map:
                tri_set.union(point_map[point], i)
            else:
                point_map[point] = i

    return [Component(set(), group) for group in tri_set.groups()]


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

    gltf.write(outpath)


def process(gltf: Gltf) -> None:
    gltf.node_mesh_reference = True
    gltf.accessor_data = True
    # gltf.expand_multiprimitive_meshes()
    # print(len(gltf._find_connected_components(0)))
    # gltf.split_disconnected_mesh(186)
    gltf.split_disconnected_mesh(458)


if __name__ == "__main__":
    import cProfile

    profile = cProfile.run("main()", sort="tottime")
    # main()
    # # with open("temp.gltf", mode="r") as f1, open(r"D:\Documents - Hard Drive\CADAssistant\2910, 2023 Top Level Robot.gltf", mode='r') as f2:
    # with open("temp.gltf", mode="r") as f1, open(r"temp2.gltf", mode="r") as f2:
    #     json1 = json.load(f1)
    #     json2 = json.load(f2)
    #     print(json1 == json2)
    #     # print([a == b for a, b in zip(json1.values(), json2.values())])
    #     # print(len([i for i, val in enumerate([comp1 != comp2 for comp1, comp2 in zip(json1['accessors'], json2['accessors'])]) if val]))
