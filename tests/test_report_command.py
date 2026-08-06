import json
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import Mock

import pytest

import aviation_weather_support
from aviation_weather_support.api import MetarApiError
from aviation_weather_support.models import MetarDataValidationError
from aviation_weather_support import reporting
from aviation_weather_support.reporting import (
    ReportWorkflowError,
    build_report_header,
    create_live_report,
    load_report_render_data,
    portable_source_path,
    replay_report,
    render_report_pdf,
)


FIXTURES = Path(__file__).parent / "fixtures"
RETRIEVED_AT = datetime(2026, 8, 5, 19, 41, 32, 891000, tzinfo=timezone.utc)


def load_fixture(name: str = "metar-katl-success.json") -> list[object]:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def successful_renderer(project_root, **kwargs):
    pdf_path = kwargs["pdf_path"]
    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    pdf_path.write_bytes(b"%PDF-1.4 mocked offline render")


def test_live_report_with_mocked_api_writes_all_artifacts(tmp_path):
    fetcher = Mock(return_value=load_fixture())

    generated = create_live_report(
        tmp_path,
        "katl",
        clock=lambda: RETRIEVED_AT,
        fetcher=fetcher,
        renderer=successful_renderer,
    )

    assert generated.raw_path.relative_to(tmp_path).as_posix() == (
        "data/reports/raw/KATL_20260805T194132891000Z_metar_raw.json"
    )
    assert generated.processed_path.relative_to(tmp_path).as_posix() == (
        "data/reports/processed/"
        "KATL_20260805T194132891000Z_metar_processed.json"
    )
    assert generated.pdf_path.relative_to(tmp_path).as_posix() == (
        "output/pdf/KATL_20260729T195200Z_metar_report.pdf"
    )
    evidence = json.loads(generated.raw_path.read_text(encoding="utf-8"))
    assert evidence["api_response"] == load_fixture()
    processed = json.loads(generated.processed_path.read_text(encoding="utf-8"))
    assert processed["report_metadata"] == {
        "schema_version": 1,
        "station": "KATL",
        "observation_time": "2026-07-29T19:52:00Z",
        "retrieved_at": "2026-08-05T19:41:32.891000Z",
        "evaluated_at": "2026-08-05T19:41:32.891000Z",
        "raw_source_path": (
            "data/reports/raw/KATL_20260805T194132891000Z_metar_raw.json"
        ),
        "processed_source_path": (
            "data/reports/processed/"
            "KATL_20260805T194132891000Z_metar_processed.json"
        ),
        "pdf_path": "output/pdf/KATL_20260729T195200Z_metar_report.pdf",
    }
    fetcher.assert_called_once_with("KATL")


def test_replay_uses_saved_time_and_never_calls_api(tmp_path, monkeypatch):
    live = create_live_report(
        tmp_path,
        "KATL",
        clock=lambda: RETRIEVED_AT,
        fetcher=Mock(return_value=load_fixture()),
        renderer=successful_renderer,
    )
    original_processed = json.loads(live.processed_path.read_text(encoding="utf-8"))
    blocked_api = Mock(side_effect=AssertionError("replay must not call the API"))
    monkeypatch.setattr(reporting, "fetch_metar", blocked_api)

    replayed = replay_report(
        tmp_path,
        live.raw_path,
        renderer=successful_renderer,
    )

    replayed_processed = json.loads(
        replayed.processed_path.read_text(encoding="utf-8")
    )
    assert replayed.result.operational_assessment.evaluated_at == RETRIEVED_AT
    assert replayed_processed == original_processed
    assert replayed.pdf_path == live.pdf_path
    blocked_api.assert_not_called()

    replay_data = load_report_render_data(
        tmp_path,
        station="KATL",
        evaluated_at="2026-08-05T19:41:32.891000Z",
        raw_input_path=replayed.raw_path,
        processed_input_path=replayed.processed_path,
    )
    replay_header = build_report_header(replay_data)
    assert replay_header.station == "KATL"
    assert replay_header.report_date == "August 5, 2026"
    assert replay_header.evaluated_at == "August 5, 2026 at 7:41 PM UTC"


def test_raw_evidence_exists_before_validation_and_failure_is_reported(tmp_path):
    def fail_after_raw_write(*args, **kwargs):
        expected = next((tmp_path / "data/reports/raw").glob("*.json"))
        assert expected.is_file()
        raise MetarDataValidationError("validation deliberately failed")

    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setattr(reporting, "process_metar_observations", fail_after_raw_write)
        with pytest.raises(ReportWorkflowError, match="validation deliberately failed") as caught:
            create_live_report(
                tmp_path,
                "KATL",
                clock=lambda: RETRIEVED_AT,
                fetcher=Mock(return_value=load_fixture()),
                renderer=successful_renderer,
            )

    assert caught.value.raw_path is not None
    assert caught.value.raw_path.is_file()
    assert caught.value.processed_path is None
    assert not list((tmp_path / "data/reports/processed").glob("*.json"))
    assert not list((tmp_path / "output/pdf").glob("*.pdf"))


def test_station_mismatch_preserves_raw_but_generates_no_report(tmp_path):
    with pytest.raises(ReportWorkflowError, match="station mismatch") as caught:
        create_live_report(
            tmp_path,
            "KAUO",
            clock=lambda: RETRIEVED_AT,
            fetcher=Mock(return_value=load_fixture()),
            renderer=successful_renderer,
        )

    assert caught.value.raw_path.is_file()
    assert caught.value.processed_path is None


@pytest.mark.parametrize("observation_time", [None, "not-a-time"])
def test_unusable_observation_time_preserves_raw_only(tmp_path, observation_time):
    response = load_fixture()
    response[0]["obsTime"] = observation_time

    with pytest.raises(
        ReportWorkflowError, match="observation time is unavailable or malformed"
    ) as caught:
        create_live_report(
            tmp_path,
            "KATL",
            clock=lambda: RETRIEVED_AT,
            fetcher=Mock(return_value=response),
            renderer=successful_renderer,
        )

    assert caught.value.raw_path.is_file()
    assert caught.value.processed_path is None


def test_render_failure_preserves_raw_and_processed_but_not_pdf(tmp_path):
    def failed_renderer(*args, **kwargs):
        raise ReportWorkflowError("Quarto deliberately failed")

    with pytest.raises(ReportWorkflowError, match="Quarto deliberately failed") as caught:
        create_live_report(
            tmp_path,
            "KATL",
            clock=lambda: RETRIEVED_AT,
            fetcher=Mock(return_value=load_fixture()),
            renderer=failed_renderer,
        )

    assert caught.value.raw_path.is_file()
    assert caught.value.processed_path.is_file()
    assert not list((tmp_path / "output/pdf").glob("*.pdf"))


def test_same_observation_intentionally_uses_one_pdf_path(tmp_path):
    first = create_live_report(
        tmp_path,
        "KATL",
        clock=lambda: RETRIEVED_AT,
        fetcher=Mock(return_value=load_fixture()),
        renderer=successful_renderer,
    )

    def replacement_renderer(project_root, **kwargs):
        kwargs["pdf_path"].write_bytes(b"replacement")

    second = create_live_report(
        tmp_path,
        "KATL",
        clock=lambda: RETRIEVED_AT.replace(microsecond=892000),
        fetcher=Mock(return_value=load_fixture()),
        renderer=replacement_renderer,
    )

    assert second.pdf_path == first.pdf_path
    assert second.pdf_path.read_bytes() == b"replacement"
    assert list((tmp_path / "output/pdf").glob("*.pdf")) == [second.pdf_path]


def test_renderer_atomically_replaces_same_observation_pdf(tmp_path, monkeypatch):
    raw_path = tmp_path / "data/reports/raw/raw.json"
    processed_path = tmp_path / "data/reports/processed/processed.json"
    pdf_path = tmp_path / "output/pdf/KATL_20260729T195200Z_metar_report.pdf"
    raw_path.parent.mkdir(parents=True)
    processed_path.parent.mkdir(parents=True)
    pdf_path.parent.mkdir(parents=True)
    raw_path.write_text("{}", encoding="utf-8")
    processed_path.write_text("{}", encoding="utf-8")
    pdf_path.write_bytes(b"old report")

    rendered_paths = []

    def mocked_quarto(command, **kwargs):
        assert "--output" not in command
        output_directory_value = command[command.index("--output-dir") + 1]
        assert "\\" not in output_directory_value
        output_directory = Path(output_directory_value)
        report_source = Path(command[command.index("render") + 1])
        output_name = report_source.with_suffix(".pdf").name
        assert not output_directory.is_absolute()
        rendered_path = (report_source.parent / output_directory / output_name).resolve()
        assert rendered_path.parent.parent == pdf_path.parent
        assert rendered_path.parent.name.startswith("quarto-report-")
        rendered_path.write_bytes(b"new report")
        assert rendered_path.is_file()
        rendered_paths.append(rendered_path)

    monkeypatch.setattr(reporting.subprocess, "run", mocked_quarto)

    render_report_pdf(
        tmp_path,
        station="KATL",
        evaluated_at=RETRIEVED_AT,
        raw_path=raw_path,
        processed_path=processed_path,
        pdf_path=pdf_path,
    )

    assert len(rendered_paths) == 1
    assert not rendered_paths[0].exists()
    assert pdf_path.read_bytes() == b"new report"
    assert list(pdf_path.parent.glob("*.pdf")) == [pdf_path]


def test_quarto_loader_validates_saved_pair_and_uses_processed_assessment(tmp_path):
    generated = create_live_report(
        tmp_path,
        "KATL",
        clock=lambda: RETRIEVED_AT,
        fetcher=Mock(return_value=load_fixture()),
        renderer=successful_renderer,
    )

    loaded = load_report_render_data(
        tmp_path,
        station="KATL",
        evaluated_at="2026-08-05T19:41:32.891000Z",
        raw_input_path=generated.raw_path,
        processed_input_path=generated.processed_path,
    )

    assert loaded.retrieved_at == RETRIEVED_AT
    assert loaded.assessment == generated.result.operational_assessment
    assert loaded.raw_source_path == generated.raw_path
    assert loaded.processed_source_path == generated.processed_path
    live_header = build_report_header(loaded)
    assert live_header.station == "KATL"
    assert live_header.report_date == "August 5, 2026"
    assert live_header.observation_time == "July 29, 2026 at 7:52 PM UTC"
    assert live_header.evaluated_at == "August 5, 2026 at 7:41 PM UTC"


def test_portable_source_path_is_relative_only_inside_project(tmp_path):
    internal = tmp_path / "data" / "reports" / "raw.json"
    external = tmp_path.parent / "external-raw.json"

    assert portable_source_path(tmp_path, internal) == "data/reports/raw.json"
    assert portable_source_path(tmp_path, external) == external.resolve().as_posix()


def test_live_cli_success_and_replay_are_offline(tmp_path, monkeypatch, capsys):
    api = Mock(return_value=load_fixture())
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(reporting, "fetch_metar", api)
    monkeypatch.setattr(reporting, "render_report_pdf", successful_renderer)

    aviation_weather_support.main(["report", "KATL"])
    live_output = capsys.readouterr()
    raw_path = next((tmp_path / "data/reports/raw").glob("*.json"))
    assert "Generated METAR report for KATL" in live_output.out
    assert "Raw evidence file: data/reports/raw/" in live_output.out
    assert "Processed file: data/reports/processed/" in live_output.out
    assert "PDF file: output/pdf/KATL_20260729T195200Z_metar_report.pdf" in live_output.out
    api.assert_called_once_with("KATL")

    api.reset_mock(side_effect=True)
    api.side_effect = AssertionError("replay must not call the API")
    aviation_weather_support.main(["report", "--input", str(raw_path)])
    replay_output = capsys.readouterr()
    assert "Generated METAR report for KATL" in replay_output.out
    api.assert_not_called()


def test_cli_validation_failure_explains_preserved_raw_only(
    tmp_path, monkeypatch, capsys
):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(reporting, "fetch_metar", Mock(return_value=load_fixture("metar-invalid.json")))

    with pytest.raises(SystemExit) as caught:
        aviation_weather_support.main(["report", "KATL"])

    output = capsys.readouterr().err
    assert caught.value.code == 1
    assert "Raw response preserved: data/reports/raw/" in output
    assert "Processed result was not generated." in output
    assert "PDF was not generated." in output


def test_cli_204_failure_explains_that_no_artifacts_were_generated(
    tmp_path, monkeypatch, capsys
):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        reporting,
        "fetch_metar",
        Mock(side_effect=MetarApiError("No current METAR observation was found for KAUO.")),
    )

    with pytest.raises(SystemExit) as caught:
        aviation_weather_support.main(["report", "KAUO"])

    output = capsys.readouterr().err
    assert caught.value.code == 1
    assert "No current METAR observation was found for KAUO." in output
    assert "No raw evidence, processed result, or PDF was generated." in output
    assert not (tmp_path / "data").exists()
    assert not (tmp_path / "output").exists()


def test_missing_report_extra_fails_before_api_or_files(tmp_path, monkeypatch):
    api = Mock(side_effect=AssertionError("missing extras must fail before API"))
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(aviation_weather_support, "find_spec", lambda name: None)
    monkeypatch.setattr(reporting, "fetch_metar", api)

    with pytest.raises(SystemExit, match=r"\[report\]"):
        aviation_weather_support.main(["report", "KATL"])

    api.assert_not_called()
    assert not (tmp_path / "data").exists()


def test_fixture_cli_never_calls_api(tmp_path, monkeypatch, capsys):
    api = Mock(side_effect=AssertionError("fixture mode must not call the API"))
    rendered = tmp_path / "output/pdf/practicum-6.pdf"
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(aviation_weather_support, "_require_report_support", lambda: None)
    monkeypatch.setattr(reporting, "fetch_metar", api)
    monkeypatch.setattr(
        aviation_weather_support,
        "render_fixture_report",
        Mock(return_value=rendered),
    )

    aviation_weather_support.main(["report", "--fixture", "KATL"])

    output = capsys.readouterr().out
    assert "Generated packaged fixture report for KATL" in output
    api.assert_not_called()
