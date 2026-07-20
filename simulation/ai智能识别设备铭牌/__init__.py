"""AI 智能识别设备铭牌模块

独立的 AI 识图子模块，专注解决设备铭牌照片/设备清单的 AI 识别场景：
  - ai_vision.py：单图场景（COP曲线、单组拓扑、设备清单识别）
  - ai_all_vision.py：多图批量场景（多张铭牌照片一次性识别多组主机）

使用方式：
    # 单图识别
    from simulation.ai智能识别设备铭牌 import extract_plant_topology, extract_cop_curve
    result = extract_plant_topology(content_type="image", image_data=img_bytes)

    # 多图批量识别
    from simulation.ai智能识别设备铭牌 import extract_multi_chiller_topology
    result = extract_multi_chiller_topology(images=[img1, img2])

依赖：项目 .env 中的 ANTHROPIC_BASE_URL / ANTHROPIC_API_KEY / ANTHROPIC_MODEL
"""

from .ai_vision import extract_plant_topology, extract_cop_curve
from .ai_all_vision import extract_multi_chiller_topology

__all__ = [
    "extract_plant_topology",
    "extract_cop_curve",
    "extract_multi_chiller_topology",
]
