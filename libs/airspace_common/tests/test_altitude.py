import pytest

from airspace_common.altitude import distance_km, height_above_airport_m


def test_qnh_corrects_pressure_altitude() -> None:
    # 8.3 m per hPa: QNH 1003.25 is 10 hPa below standard, so the aircraft is 83 m lower.
    result = height_above_airport_m(600.0, 650.0, 183.0, qnh_hpa=1003.25)
    assert result is not None
    assert result[0] == pytest.approx(600.0 - 83.0 - 183.0)
    assert result[1] == "qnh"


def test_without_metar_pressure_altitude_is_used_uncorrected() -> None:
    assert height_above_airport_m(600.0, 650.0, 183.0) == (417.0, "uncorrected")


def test_geometric_altitude_is_the_fallback() -> None:
    assert height_above_airport_m(None, 650.0, 183.0, qnh_hpa=1020.0) == (467.0, "geo")


def test_no_altitude_means_no_height() -> None:
    assert height_above_airport_m(None, None, 183.0) is None


def test_distance_between_vienna_and_bratislava_airports() -> None:
    # LOWW (48.1103, 16.5697) to LZIB (48.1702, 17.2127): about 48 km.
    assert distance_km(48.1103, 16.5697, 48.1702, 17.2127) == pytest.approx(48.2, abs=0.5)


def test_distance_to_itself_is_zero() -> None:
    assert distance_km(47.43, 19.26, 47.43, 19.26) == 0.0
