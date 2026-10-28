"""Parse a BPMN 2.0 XML file and extract the list of task nodes.

Only the pieces needed for performance analysis are extracted: each task's
id, name and BPMN element type (userTask, serviceTask, ...). Namespaces are
handled generically (by local tag name) so the parser works with files
exported from Camunda, bpmn.io, Signavio, Bizagi, etc.
"""
from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass, field


TASK_TAGS = {
    "task",
    "usertask",
    "servicetask",
    "scripttask",
    "manualtask",
    "businessruletask",
    "sendtask",
    "receivetask",
    "calltask",
    "subprocess",
}

# Gateway mà tại đó CHỈ MỘT nhánh được thực hiện cho mỗi case (loại trừ lẫn
# nhau) — parallelGateway (AND, tất cả nhánh đều chạy) và inclusiveGateway
# (OR, có thể nhiều nhánh cùng chạy) không thuộc nhóm này nên không suy ra
# quan hệ loại trừ.
EXCLUSIVE_GATEWAY_TAGS = {"exclusivegateway", "eventbasedgateway"}
GATEWAY_TAGS = EXCLUSIVE_GATEWAY_TAGS | {"parallelgateway", "inclusivegateway", "complexgateway"}


@dataclass
class BpmnTask:
    id: str
    name: str
    element_type: str


@dataclass
class BpmnModel:
    tasks: list = field(default_factory=list)  # list[BpmnTask]
    # task_id -> list[task_id] các task LIỀN TRƯỚC gần nhất trong luồng BPMN
    # (đã bỏ qua gateway/event trung gian). Rỗng nghĩa là task đầu tiên của
    # quy trình (không có task nào bắt buộc phải xong trước nó).
    predecessors: dict = field(default_factory=dict)
    # task_id -> set[task_id] các task ở NHÁNH KHÁC của cùng 1 exclusive/
    # event-based gateway (loại trừ lẫn nhau — case chỉ đi 1 trong các nhánh).
    # Nếu case đã làm 1 trong các task này thì KHÔNG được coi task còn lại là
    # "bị bỏ sót" nữa, vì đó vốn là nhánh không được chọn.
    exclusive_alternatives: dict = field(default_factory=dict)

    def id_index(self) -> dict:
        return {t.id: t for t in self.tasks if t.id}

    def name_index(self) -> dict:
        """Lower-cased, trimmed name -> BpmnTask (first match wins)."""
        idx = {}
        for t in self.tasks:
            key = (t.name or "").strip().lower()
            if key and key not in idx:
                idx[key] = t
        return idx


def _local_tag(tag: str) -> str:
    return tag.split("}", 1)[-1].lower() if "}" in tag else tag.lower()


def _nearest_predecessor_tasks(node_id: str, incoming: dict, task_ids: set, visited=None) -> list:
    """Đi ngược theo sequenceFlow từ `node_id`, trả về danh sách task gần
    nhất (bỏ qua gateway/event trung gian) dẫn tới `node_id`."""
    if visited is None:
        visited = set()
    if node_id in visited:
        return []
    visited.add(node_id)

    found = []
    for src in incoming.get(node_id, []):
        if src in task_ids:
            if src not in found:
                found.append(src)
        else:
            for t in _nearest_predecessor_tasks(src, incoming, task_ids, visited):
                if t not in found:
                    found.append(t)
    return found


def _first_tasks_from(node_id: str, outgoing: dict, task_ids: set, visited=None) -> list:
    """Đi XUÔI theo sequenceFlow từ `node_id`, trả về danh sách task gần
    nhất (bỏ qua gateway/event trung gian) mà nhánh này dẫn tới."""
    if visited is None:
        visited = set()
    if node_id in visited:
        return []
    visited.add(node_id)

    if node_id in task_ids:
        return [node_id]

    found = []
    for tgt in outgoing.get(node_id, []):
        for t in _first_tasks_from(tgt, outgoing, task_ids, visited):
            if t not in found:
                found.append(t)
    return found


def parse_bpmn(file_path: str) -> BpmnModel:
    """Parse the .bpmn / .xml file and return the BpmnModel with all tasks
    cùng quan hệ task liền-trước và quan hệ loại-trừ-lẫn-nhau (nhánh khác
    của cùng 1 exclusive/event-based gateway) suy ra từ các sequenceFlow."""
    tree = ET.parse(file_path)
    root = tree.getroot()

    tasks = []
    gateways: dict = {}  # gateway_id -> tag (chỉ các exclusive/event-based)
    incoming: dict = {}  # node_id -> list[node_id nguồn]
    outgoing: dict = {}  # node_id -> list[node_id đích]
    for elem in root.iter():
        tag = _local_tag(elem.tag)
        if tag in TASK_TAGS:
            task_id = elem.get("id", "")
            name = elem.get("name", "") or task_id
            tasks.append(BpmnTask(id=task_id, name=name, element_type=tag))
        elif tag in EXCLUSIVE_GATEWAY_TAGS:
            gw_id = elem.get("id", "")
            if gw_id:
                gateways[gw_id] = tag
        elif tag == "sequenceflow":
            src = elem.get("sourceRef")
            tgt = elem.get("targetRef")
            if src and tgt:
                incoming.setdefault(tgt, []).append(src)
                outgoing.setdefault(src, []).append(tgt)

    if not tasks:
        raise ValueError(
            "Không tìm thấy Task nào trong file BPMN. Hãy kiểm tra lại file .bpmn."
        )

    task_ids = {t.id for t in tasks if t.id}
    predecessors = {}
    for t in tasks:
        if not t.id:
            continue
        predecessors[t.id] = _nearest_predecessor_tasks(t.id, incoming, task_ids)

    exclusive_alternatives: dict = {tid: set() for tid in task_ids}
    for gw_id in gateways:
        branch_task_sets = [
            set(_first_tasks_from(tgt, outgoing, task_ids))
            for tgt in outgoing.get(gw_id, [])
        ]
        for i, branch_set in enumerate(branch_task_sets):
            others = set()
            for j, other_set in enumerate(branch_task_sets):
                if j != i:
                    others |= other_set
            for tid in branch_set:
                exclusive_alternatives.setdefault(tid, set())
                exclusive_alternatives[tid] |= (others - branch_set)

    return BpmnModel(
        tasks=tasks, predecessors=predecessors, exclusive_alternatives=exclusive_alternatives
    )
