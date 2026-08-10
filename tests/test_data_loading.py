from src.market_intel.config import get_settings
from src.market_intel.exposure import ExposureEngine


def test_config_accepts_multiple_exposure_files():
    paths = get_settings().paths("company_exposure_csv")
    assert len(paths) == 2
    assert all(path.suffix.lower() == ".xlsx" for path in paths)
    assert all(path.exists() for path in paths)


def test_multiple_excel_files_are_combined():
    engine = ExposureEngine()
    assert len(engine.source_file_names) == 2
    assert len(engine.df) == 20
    assert engine.df["_source_file"].nunique() == 2
    assert "Albemarle Corporation" in engine.companies
    assert "Delta Air Lines, Inc." in engine.companies
    assert "Ford Motor Company" in engine.companies
