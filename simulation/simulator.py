"""冷站全年8760h仿真引擎"""
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

    @staticmethod
    def _maybe_scalar(value, *inputs):
        if all(np.isscalar(input_value) for input_value in inputs):
            return float(np.asarray(value))
        return value

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
        plr_arr = np.asarray(plr, dtype=float)
        total_cooling = np.zeros_like(plr_arr, dtype=float)
        total_power = np.zeros_like(plr_arr, dtype=float)
        for group, n_on in dispatch:
            cooling = group.capacity_kw * n_on * plr_arr
            total_cooling += cooling
            if group.cop_curve:
                loads = np.array(sorted(group.cop_curve.keys()), dtype=float)
                cops = np.array([group.cop_curve[k] for k in loads], dtype=float)
                cop = np.interp(np.clip(plr_arr, loads[0], loads[-1]), loads, cops)
                if not group.variable_freq:
                    cop = np.where(plr_arr < 0.95, cop * 0.92, cop)
            else:
                plr_points = np.array([0.10, 0.25, 0.50, 0.75, 1.0])
                ratio_points = np.array([0.40, 0.65, 0.90, 1.02, 1.0])
                ratio = np.interp(np.clip(plr_arr, 0.1, 1.0), plr_points, ratio_points)
                cop = group.rated_cop * ratio
                if not group.variable_freq:
                    cop *= 0.95
            power = np.divide(cooling, cop, out=np.zeros_like(total_power), where=cop > 0)
            total_power += power
        if np.isscalar(plr):
            return float(total_cooling), float(total_power)
        return total_cooling, total_power

    def _calc_pump_power(self, pumps: List[PumpGroup], n_on: int, freq_hz: float):
        n_on_arr, freq_arr = np.broadcast_arrays(
            np.asarray(n_on, dtype=float),
            np.asarray(freq_hz, dtype=float),
        )
        power = np.zeros_like(n_on_arr, dtype=float)
        remaining = n_on_arr.copy()
        for group in pumps:
            n = np.minimum(remaining, group.qty)
            n = np.where(n > 0, n, 0.0)
            if group.variable_freq:
                ratio = freq_arr / 50.0
            else:
                ratio = 1.0
            power += group.power_kw * n * ratio ** 3
            remaining -= n
        return self._maybe_scalar(power, n_on, freq_hz)

    def _calc_tower_power(self, towers: List[TowerGroup], n_on: int, freq_hz: float):
        n_on_arr, freq_arr = np.broadcast_arrays(
            np.asarray(n_on, dtype=float),
            np.asarray(freq_hz, dtype=float),
        )
        power = np.zeros_like(n_on_arr, dtype=float)
        remaining = n_on_arr.copy()
        for group in towers:
            n = np.minimum(remaining, group.qty)
            n = np.where(n > 0, n, 0.0)
            if group.variable_freq:
                ratio = freq_arr / 50.0
            else:
                ratio = 1.0
            power += group.fan_power_kw * group.fans_per_tower * n * ratio ** 3
            remaining -= n
        return self._maybe_scalar(power, n_on, freq_hz)

    def simulate_baseline(self) -> pd.DataFrame:
        hours, day_of_year, hour_of_day, months, ambient = self._generate_profile()
        month_idx = months - 1
        plr = self._calc_plr(hour_of_day)
        n_chiller = self._monthly_chiller_counts()[month_idx]
        total_cooling, chiller_power = self._calc_chiller_power_by_month(months, plr)
        chw_pump_power = self._calc_pump_power(
            self.config.chw_pumps,
            n_chiller,
            np.asarray(self.config.monthly_chw_pump_hz, dtype=float)[month_idx],
        )
        cw_pump_power = self._calc_pump_power(
            self.config.cw_pumps,
            n_chiller,
            np.asarray(self.config.monthly_cw_pump_hz, dtype=float)[month_idx],
        )
        tower_power = self._calc_tower_power(
            self.config.towers,
            n_chiller,
            np.asarray(self.config.monthly_tower_hz, dtype=float)[month_idx],
        )

        total_power = chiller_power + chw_pump_power + cw_pump_power + tower_power
        system_cop = np.divide(total_cooling, total_power, out=np.zeros_like(total_power), where=total_power > 0)

        return self._build_result_frame(
            hours=hours,
            day_of_year=day_of_year,
            hour_of_day=hour_of_day,
            months=months,
            ambient=ambient,
            n_chiller=n_chiller,
            plr=plr,
            total_cooling=total_cooling,
            chiller_power=chiller_power,
            chw_pump_power=chw_pump_power,
            cw_pump_power=cw_pump_power,
            tower_power=tower_power,
            total_power=total_power,
            system_cop=system_cop,
            chw_dt=np.asarray(self.config.monthly_chw_dt, dtype=float)[month_idx],
            cw_dt=np.asarray(self.config.monthly_cw_dt, dtype=float)[month_idx],
        )

    def simulate_optimized(self, chw_target_dt: float = 5.0) -> pd.DataFrame:
        hours, day_of_year, hour_of_day, months, ambient = self._generate_profile()
        month_idx = months - 1
        plr = self._calc_plr(hour_of_day)
        n_chiller = self._monthly_chiller_counts()[month_idx]
        total_cooling, chiller_power = self._calc_chiller_power_by_month(months, plr)
        chw_pump_power = self._calc_pump_power_optimized(
            self.config.chw_pumps, n_chiller, total_cooling, chw_target_dt)

        heat_rejection = total_cooling + chiller_power
        cw_has_vf = any(p.variable_freq for p in self.config.cw_pumps)
        if cw_has_vf:
            cw_pump_power = self._calc_pump_power_optimized(
                self.config.cw_pumps, n_chiller, heat_rejection, chw_target_dt)
        else:
            cw_pump_power = self._calc_pump_power(self.config.cw_pumps, n_chiller, 50.0)

        tower_freq = self._calc_tower_optimal_freq(ambient, months)
        tower_power = self._calc_tower_power(self.config.towers, n_chiller, tower_freq)
        total_power = chiller_power + chw_pump_power + cw_pump_power + tower_power
        system_cop = np.divide(total_cooling, total_power, out=np.zeros_like(total_power), where=total_power > 0)

        cw_dt = (
            np.full_like(plr, float(chw_target_dt), dtype=float)
            if cw_has_vf
            else np.asarray(self.config.monthly_cw_dt, dtype=float)[month_idx]
        )
        return self._build_result_frame(
            hours=hours,
            day_of_year=day_of_year,
            hour_of_day=hour_of_day,
            months=months,
            ambient=ambient,
            n_chiller=n_chiller,
            plr=plr,
            total_cooling=total_cooling,
            chiller_power=chiller_power,
            chw_pump_power=chw_pump_power,
            cw_pump_power=cw_pump_power,
            tower_power=tower_power,
            total_power=total_power,
            system_cop=system_cop,
            chw_dt=np.full_like(plr, float(chw_target_dt), dtype=float),
            cw_dt=cw_dt,
        )

    def _calc_pump_power_optimized(self, pumps, n_on, heat_kw, target_dt):
        cp = 4.186
        rho = 998.0
        n_on_arr, heat_arr, target_dt_arr = np.broadcast_arrays(
            np.asarray(n_on, dtype=float),
            np.asarray(heat_kw, dtype=float),
            np.asarray(target_dt, dtype=float),
        )
        power = np.zeros_like(n_on_arr, dtype=float)
        remaining = n_on_arr.copy()
        for group in pumps:
            n = np.minimum(remaining, group.qty)
            n = np.where(n > 0, n, 0.0)
            if group.variable_freq:
                rated_flow_kgs = group.flow_m3h * n / 3600.0 * rho
                required_flow = heat_arr / (cp * target_dt_arr)
                flow_ratio = np.divide(
                    required_flow,
                    rated_flow_kgs,
                    out=np.zeros_like(power),
                    where=rated_flow_kgs > 0,
                )
                freq_ratio = np.clip(flow_ratio, 0.55, 1.0)
                # Include practical VFD and pipe-network efficiency losses.
                actual_efficiency = 0.92
                power += group.power_kw * n * freq_ratio ** 3 / actual_efficiency
            else:
                power += group.power_kw * n * 1.0
            remaining -= n
        return self._maybe_scalar(power, n_on, heat_kw, target_dt)

    def _calc_tower_optimal_freq(self, ambient_c: float, month: int) -> float:
        ambient_arr, month_arr = np.broadcast_arrays(
            np.asarray(ambient_c, dtype=float),
            np.asarray(month, dtype=int),
        )
        wet_bulb = ambient_arr - 4.0
        tower_outlet = np.asarray(self.monthly_ambient, dtype=float)[month_arr - 1] + 4.5
        tower_outlet = np.maximum(21.0, tower_outlet)
        approach = tower_outlet - wet_bulb
        # Conservative tower strategy with a practical minimum frequency.
        freq = np.select(
            [approach >= 14, approach >= 10.5, approach >= 7],
            [20.0, 30.0, 40.0],
            default=50.0,
        )
        return self._maybe_scalar(freq, ambient_c, month)

    def _calc_plr(self, hour_of_day: int) -> float:
        hourly_factor = HOURLY_LOAD_FACTOR[np.asarray(hour_of_day, dtype=int)]
        plr = self.config.base_load_ratio * hourly_factor / HOURLY_LOAD_FACTOR.mean()
        plr = np.clip(plr, 0.20, 0.95)
        return self._maybe_scalar(plr, hour_of_day)

    def _generate_profile(self):
        hours = np.arange(8760)
        day_of_year = hours // 24
        hour_of_day = hours % 24
        months = pd.date_range("2024-01-01", periods=8760, freq="h").month.values
        monthly_ambient = np.asarray(self.monthly_ambient, dtype=float)
        daily_var = 3.0 * np.sin(2 * np.pi * (hour_of_day - 6) / 24)
        ambient = monthly_ambient[months - 1] + daily_var
        return hours, day_of_year, hour_of_day, months, ambient

    def _monthly_chiller_counts(self):
        return np.array([
            sum(n for _, n in self._get_dispatch(month))
            for month in range(1, 13)
        ], dtype=int)

    def _calc_chiller_power_by_month(self, months, plr):
        total_cooling = np.zeros_like(plr, dtype=float)
        chiller_power = np.zeros_like(plr, dtype=float)
        for month in range(1, 13):
            mask = months == month
            if not mask.any():
                continue
            dispatch = self._get_dispatch(month)
            cooling, power = self._calc_chiller_power(dispatch, plr[mask])
            total_cooling[mask] = cooling
            chiller_power[mask] = power
        return total_cooling, chiller_power

    def _build_result_frame(
        self,
        *,
        hours,
        day_of_year,
        hour_of_day,
        months,
        ambient,
        n_chiller,
        plr,
        total_cooling,
        chiller_power,
        chw_pump_power,
        cw_pump_power,
        tower_power,
        total_power,
        system_cop,
        chw_dt,
        cw_dt,
    ):
        return pd.DataFrame({
            "hour": hours.astype(int),
            "month": months.astype(int),
            "day_of_year": (day_of_year + 1).astype(int),
            "hour_of_day": hour_of_day.astype(int),
            "ambient_temp_c": np.round(ambient, 2),
            "total_chiller_count": n_chiller.astype(int),
            "load_ratio": np.round(plr, 4),
            "cooling_load_kw": np.round(total_cooling, 2),
            "chiller_power_kw": np.round(chiller_power, 2),
            "chw_pump_power_kw": np.round(chw_pump_power, 2),
            "cw_pump_power_kw": np.round(cw_pump_power, 2),
            "tower_fan_power_kw": np.round(tower_power, 2),
            "total_power_kw": np.round(total_power, 2),
            "system_cop": np.round(system_cop, 3),
            "chw_dt_c": chw_dt,
            "cw_dt_c": cw_dt,
        })

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
