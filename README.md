# dock2k8s

一个将 Docker Compose 项目转换为 Kubernetes 清单并部署到 K8S 集群的命令行工具。

## 功能

- 解析 `docker-compose.yml` 文件
- 自动生成 Kubernetes 资源清单（Deployment、Service、ConfigMap）
- 支持端口映射、环境变量、副本数配置
- 可直接通过 `kubectl` 部署到集群
- 支持导出 YAML 清单文件

## 安装

```bash
pip install -e .
```

## 使用方法

### 生成 Kubernetes 清单

```bash
# 从 docker-compose.yml 生成 K8S 清单并输出到 stdout
dock2k8s generate docker-compose.yml

# 输出到文件
dock2k8s generate docker-compose.yml -o k8s-manifests.yaml

# 指定命名空间
dock2k8s generate docker-compose.yml -n my-namespace
```

### 直接部署到集群

```bash
# 部署到默认命名空间
dock2k8s deploy docker-compose.yml

# 部署到指定命名空间
dock2k8s deploy docker-compose.yml -n my-namespace
```

## 支持的 Docker Compose 特性

| Docker Compose | Kubernetes |
|---|---|
| `image` | Deployment container image |
| `ports` | Service (ClusterIP) |
| `environment` | ConfigMap + envFrom |
| `replicas` (deploy) | Deployment replicas |
| `command` | Container command |

## 示例

```yaml
# docker-compose.yml
services:
  web:
    image: nginx:latest
    ports:
      - "80:80"
    environment:
      - APP_ENV=production
  api:
    image: myapp/api:v1
    ports:
      - "8080:8080"
    environment:
      - DB_HOST=db
      - DB_PORT=5432
```

```bash
dock2k8s generate docker-compose.yml
```

## 开发

```bash
# 安装开发依赖
pip install -e ".[dev]"

# 运行测试
python -m pytest tests/
```

## License

MIT
