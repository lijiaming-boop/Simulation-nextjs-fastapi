"""冷站全年8760h仿真引擎"""
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
    def __init__(self, config: PlantConfig, monthly_ambient: List[float]):
        self.config = config
        self.monthly_ambient = monthly_ambient

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
            power += group.fan_power_kw * group.fans_per_tower * n * ratio ** 3
            remaining -= n
        return power

    def simulate_baseline(self) -> pd.DataFrame:
        hours, day_of_year, hour_of_day, months, ambient = self._generate_profile()
        records = []
        for h in range(8760):
            m = int(months[h])
            hod = int(hour_of_day[h])
            amb = float(ambient[h])

            plr = self._calc_plr(hod)
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

            plr = self._calc_plr(hod)
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

    def _calc_plr(self, hour_of_day: int) -> float:
        hourly_factor = HOURLY_LOAD_FACTOR[hour_of_day]
        plr = self.config.base_load_ratio * hourly_factor / HOURLY_LOAD_FACTOR.mean()
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
