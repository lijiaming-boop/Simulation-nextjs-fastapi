"""测试模板配置"""
import pytest
from config.template_config import TemplateConfig


def test_get_template_standard():
    """测试获取标准版模板路径"""
    config = TemplateConfig()
    path = config.get_template_path("standard")
    assert "标准版" in path
    assert path.endswith(".xlsx")


def test_get_template_secondary_pump():
    """测试获取二次泵版模板路径"""
    config = TemplateConfig()
    path = config.get_template_path("secondary_pump")
    assert "二次泵版" in path
    assert path.endswith(".xlsx")


def test_unsupported_type_raises_error():
    """测试不支持的站房类型抛出异常"""
    config = TemplateConfig()
    with pytest.raises(ValueError, match="不支持的站房类型"):
        config.get_template_path("unsupported")


def test_template_exists():
    """测试模板文件确实存在"""
    from pathlib import Path
    config = TemplateConfig()

    for station_type in ["standard", "secondary_pump"]:
        path = config.get_template_path(station_type)
        assert Path(path).exists(), f"模板文件不存在: {path}"
