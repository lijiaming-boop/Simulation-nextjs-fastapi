"""冷站全年8760h仿真引擎"""
# # 自定义端口启动
# streamlit run app.py --server.port 8501 --server.address 0.0.0.0
import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd


@dataclass
class ChillerGroup:
    name: str
    qty: int
    capacity_kw: float
    rated_power_kw: float
    rated_cop: float
    variable_freq: bool = False
    cop_curve: Optional[Dict[float, float]] = None


@dataclass
class PumpGroup:
    name: str
    qty: int
    power_kw: float
    flow_m3h: float
    variable_freq: bool = False


@dataclass
class TowerGroup:
    name: str
    qty: int
    fan_power_kw: float
    fans_per_tower: int = 1
    variable_freq: bool = False


@dataclass
class PlantConfig:
    chillers: List[ChillerGroup] = field(default_factory=list)
    chw_pumps: List[PumpGroup] = field(default_factory=list)
    cw_pumps: List[PumpGroup] = field(default_factory=list)
    towers: List[TowerGroup] = field(default_factory=list)
    monthly_chiller_count: List[int] = field(default_factory=lambda: [1]*12)
    monthly_chw_pump_hz: List[float] = field(default_factory=lambda: [50.0]*12)
    monthly_cw_pump_hz: List[float] = field(default_factory=lambda: [50.0]*12)
    monthly_tower_hz: List[float] = field(default_factory=lambda: [50.0]*12)
    monthly_chw_dt: List[float] = field(default_factory=lambda: [5.0]*12)
    monthly_cw_dt: List[float] = field(default_factory=lambda: [5.0]*12)
    monthly_chw_supply_temp: List[float] = field(default_factory=lambda: [7.0]*12)
    base_load_ratio: float = 0.70

    # todo 优化点 新增: 月度负载率修正系数（典型办公建筑）
    monthly_load_factor: List[float] = field(
        default_factory=lambda:
    [
        0.40,  # 1月  冬季低负荷
        0.40,  # 2月  冬季低负荷
        0.50,  # 3月  过渡季
        0.60,  # 4月  过渡季
        0.75,  # 5月  春末夏初
        0.90,  # 6月  夏季高峰前
        1.00,  # 7月  夏季峰值
        1.00,  # 8月  夏季峰值
        0.85,  # 9月  夏末秋初
        0.65,  # 10月 秋季过渡
        0.50,  # 11月 秋季转冬
        0.40   # 12月 冬季低负荷
    ])

    # 工作日/休息日逐时负载曲线（24h），替代硬编码 HOURLY_LOAD_FACTOR
    workday_hourly_curve: List[float] = field(default_factory=lambda: list(HOURLY_LOAD_FACTOR))
    offday_hourly_curve: List[float] = field(default_factory=lambda: list(HOURLY_LOAD_FACTOR))
    # 365 天日历：0=工作日, 1=休息日
    day_type: List[int] = field(default_factory=lambda: [0] * 365)

HOURLY_LOAD_FACTOR = np.array([
    0.60, 0.58, 0.55, 0.55, 0.58, 0.65,
    0.72, 0.80, 0.88, 0.95, 0.98, 1.00,
    0.98, 1.00, 1.00, 0.98, 0.95, 0.90,
    0.85, 0.80, 0.75, 0.72, 0.68, 0.63,
])


def interp_cop(cop_curve: Dict[float, float], plr: float) -> float:
    if not cop_curve:
        return 5.0
    loads = sorted(cop_curve.keys())
    cops = [cop_curve[k] for k in loads]
    plr = max(loads[0], min(loads[-1], plr))
    return float(np.interp(plr, loads, cops))


def estimate_screw_cop(rated_cop: float, plr: float) -> float:
    if plr <= 0:
        return 0.0
    plr_points = np.array([0.10, 0.25, 0.50, 0.75, 1.0])
    ratio_points = np.array([0.40, 0.65, 0.90, 1.02, 1.0])
    plr = max(0.1, min(1.0, plr))
    ratio = float(np.interp(plr, plr_points, ratio_points))
    return rated_cop * ratio


class PlantSimulator:
    def __init__(self, config: PlantConfig, monthly_ambient: List[float],
                 monthly_tower_outlet: Optional[List[float]] = None):
        self.config = config
        self.monthly_ambient = monthly_ambient
        # 以工作日曲线均值为归一化基准（休息日曲线共用此基准，保证休息日负载整体低于工作日）
        ref = float(np.mean(config.workday_hourly_curve))
        self._hourly_ref_mean = ref if ref > 0.001 else 1.0  # 防除零：全零曲线回退到 1.0


    def _get_dispatch(self, month: int) -> List[Tuple[ChillerGroup, int]]:
        n_total = self.config.monthly_chiller_count[month - 1]
        dispatch = []
        remaining = n_total
        for group in self.config.chillers:
            n = min(remaining, group.qty)
            if n > 0:
                dispatch.append((group, n))
                remaining -= n
            if remaining <= 0:
                break
        return dispatch

    def _calc_chiller_power(self, dispatch, plr):
        total_cooling = 0.0
        total_power = 0.0
        for group, n_on in dispatch:
            cooling = group.capacity_kw * n_on * plr
            total_cooling += cooling
            if group.cop_curve:
                cop = interp_cop(group.cop_curve, plr)
                if not group.variable_freq and plr < 0.95:
                    cop *= 0.92
            else:
                if group.variable_freq:
                    cop = estimate_screw_cop(group.rated_cop, plr)
                else:
                    cop = estimate_screw_cop(group.rated_cop, plr) * 0.95
            power = cooling / cop if cop > 0 else 0
            total_power += power
        return total_cooling, total_power

    def _calc_pump_power(self, pumps: List[PumpGroup], n_on: int, freq_hz: float):
        power = 0.0
        remaining = n_on
        for group in pumps:
            n = min(remaining, group.qty)
            if n <= 0:
                continue
            if group.variable_freq:
                ratio = freq_hz / 50.0
            else:
                ratio = 1.0
            power += group.power_kw * n * ratio ** 3
            remaining -= n
        return power

    def _calc_tower_power(self, towers: List[TowerGroup], n_on: int, freq_hz: float):
        power = 0.0
        remaining = n_on
        for group in towers:
            n = min(remaining, group.qty)
            if n <= 0:
                continue
            if group.variable_freq:
                ratio = freq_hz / 50.0
            else:
                ratio = 1.0
            power += group.fan_power_kw * group.fans_per_tower * n * ratio ** 3# 20/50=0.2
            remaining -= n
        return power

    def simulate_baseline(self) -> pd.DataFrame:
        hours, day_of_year, hour_of_day, months, ambient = self._generate_profile()

        records = []

        for h in range(8760):
            m = int(months[h])
            hod = int(hour_of_day[h])
            amb = float(ambient[h])

            # 传入 day_of_year 以根据工作日历选择曲线
            plr = self._calc_plr(hod, m, int(day_of_year[h]))

            dispatch = self._get_dispatch(m)
            n_chiller = sum(n for _, n in dispatch)

            total_cooling, chiller_power = self._calc_chiller_power(dispatch, plr)
            chw_pump_power = self._calc_pump_power(
                self.config.chw_pumps, n_chiller, self.config.monthly_chw_pump_hz[m-1])
            cw_pump_power = self._calc_pump_power(
                self.config.cw_pumps, n_chiller, self.config.monthly_cw_pump_hz[m-1])
            tower_power = self._calc_tower_power(
                self.config.towers, n_chiller, self.config.monthly_tower_hz[m-1])

            total_power = chiller_power + chw_pump_power + cw_pump_power + tower_power
            system_cop = total_cooling / total_power if total_power > 0 else 0

            records.append({
                "hour": h, "month": m, "day_of_year": int(day_of_year[h])+1,
                "hour_of_day": hod, "ambient_temp_c": round(amb, 2),
                "total_chiller_count": n_chiller, "load_ratio": round(plr, 4),
                "cooling_load_kw": round(total_cooling, 2),
                "chiller_power_kw": round(chiller_power, 2),
                "chw_pump_power_kw": round(chw_pump_power, 2),
                "cw_pump_power_kw": round(cw_pump_power, 2),
                "tower_fan_power_kw": round(tower_power, 2),
                "total_power_kw": round(total_power, 2),
                "system_cop": round(system_cop, 3),
                "chw_dt_c": self.config.monthly_chw_dt[m-1],
                "cw_dt_c": self.config.monthly_cw_dt[m-1],
            })
        return pd.DataFrame(records)

    def simulate_optimized(self, chw_target_dt: float = 5.0) -> pd.DataFrame:
        hours, day_of_year, hour_of_day, months, ambient = self._generate_profile()
        records = []
        for h in range(8760):
            m = int(months[h])
            hod = int(hour_of_day[h])
            amb = float(ambient[h])

            # 传入 day_of_year 以根据工作日历选择曲线
            plr = self._calc_plr(hod, m, int(day_of_year[h]))

            dispatch = self._get_dispatch(m)
            n_chiller = sum(n for _, n in dispatch)

            total_cooling, chiller_power = self._calc_chiller_power(dispatch, plr)

            # 冷冻泵: 温差控制
            chw_pump_power = self._calc_pump_power_optimized(
                self.config.chw_pumps, n_chiller, total_cooling, chw_target_dt)

            # 冷却泵: 工频泵保持不变，变频泵温差控制
            heat_rejection = total_cooling + chiller_power
            cw_has_vf = any(p.variable_freq for p in self.config.cw_pumps)
            if cw_has_vf:
                cw_pump_power = self._calc_pump_power_optimized(
                    self.config.cw_pumps, n_chiller, heat_rejection, chw_target_dt)

            else:
                cw_pump_power = self._calc_pump_power(
                    self.config.cw_pumps, n_chiller, 50.0)


            # 冷却塔: 变频塔优化
            tower_freq = self._calc_tower_optimal_freq(amb, m)
            tower_power = self._calc_tower_power(self.config.towers, n_chiller, tower_freq)

            total_power = chiller_power + chw_pump_power + cw_pump_power + tower_power
            system_cop = total_cooling / total_power if total_power > 0 else 0

            records.append({
                "hour": h, "month": m, "day_of_year": int(day_of_year[h])+1,
                "hour_of_day": hod, "ambient_temp_c": round(amb, 2),
                "total_chiller_count": n_chiller, "load_ratio": round(plr, 4),
                "cooling_load_kw": round(total_cooling, 2),
                "chiller_power_kw": round(chiller_power, 2),
                "chw_pump_power_kw": round(chw_pump_power, 2),
                "cw_pump_power_kw": round(cw_pump_power, 2),
                "tower_fan_power_kw": round(tower_power, 2),
                "total_power_kw": round(total_power, 2),
                "system_cop": round(system_cop, 3),
                "chw_dt_c": chw_target_dt,
                "cw_dt_c": chw_target_dt if cw_has_vf else self.config.monthly_cw_dt[m-1],
            })
        return pd.DataFrame(records)

    def _calc_pump_power_optimized(self, pumps, n_on, heat_kw, target_dt):
        cp = 4.186
        rho = 998.0
        power = 0.0
        remaining = n_on
        for group in pumps:
            n = min(remaining, group.qty)
            if n <= 0:
                continue
            if group.variable_freq:
                rated_flow_kgs = group.flow_m3h * n / 3600.0 * rho
                required_flow = heat_kw / (cp * target_dt)
                freq_ratio = max(0.55, min(1.0, required_flow / rated_flow_kgs))
                # 实际工程损耗: 变频器效率损失约3%、管网特性偏差约5%
                actual_efficiency = 0.92
                power += group.power_kw * n * freq_ratio ** 3 / actual_efficiency
            else:
                power += group.power_kw * n * 1.0
            remaining -= n
        return power

    def _calc_tower_optimal_freq(self, ambient_c: float, month: int) -> float:
        wet_bulb = ambient_c - 4.0
        tower_outlet = self.monthly_ambient[month-1] + 4.5
        tower_outlet = max(21.0, tower_outlet)
        approach = tower_outlet - wet_bulb
        # 保守策略: 最低不低于35%频率(实际工程安全裕量)
        if approach >= 14:
            return 20.0
        elif approach >= 10.5:
            return 30.0
        elif approach >= 7:
            return 40.0
        else:
            return 50.0

    # todo 优化点 新增的参数被考虑进核心算法
    # def _calc_plr(self, hour_of_day: int) -> float:
    #     hourly_factor = HOURLY_LOAD_FACTOR[hour_of_day]
    #     plr = self.config.base_load_ratio * hourly_factor / HOURLY_LOAD_FACTOR.mean()
    #     return float(np.clip(plr, 0.20, 0.95))
    def _calc_plr(self, hour_of_day: int, month: int, day_of_year: int = 0) -> float:
        """计算负载率（考虑季节差异 + 工作日/休息日双曲线）

        Args:
            hour_of_day: 小时索引 (0-23)
            month: 月份 (1-12)
            day_of_year: 年积日 (0-364)，用于查 day_type

        Returns:
            负载率 (0.2-0.95)
        """
        # 根据日历选择曲线：0=工作日, 1=休息日
        is_rest = bool(self.config.day_type[min(day_of_year, 364)])
        curve = self.config.offday_hourly_curve if is_rest else self.config.workday_hourly_curve
        hourly_factor = curve[hour_of_day]
        monthly_factor = self.config.monthly_load_factor[month - 1]

        # 综合计算：基础负载率 × 月度系数 × 小时系数 / 工作日均值（统一基准）
        plr = (
                self.config.base_load_ratio
                * monthly_factor
                * hourly_factor
                / self._hourly_ref_mean
        )

        return float(np.clip(plr, 0.20, 0.95))


    def _generate_profile(self):
        hours = np.arange(8760)
        day_of_year = hours // 24
        hour_of_day = hours % 24
        months = pd.date_range("2024-01-01", periods=8760, freq="h").month.values
        ambient = np.zeros(8760)
        for h in range(8760):
            m = months[h] - 1
            daily_var = 3.0 * math.sin(2 * math.pi * (hour_of_day[h] - 6) / 24)
            ambient[h] = self.monthly_ambient[m] + daily_var
        return hours, day_of_year, hour_of_day, months, ambient

    def generate_summary(self, df_base: pd.DataFrame, df_opt: pd.DataFrame) -> dict:
        base_cooling = df_base["cooling_load_kw"].sum()
        base_power = df_base["total_power_kw"].sum()
        opt_power = df_opt["total_power_kw"].sum()
        saving = base_power - opt_power

        summer_mask = df_base["month"].isin([6, 7, 8, 9])
        winter_mask = df_base["month"].isin([12, 1, 2])

        return {
            "baseline_cop": base_cooling / base_power if base_power > 0 else 0,
            "optimized_cop": base_cooling / opt_power if opt_power > 0 else 0,
            "annual_cooling_kwh": float(base_cooling),
            "baseline_power_kwh": float(base_power),
            "optimized_power_kwh": float(opt_power),
            "saving_kwh": float(saving),
            "saving_pct": float(saving / base_power * 100) if base_power > 0 else 0,
            "saving_cost_yuan": float(saving * 0.5),
            "baseline_chiller_kwh": float(df_base["chiller_power_kw"].sum()),
            "baseline_chw_pump_kwh": float(df_base["chw_pump_power_kw"].sum()),
            "baseline_cw_pump_kwh": float(df_base["cw_pump_power_kw"].sum()),
            "baseline_tower_kwh": float(df_base["tower_fan_power_kw"].sum()),
            "optimized_chiller_kwh": float(df_opt["chiller_power_kw"].sum()),
            "optimized_chw_pump_kwh": float(df_opt["chw_pump_power_kw"].sum()),
            "optimized_cw_pump_kwh": float(df_opt["cw_pump_power_kw"].sum()),
            "optimized_tower_kwh": float(df_opt["tower_fan_power_kw"].sum()),
            "summer_base_cop": float(
                df_base.loc[summer_mask, "cooling_load_kw"].sum() /
                df_base.loc[summer_mask, "total_power_kw"].sum()
            ) if df_base.loc[summer_mask, "total_power_kw"].sum() > 0 else 0,
            "summer_opt_cop": float(
                df_opt.loc[summer_mask, "cooling_load_kw"].sum() /
                df_opt.loc[summer_mask, "total_power_kw"].sum()
            ) if df_opt.loc[summer_mask, "total_power_kw"].sum() > 0 else 0,
            "winter_base_cop": float(
                df_base.loc[winter_mask, "cooling_load_kw"].sum() /
                df_base.loc[winter_mask, "total_power_kw"].sum()
            ) if df_base.loc[winter_mask, "total_power_kw"].sum() > 0 else 0,
            "winter_opt_cop": float(
                df_opt.loc[winter_mask, "cooling_load_kw"].sum() /
                df_opt.loc[winter_mask, "total_power_kw"].sum()
            ) if df_opt.loc[winter_mask, "total_power_kw"].sum() > 0 else 0,
        }


def infer_monthly_load_factors(ac_data: dict) -> List[float]:
    """从调研表月度能耗数据反推负载率系数

    Args:
        ac_data: 空调模块提取的数据，包含 monthly_data

    Returns:
        12个月的负载率系数列表（归一化到0-1）

    Example:
        >>> ac_data = {
        ...     "monthly_data": {
        ...         "0": {"total_energy": 50},  # 1月
        ...         "1": {"total_energy": 55},  # 2月
        ...         ...
        ...         "6": {"total_energy": 120}, # 7月（峰值）
        ...     }
        ... }
        >>> factors = infer_monthly_load_factors(ac_data)
        >>> print(factors)  # [0.42, 0.46, ..., 1.0, ...]
    """
    if not ac_data or "monthly_data" not in ac_data:
        # 返回默认值
        return [
            0.40, 0.40, 0.50, 0.60, 0.75, 0.90,
            1.00, 1.00, 0.85, 0.65, 0.50, 0.40
        ]

    monthly_data = ac_data["monthly_data"]
    energies = []

    for m in range(12):
        m_key = str(m)
        if m_key in monthly_data:
            energy = monthly_data[m_key].get("total_energy")
            if energy is not None and energy > 0:
                energies.append(float(energy))
            else:
                energies.append(None)
        else:
            energies.append(None)

    # 找出最大能耗（作为基准）
    valid_energies = [e for e in energies if e is not None]
    if not valid_energies:
        # 无有效数据，返回默认值
        return [
            0.40, 0.40, 0.50, 0.60, 0.75, 0.90,
            1.00, 1.00, 0.85, 0.65, 0.50, 0.40
        ]

    max_energy = max(valid_energies)

    # 计算归一化系数
    factors = []
    for energy in energies:
        if energy is not None:
            factors.append(energy / max_energy)
        else:
            # 缺失数据用相邻月份插值或默认值
            factors.append(0.5)

    return factors
