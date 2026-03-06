# 卫星广播分发 SDN 控制器

[English](README.md) | 中文

一个面向低轨道（LEO）卫星广播分发系统的 SDN 控制器，具备动态资源调度功能，专为 Kubernetes 部署而设计。

## 功能特性

- **动态拓扑管理** — 跟踪 LEO 卫星星座变化，包括轨道面偏移、链路状态转换和节点心跳检测。
- **资源感知调度** — 根据节点负载（CPU、内存、带宽）和网络路径质量分配广播分发任务。
- **SDN 流规则生成** — 计算最短路径广播树，并在卫星节点上安装逐跳转发规则。
- **K8s 原生健康端点** — 提供 `/healthz` 和 `/readyz` 探针，用于存活性和就绪性检查。

## 前置条件

- Python 3.10 或更高版本
- pip（Python 包管理器）
- Docker（可选，用于容器化部署）
- kubectl + Kubernetes 集群（可选，用于 K8s 部署）

## 项目结构

```
src/satellite_sdn/
├── __init__.py     # 包标识和版本
├── __main__.py     # 独立运行入口
├── models.py       # 数据模型（SatelliteNode, InterSatelliteLink, FlowRule, BroadcastTask）
├── topology.py     # LEO 拓扑管理器（含 Dijkstra 最短路径路由）
├── scheduler.py    # 优先级感知资源调度器（含带宽预留）
└── controller.py   # SDN 控制器（含 HTTP 健康/API 服务器）
k8s/
├── configmap.yaml  # 控制器配置（可调参数）
├── deployment.yaml # K8s Deployment（含存活/就绪探针）
└── service.yaml    # ClusterIP Service（端口 8081）
tests/
├── test_models.py
├── test_topology.py
├── test_scheduler.py
└── test_controller.py
```

## 安装

```bash
# 克隆仓库
git clone https://github.com/niordepr/vim-config.git
cd vim-config

# 以开发模式安装（包含 pytest 用于运行测试）
pip install -e ".[dev]"
```

## 快速开始

### 作为独立服务运行控制器

```bash
python -m satellite_sdn
```

这将启动 SDN 控制器，并在端口 8081 上开启一个 HTTP 服务器，提供以下健康检查和管理端点：

| 端点        | 描述                                            |
| ----------- | ----------------------------------------------- |
| `/healthz`  | 存活探针 — 始终返回 `{"status":"ok"}`            |
| `/readyz`   | 就绪探针 — 控制器运行时返回 `ready`               |
| `/topology` | 当前星座拓扑的 JSON 快照                          |
| `/rules`    | 当前已安装的 SDN 流规则                           |

### 在代码中使用库

核心类可以直接在 Python 中导入和使用：

```python
from satellite_sdn.controller import SDNController
from satellite_sdn.models import (
    SatelliteNode,
    InterSatelliteLink,
    BroadcastTask,
)

# 1. 创建控制器
ctrl = SDNController(load_threshold=0.8)

# 2. 注册卫星节点
ctrl.register_node(SatelliteNode(node_id="sat-0", orbit_id=0, position_index=0))
ctrl.register_node(SatelliteNode(node_id="sat-1", orbit_id=0, position_index=1))
ctrl.register_node(SatelliteNode(node_id="sat-2", orbit_id=1, position_index=0))

# 3. 注册星间链路
ctrl.register_link(InterSatelliteLink(
    link_id="link-01", source_id="sat-0", target_id="sat-1", latency_ms=5.0,
))
ctrl.register_link(InterSatelliteLink(
    link_id="link-12", source_id="sat-1", target_id="sat-2", latency_ms=8.0,
))

# 4. 提交广播分发任务
results = ctrl.submit_tasks([
    BroadcastTask(
        task_id="task-1",
        source_node_id="sat-0",
        target_node_ids=["sat-1", "sat-2"],
        bandwidth_required_mbps=100.0,
        priority=5,
    )
])

# 5. 查看结果
for r in results:
    print(f"任务 {r.task_id}: 成功={r.success}")
    for target, path in r.assigned_paths.items():
        print(f"  -> {target}: {' -> '.join(path)}")
    for rule in r.flow_rules:
        print(f"  规则 {rule.rule_id}: {rule.node_id} -> {rule.next_hop}")
```

### 更新节点指标

节点指标可以在运行时更新，以反映实时资源使用情况：

```python
from satellite_sdn.models import NodeStatus, LinkStatus

# 更新 CPU / 内存 / 带宽指标
ctrl.update_node_metrics("sat-0", cpu_usage=0.6, memory_usage=0.4)
ctrl.update_node_metrics("sat-1", bandwidth_mbps=500.0)

# 更改节点或链路状态
ctrl.update_node_status("sat-2", NodeStatus.OFFLINE)
ctrl.update_link_status("link-12", LinkStatus.DOWN)
```

### 查询拓扑

```python
# 获取完整拓扑快照（可 JSON 序列化的字典）
snapshot = ctrl.topology_snapshot()

# 直接访问拓扑管理器
online = ctrl.topology.online_nodes
print(f"{len(online)} 个节点在线")

# 计算两个节点之间的最短路径
path, cost = ctrl.topology.shortest_path("sat-0", "sat-2")
print(f"路径: {' -> '.join(path)}, 代价: {cost}")
```

## 配置

控制器接受以下参数：

| 参数                   | 默认值  | 描述                                              |
| ---------------------- | ------- | ------------------------------------------------- |
| `heartbeat_timeout_s`  | `30.0`  | 无响应节点被标记为 OFFLINE 之前的等待秒数            |
| `load_threshold`       | `0.8`   | 节点可接受任务的最大负载分数（0–1）                  |
| `reconcile_interval_s` | `10.0`  | 周期性协调扫描的间隔秒数                            |

可以在创建控制器时设置这些参数：

```python
ctrl = SDNController(
    heartbeat_timeout_s=60.0,
    load_threshold=0.9,
    reconcile_interval_s=5.0,
)
```

也可以通过环境变量进行配置（适用于独立运行和 Kubernetes 部署）：

```bash
HEARTBEAT_TIMEOUT_S=60 LOAD_THRESHOLD=0.9 RECONCILE_INTERVAL_S=5 python -m satellite_sdn
```

部署到 Kubernetes 时，通过 `k8s/configmap.yaml` 中的 ConfigMap 进行配置，环境变量会自动注入到容器中。

## 运行测试

```bash
# 运行所有测试
pytest

# 运行测试并显示详细输出
pytest -v

# 运行特定测试文件
pytest tests/test_scheduler.py

# 运行特定测试类或方法
pytest tests/test_topology.py::TestShortestPath::test_simple_path
```

## Kubernetes 部署

### 构建和部署

```bash
# 构建容器镜像
docker build -t satellite-sdn-controller:latest .

# 应用所有 K8s 清单（ConfigMap、Deployment、Service）
kubectl apply -f k8s/

# 验证部署
kubectl get pods -l app=satellite-sdn-controller
kubectl logs -l app=satellite-sdn-controller
```

### 访问服务

在集群内部，控制器可通过 `satellite-sdn-controller:8081` 访问。

```bash
# 端口转发以进行本地访问
kubectl port-forward svc/satellite-sdn-controller 8081:8081

# 健康检查
curl http://localhost:8081/healthz

# 拓扑快照
curl http://localhost:8081/topology
```

### 自定义配置

编辑 `k8s/configmap.yaml` 并重新应用：

```yaml
data:
  HEARTBEAT_TIMEOUT_S: "60"
  LOAD_THRESHOLD: "0.9"
  RECONCILE_INTERVAL_S: "5"
```

```bash
kubectl apply -f k8s/configmap.yaml
kubectl rollout restart deployment/satellite-sdn-controller
```

## 许可证

MIT
