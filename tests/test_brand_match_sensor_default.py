"""Sensor freshness Brand Match harus aktif sejak instance Dagster baru (bukan hanya
karena state instance lokal). Sensor ingestion L0 sengaja tidak diubah."""

from dagster import DefaultSensorStatus

from kol_orchestration import brand_match, sensors


def test_sensor_brand_match_default_running():
    assert brand_match.brand_profile_changed_sensor.default_status == DefaultSensorStatus.RUNNING
    assert brand_match.brand_match_after_transform.default_status == DefaultSensorStatus.RUNNING


def test_sensor_ingestion_l0_tidak_diubah():
    assert sensors.l0_raw_new_data_sensor.default_status == DefaultSensorStatus.STOPPED
