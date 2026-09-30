"""Tests cho lệnh CLI `hgr build`, `hgr extract`, `hgr embed` (Giai đoạn M9).

Toàn bộ các bước pipeline và client Ollama/Neo4j được mock hoàn toàn trong test.
"""
from __future__ import annotations

from unittest.mock import MagicMock
import pytest
from typer.testing import CliRunner

from hgr.cli import app


@pytest.fixture
def mock_steps(monkeypatch):
    """Mock toàn bộ 7 bước pipeline và ghi nhận thứ tự gọi."""
    call_order: list[str] = []

    def make_mock(step_name: str):
        m = MagicMock(name=step_name)

        def side_effect(*args, **kwargs):
            call_order.append(step_name)
            return None

        m.side_effect = side_effect
        return m

    mocks = {
        "ingest": make_mock("ingest"),
        "parse": make_mock("parse"),
        "chunk": make_mock("chunk"),
        "extract": make_mock("extract"),
        "resolve": make_mock("resolve"),
        "load": make_mock("load"),
        "embed": make_mock("embed"),
    }

    for name, m in mocks.items():
        monkeypatch.setattr(f"hgr.cli.{name}", m)

    return mocks, call_order


def test_build_normal_order_and_calls(mock_steps):
    """Chạy build bình thường: xác nhận cả 7 bước được gọi đúng thứ tự, đúng 1 lần mỗi bước."""
    mocks, call_order = mock_steps
    runner = CliRunner()

    result = runner.invoke(app, ["build"])

    assert result.exit_code == 0
    assert call_order == ["ingest", "parse", "chunk", "extract", "resolve", "load", "embed"]

    for name, m in mocks.items():
        assert m.call_count == 1, f"Bước {name} phải được gọi đúng 1 lần"

    mocks["ingest"].assert_called_once_with(profile="mini", fresh=False)
    mocks["parse"].assert_called_once_with()
    mocks["chunk"].assert_called_once_with()
    mocks["extract"].assert_called_once_with(structured=False, era=None, period=None, tier=None)
    mocks["resolve"].assert_called_once_with()
    mocks["load"].assert_called_once_with()
    mocks["embed"].assert_called_once_with()

    assert "[1/7] Bắt đầu Ingest" in result.output
    assert "[7/7] Bắt đầu Embed" in result.output
    assert "TOÀN BỘ PIPELINE BUILD ĐÃ HOÀN TẤT" in result.output


def test_build_step_failure_stops_pipeline(mock_steps):
    """Một bước (extract) ném lỗi: xác nhận các bước SAU nó (resolve, load, embed) KHÔNG được gọi;
    các bước TRƯỚC nó đã gọi rồi thì không bị gọi lại; build thoát với lỗi rõ ràng.
    """
    mocks, call_order = mock_steps

    def fail(*args, **kwargs):
        call_order.append("extract")
        raise RuntimeError("Mô phỏng lỗi Ollama extraction failure")

    mocks["extract"].side_effect = fail

    runner = CliRunner()
    result = runner.invoke(app, ["build"])

    assert result.exit_code != 0

    # Các bước trước extract đã chạy
    assert call_order == ["ingest", "parse", "chunk", "extract"]
    mocks["ingest"].assert_called_once()
    mocks["parse"].assert_called_once()
    mocks["chunk"].assert_called_once()
    mocks["extract"].assert_called_once()

    # Các bước sau extract TUYỆT ĐỐI không được gọi
    mocks["resolve"].assert_not_called()
    mocks["load"].assert_not_called()
    mocks["embed"].assert_not_called()

    assert "Build thất bại tại bước [extract]" in result.output
    assert "Mô phỏng lỗi Ollama extraction failure" in result.output


def test_build_skip_to_step(mock_steps):
    """--skip-to load: xác nhận chỉ load và embed được gọi, các bước trước đó không được gọi."""
    mocks, call_order = mock_steps
    runner = CliRunner()

    result = runner.invoke(app, ["build", "--skip-to", "load"])

    assert result.exit_code == 0
    assert call_order == ["load", "embed"]

    mocks["ingest"].assert_not_called()
    mocks["parse"].assert_not_called()
    mocks["chunk"].assert_not_called()
    mocks["extract"].assert_not_called()
    mocks["resolve"].assert_not_called()

    mocks["load"].assert_called_once_with()
    mocks["embed"].assert_called_once_with()


def test_build_skip_to_invalid_step(mock_steps):
    """--skip-to <bước không hợp lệ>: báo lỗi rõ ràng, không chạy bước nào, exit != 0."""
    mocks, call_order = mock_steps
    runner = CliRunner()

    result = runner.invoke(app, ["build", "--skip-to", "khong_ton_tai"])

    assert result.exit_code != 0
    assert "Bước '--skip-to khong_ton_tai' không hợp lệ" in result.output
    assert len(call_order) == 0


def test_build_dry_run_calls_no_steps(mock_steps):
    """--dry-run: xác nhận KHÔNG có hàm bước nào được gọi, chỉ có output text mô tả kế hoạch."""
    mocks, call_order = mock_steps
    runner = CliRunner()

    result = runner.invoke(app, ["build", "--dry-run"])

    assert result.exit_code == 0
    assert len(call_order) == 0
    for name, m in mocks.items():
        m.assert_not_called()

    assert "[DRY-RUN] KẾ HOẠCH THỰC THI PIPELINE BUILD:" in result.output
    assert "[1/7] INGEST" in result.output
    assert "[7/7] EMBED" in result.output
    assert "Kết thúc kiểm tra cấu hình" in result.output


def test_build_flags_forwarding_mini_era_tier(mock_steps):
    """--profile mini kèm --era hoặc --tier: xác nhận cờ được truyền đúng xuống hàm bước tương ứng."""
    mocks, call_order = mock_steps
    runner = CliRunner()

    result = runner.invoke(app, ["build", "--profile", "mini", "--era", "le", "--tier", "A"])

    assert result.exit_code == 0
    mocks["ingest"].assert_called_once_with(profile="mini", fresh=False)
    mocks["extract"].assert_called_once_with(structured=False, era="le", period=None, tier="A")


def test_build_flags_forwarding_profile_era_prefix(mock_steps):
    """--profile era:<id> tự động suy ra era cho extract khi không truyền --era riêng."""
    mocks, call_order = mock_steps
    runner = CliRunner()

    result = runner.invoke(app, ["build", "--profile", "era:phongkien", "--tier", "B"])

    assert result.exit_code == 0
    mocks["ingest"].assert_called_once_with(profile="era:phongkien", fresh=False)
    mocks["extract"].assert_called_once_with(structured=False, era="phongkien", period=None, tier="B")


def test_build_flags_forwarding_fresh(mock_steps):
    """--fresh được truyền xuống ingest."""
    mocks, call_order = mock_steps
    runner = CliRunner()

    result = runner.invoke(app, ["build", "--fresh"])

    assert result.exit_code == 0
    mocks["ingest"].assert_called_once_with(profile="mini", fresh=True)


# ==============================================================================
# TESTS KIỂM TRA KHỞI TẠO OLLAMACLIENT
# ==============================================================================

def test_extract_standalone_structured_false_initializes_client(monkeypatch):
    """Lệnh extract độc lập với structured=False: khởi tạo OllamaClient và truyền client vào run()."""
    mock_run = MagicMock()
    mock_client_cls = MagicMock()
    mock_client_instance = MagicMock()
    mock_client_cls.return_value = mock_client_instance

    monkeypatch.setattr("hgr.extract.extractor.run", mock_run)
    monkeypatch.setattr("hgr.llm.ollama_client.OllamaClient", mock_client_cls)

    from hgr.config import get_settings
    settings = get_settings()

    runner = CliRunner()
    result = runner.invoke(app, ["extract"])

    assert result.exit_code == 0
    mock_client_cls.assert_called_once_with(
        settings.llm.host,
        settings.llm.chat_model,
        settings.llm.embed_model,
        settings.llm.num_ctx,
        max_retries=settings.llm.max_retries,
    )
    mock_run.assert_called_once_with(
        era=None,
        period=None,
        tier=None,
        structured=False,
        client=mock_client_instance,
    )
    assert mock_run.call_args.kwargs["client"] is not None


def test_extract_standalone_structured_true_does_not_initialize_client(monkeypatch):
    """Lệnh extract độc lập với structured=True: KHÔNG khởi tạo OllamaClient và run() nhận client=None."""
    mock_run = MagicMock()
    mock_client_cls = MagicMock()

    monkeypatch.setattr("hgr.extract.extractor.run", mock_run)
    monkeypatch.setattr("hgr.llm.ollama_client.OllamaClient", mock_client_cls)

    runner = CliRunner()
    result = runner.invoke(app, ["extract", "--structured"])

    assert result.exit_code == 0
    mock_client_cls.assert_not_called()
    mock_run.assert_called_once_with(
        era=None,
        period=None,
        tier=None,
        structured=True,
        client=None,
    )


def test_embed_standalone_initializes_client(monkeypatch):
    """Lệnh embed độc lập: khởi tạo OllamaClient và truyền vào embed_chunks, embed_entities."""
    mock_client_cls = MagicMock()
    mock_client_instance = MagicMock()
    mock_client_cls.return_value = mock_client_instance

    mock_store = MagicMock()
    mock_store.ping.return_value = True
    mock_store_cls = MagicMock(return_value=mock_store)

    mock_embed_chunks = MagicMock(return_value=10)
    mock_embed_entities = MagicMock(return_value=20)

    monkeypatch.setattr("hgr.llm.ollama_client.OllamaClient", mock_client_cls)
    monkeypatch.setattr("hgr.graph.store.Neo4jStore", mock_store_cls)
    monkeypatch.setattr("hgr.embed.embedder.embed_chunks", mock_embed_chunks)
    monkeypatch.setattr("hgr.embed.embedder.embed_entities", mock_embed_entities)

    from hgr.config import get_settings
    settings = get_settings()

    runner = CliRunner()
    result = runner.invoke(app, ["embed"])

    assert result.exit_code == 0
    mock_client_cls.assert_called_once_with(
        settings.llm.host,
        settings.llm.chat_model,
        settings.llm.embed_model,
        settings.llm.num_ctx,
        max_retries=settings.llm.max_retries,
    )
    mock_embed_chunks.assert_called_once_with(mock_store, mock_client_instance)
    mock_embed_entities.assert_called_once_with(mock_store, mock_client_instance)


def test_build_shares_single_client_between_extract_and_embed(monkeypatch):
    """Xác nhận build() chỉ khởi tạo đúng 1 instance OllamaClient dùng chung cho extract và embed."""
    mock_run = MagicMock()
    mock_client_cls = MagicMock()
    mock_client_instance = MagicMock()
    mock_client_cls.return_value = mock_client_instance

    mock_store = MagicMock()
    mock_store.ping.return_value = True
    mock_store_cls = MagicMock(return_value=mock_store)

    mock_embed_chunks = MagicMock(return_value=1)
    mock_embed_entities = MagicMock(return_value=1)

    monkeypatch.setattr("hgr.cli.ingest", MagicMock())
    monkeypatch.setattr("hgr.cli.parse", MagicMock())
    monkeypatch.setattr("hgr.cli.chunk", MagicMock())
    monkeypatch.setattr("hgr.cli.resolve", MagicMock())
    monkeypatch.setattr("hgr.cli.load", MagicMock())

    monkeypatch.setattr("hgr.extract.extractor.run", mock_run)
    monkeypatch.setattr("hgr.llm.ollama_client.OllamaClient", mock_client_cls)
    monkeypatch.setattr("hgr.graph.store.Neo4jStore", mock_store_cls)
    monkeypatch.setattr("hgr.embed.embedder.embed_chunks", mock_embed_chunks)
    monkeypatch.setattr("hgr.embed.embedder.embed_entities", mock_embed_entities)

    runner = CliRunner()
    result = runner.invoke(app, ["build"])

    assert result.exit_code == 0
    # OllamaClient chỉ được khởi tạo đúng 1 lần duy nhất trong toàn bộ lượt build
    assert mock_client_cls.call_count == 1
    # extract nhận đúng mock_client_instance
    assert mock_run.call_args.kwargs["client"] is mock_client_instance
    # embed nhận cùng đúng mock_client_instance đó
    assert mock_embed_chunks.call_args.args[1] is mock_client_instance
    assert mock_embed_entities.call_args.args[1] is mock_client_instance
