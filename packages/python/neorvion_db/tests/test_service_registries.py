import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[4]
SERVICES = ("erp", "iam", "knowledge")


@pytest.mark.parametrize("service", SERVICES)
def test_service_registry_and_repository_scan(service: str) -> None:
    """用各服务自己的虚拟环境导入模型，避免三个 app 包互相覆盖，也不启动数据库。"""
    root = REPO / "services" / service
    python = root / ".venv" / "Scripts" / "python.exe"
    if not python.exists():
        pytest.fail(f"缺少 {python}。请先在 {root} 执行 uv sync")
    completed = subprocess.run(
        [str(python), "-m", "neorvion_db.check_service", str(root)],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert "static=ok" in completed.stdout
    assert "privilege_exposure=ok" in completed.stdout
    assert "tenant_scoped=" in completed.stdout
