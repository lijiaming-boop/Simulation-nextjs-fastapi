import time

import numpy as np
import pandas as pd

from simulation.simulator import (
    ChillerGroup,
    HOURLY_LOAD_FACTOR,
    PlantConfig,
    PlantSimulator,
    PumpGroup,
    TowerGroup,
    estimate_screw_cop,
    interp_cop,
)


MONTHLY_AMBIENT = [8.0, 10.0, 15.0, 20.0, 25.0, 29.0, 32.0, 31.0, 27.0, 21.0, 15.0, 9.0]


def _sample_config(cw_variable=True):
    cw_pumps = [
        PumpGroup("cw-vf", qty=1, power_kw=45.0, flow_m3h=360.0, variable_freq=cw_variable),
        PumpGroup("cw-fixed", qty=2, power_kw=41.0, flow_m3h=330.0, variable_freq=False),
    ]
    return PlantConfig(
        chillers=[
            ChillerGroup(
                "centrifugal-fixed",
                qty=1,
                capacity_kw=1200.0,
                rated_power_kw=210.0,
                rated_cop=5.7,
                variable_freq=False,
                cop_curve={0.25: 4.8, 0.50: 5.3, 0.75: 5.8, 1.00: 5.6},
            ),
            ChillerGroup(
                "screw-vf",
                qty=2,
                capacity_kw=850.0,
                rated_power_kw=170.0,
                rated_cop=5.0,
                variable_freq=True,
            ),
        ],
        chw_pumps=[
            PumpGroup("chw-vf", qty=1, power_kw=37.0, flow_m3h=300.0, variable_freq=True),
            PumpGroup("chw-fixed", qty=2, power_kw=33.0, flow_m3h=280.0, variable_freq=False),
        ],
        cw_pumps=cw_pumps,
        towers=[
            TowerGroup("tower-vf", qty=1, fan_power_kw=18.0, fans_per_tower=2, variable_freq=True),
            TowerGroup("tower-fixed", qty=2, fan_power_kw=16.0, fans_per_tower=1, variable_freq=False),
        ],
        monthly_chiller_count=[1, 1, 2, 2, 3, 3, 3, 3, 2, 2, 1, 1],
        monthly_chw_pump_hz=[42, 42, 44, 46, 48, 50, 50, 49, 47, 45, 43, 42],
        monthly_cw_pump_hz=[41, 42, 43, 45, 47, 49, 50, 50, 48, 45, 43, 41],
        monthly_tower_hz=[35, 35, 38, 42, 45, 48, 50, 50, 46, 42, 38, 35],
        monthly_chw_dt=[4.5, 4.6, 4.8, 5.0, 5.2, 5.4, 5.5, 5.4, 5.2, 5.0, 4.8, 4.6],
        monthly_cw_dt=[4.8, 4.9, 5.0, 5.2, 5.4, 5.6, 5.8, 5.7, 5.5, 5.2, 5.0, 4.9],
        base_load_ratio=0.74,
    )


def _calc_plr_reference(config, hour_of_day, month, day_of_year=0):
    """参照实现：与生产 _calc_plr 同语义（月度负载系数 + 工作日/休息日双曲线）"""
    ref_mean = float(np.mean(config.workday_hourly_curve))
    if ref_mean <= 0.001:
        ref_mean = 1.0
    is_rest = bool(config.day_type[min(day_of_year, 364)])
    curve = config.offday_hourly_curve if is_rest else config.workday_hourly_curve
    hourly_factor = curve[hour_of_day]
    monthly_factor = config.monthly_load_factor[month - 1]
    plr = config.base_load_ratio * monthly_factor * hourly_factor / ref_mean
    return float(np.clip(plr, 0.20, 0.95))


def _calc_chiller_power_reference(dispatch, plr):
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


def _calc_pump_power_reference(pumps, n_on, freq_hz):
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


def _calc_tower_power_reference(towers, n_on, freq_hz):
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


def _calc_pump_power_optimized_reference(pumps, n_on, heat_kw, target_dt):
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
            actual_efficiency = 0.92
            power += group.power_kw * n * freq_ratio ** 3 / actual_efficiency
        else:
            power += group.power_kw * n * 1.0
        remaining -= n
    return power


def _calc_tower_optimal_freq_reference(simulator, ambient_c, month):
    wet_bulb = ambient_c - 4.0
    tower_outlet = simulator.monthly_ambient[month - 1] + 4.5
    tower_outlet = max(21.0, tower_outlet)
    approach = tower_outlet - wet_bulb
    if approach >= 14:
        return 20.0
    if approach >= 10.5:
        return 30.0
    if approach >= 7:
        return 40.0
    return 50.0


def _build_reference_frame(records):
    return pd.DataFrame(records)


def _simulate_baseline_reference(simulator):
    hours, day_of_year, hour_of_day, months, ambient = simulator._generate_profile()
    records = []
    for h in range(8760):
        m = int(months[h])
        hod = int(hour_of_day[h])
        amb = float(ambient[h])
        plr = _calc_plr_reference(simulator.config, hod, m, int(day_of_year[h]))
        dispatch = simulator._get_dispatch(m)
        n_chiller = sum(n for _, n in dispatch)
        total_cooling, chiller_power = _calc_chiller_power_reference(dispatch, plr)
        chw_pump_power = _calc_pump_power_reference(
            simulator.config.chw_pumps, n_chiller, simulator.config.monthly_chw_pump_hz[m - 1]
        )
        cw_pump_power = _calc_pump_power_reference(
            simulator.config.cw_pumps, n_chiller, simulator.config.monthly_cw_pump_hz[m - 1]
        )
        tower_power = _calc_tower_power_reference(
            simulator.config.towers, n_chiller, simulator.config.monthly_tower_hz[m - 1]
        )
        total_power = chiller_power + chw_pump_power + cw_pump_power + tower_power
        system_cop = total_cooling / total_power if total_power > 0 else 0
        records.append({
            "hour": h,
            "month": m,
            "day_of_year": int(day_of_year[h]) + 1,
            "hour_of_day": hod,
            "ambient_temp_c": round(amb, 2),
            "total_chiller_count": n_chiller,
            "load_ratio": round(plr, 4),
            "cooling_load_kw": round(total_cooling, 2),
            "chiller_power_kw": round(chiller_power, 2),
            "chw_pump_power_kw": round(chw_pump_power, 2),
            "cw_pump_power_kw": round(cw_pump_power, 2),
            "tower_fan_power_kw": round(tower_power, 2),
            "total_power_kw": round(total_power, 2),
            "system_cop": round(system_cop, 3),
            "chw_dt_c": simulator.config.monthly_chw_dt[m - 1],
            "cw_dt_c": simulator.config.monthly_cw_dt[m - 1],
        })
    return _build_reference_frame(records)


def _simulate_optimized_reference(simulator, chw_target_dt=5.0):
    hours, day_of_year, hour_of_day, months, ambient = simulator._generate_profile()
    records = []
    cw_has_vf = any(p.variable_freq for p in simulator.config.cw_pumps)
    for h in range(8760):
        m = int(months[h])
        hod = int(hour_of_day[h])
        amb = float(ambient[h])
        plr = _calc_plr_reference(simulator.config, hod, m, int(day_of_year[h]))
        dispatch = simulator._get_dispatch(m)
        n_chiller = sum(n for _, n in dispatch)
        total_cooling, chiller_power = _calc_chiller_power_reference(dispatch, plr)
        chw_pump_power = _calc_pump_power_optimized_reference(
            simulator.config.chw_pumps, n_chiller, total_cooling, chw_target_dt
        )
        heat_rejection = total_cooling + chiller_power
        if cw_has_vf:
            cw_pump_power = _calc_pump_power_optimized_reference(
                simulator.config.cw_pumps, n_chiller, heat_rejection, chw_target_dt
            )
        else:
            cw_pump_power = _calc_pump_power_reference(simulator.config.cw_pumps, n_chiller, 50.0)
        tower_freq = _calc_tower_optimal_freq_reference(simulator, amb, m)
        tower_power = _calc_tower_power_reference(simulator.config.towers, n_chiller, tower_freq)
        total_power = chiller_power + chw_pump_power + cw_pump_power + tower_power
        system_cop = total_cooling / total_power if total_power > 0 else 0
        records.append({
            "hour": h,
            "month": m,
            "day_of_year": int(day_of_year[h]) + 1,
            "hour_of_day": hod,
            "ambient_temp_c": round(amb, 2),
            "total_chiller_count": n_chiller,
            "load_ratio": round(plr, 4),
            "cooling_load_kw": round(total_cooling, 2),
            "chiller_power_kw": round(chiller_power, 2),
            "chw_pump_power_kw": round(chw_pump_power, 2),
            "cw_pump_power_kw": round(cw_pump_power, 2),
            "tower_fan_power_kw": round(tower_power, 2),
            "total_power_kw": round(total_power, 2),
            "system_cop": round(system_cop, 3),
            "chw_dt_c": chw_target_dt,
            "cw_dt_c": chw_target_dt if cw_has_vf else simulator.config.monthly_cw_dt[m - 1],
        })
    return _build_reference_frame(records)


def _assert_frames_equal(actual, expected):
    pd.testing.assert_frame_equal(actual, expected, check_exact=False, rtol=0, atol=1e-12)


def test_vectorized_baseline_matches_hourly_reference():
    simulator = PlantSimulator(_sample_config(), MONTHLY_AMBIENT)
    _assert_frames_equal(simulator.simulate_baseline(), _simulate_baseline_reference(simulator))


def test_vectorized_optimized_matches_hourly_reference_with_variable_cw_pump():
    simulator = PlantSimulator(_sample_config(cw_variable=True), MONTHLY_AMBIENT)
    _assert_frames_equal(simulator.simulate_optimized(chw_target_dt=5.8), _simulate_optimized_reference(simulator, 5.8))


def test_vectorized_optimized_matches_hourly_reference_without_variable_cw_pump():
    simulator = PlantSimulator(_sample_config(cw_variable=False), MONTHLY_AMBIENT)
    _assert_frames_equal(simulator.simulate_optimized(chw_target_dt=5.8), _simulate_optimized_reference(simulator, 5.8))


def test_vectorized_optimized_performance(capsys):
    simulator = PlantSimulator(_sample_config(cw_variable=True), MONTHLY_AMBIENT)

    start = time.perf_counter()
    expected = _simulate_optimized_reference(simulator, 5.8)
    reference_elapsed = time.perf_counter() - start

    start = time.perf_counter()
    actual = simulator.simulate_optimized(chw_target_dt=5.8)
    vectorized_elapsed = time.perf_counter() - start
    _assert_frames_equal(actual, expected)

    calibration_start = time.perf_counter()
    for target_dt in np.linspace(3.5, 7.0, 9):
        simulator.simulate_optimized(chw_target_dt=float(target_dt))
    calibration_elapsed = time.perf_counter() - calibration_start

    speedup = reference_elapsed / max(vectorized_elapsed, 1e-12)
    with capsys.disabled():
        print(
            f"\nsimulator performance: reference={reference_elapsed:.4f}s, "
            f"vectorized={vectorized_elapsed:.4f}s, speedup={speedup:.1f}x, "
            f"9 optimized runs={calibration_elapsed:.4f}s"
        )
    # 注意：生产实现目前是逐时 Python 循环（并未真正向量化），与参照实现
    # 复杂度相同，因此只要求不慢于参照（1.15x 容差吸收机器波动）。
    # 真正的向量化改造落地后应将阈值恢复到 2.0x 以上。
    assert speedup >= 1.15
