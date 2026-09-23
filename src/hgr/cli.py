"""CLI `hgr` - mỗi bước pipeline là một lệnh (PLAN.md Mục 6)."""
import typer
from pydantic import BaseModel

app = typer.Typer(help="History GraphRAG - chatbot lịch sử Việt Nam", no_args_is_help=True)

PROFILE_HELP = "mini | core | full | era:<id> | period:<id>"


def _todo(step: str, milestone: str) -> None:
    typer.secho(f"[{step}] chưa triển khai ({milestone})", fg=typer.colors.YELLOW)
    raise typer.Exit(1)


def _ok(msg: str) -> None:
    typer.secho(f"[OK] {msg}", fg=typer.colors.GREEN)


def _fail(msg: str) -> None:
    typer.secho(f"[FAIL] {msg}", fg=typer.colors.RED)


def _model_pulled(name: str, available: list[str]) -> bool:
    base = name.split(":")[0]
    return any(m == name or m.split(":")[0] == base for m in available)


class _DoctorPing(BaseModel):
    ok: bool


@app.command()
def doctor():
    """Kiểm tra Neo4j, Ollama, model đã pull. (M1)"""
    from hgr.config import get_settings
    from hgr.graph.store import Neo4jStore
    from hgr.llm.ollama_client import OllamaClient

    settings = get_settings()
    healthy = True

    store = Neo4jStore(
        settings.neo4j.uri, settings.neo4j.user, settings.neo4j.password, settings.neo4j.database
    )
    if store.ping():
        _ok(f"Neo4j kết nối được ({settings.neo4j.uri})")
    else:
        _fail(f"Không kết nối được Neo4j ({settings.neo4j.uri}). Đã chạy 'docker compose up -d'?")
        healthy = False
    store.close()

    client = OllamaClient(
        settings.llm.host,
        settings.llm.chat_model,
        settings.llm.embed_model,
        settings.llm.num_ctx,
        max_retries=settings.llm.max_retries,
    )
    available: list[str] = []
    try:
        available = client.list_models()
        _ok(f"Ollama kết nối được ({settings.llm.host})")
    except Exception as e:
        _fail(f"Không kết nối được Ollama ({settings.llm.host}): {e}")
        healthy = False

    for name in (settings.llm.chat_model, settings.llm.embed_model):
        if _model_pulled(name, available):
            _ok(f"Model đã pull: {name}")
        else:
            _fail(f"Chưa pull model: {name} (chạy: ollama pull {name})")
            healthy = False

    if healthy:
        try:
            result = client.chat_json(
                [{"role": "user", "content": 'Trả lời đúng JSON schema, đặt trường "ok" = true.'}],
                _DoctorPing,
            )
            if result.ok:
                _ok("chat_json trả JSON hợp lệ")
            else:
                typer.secho('[WARN] chat_json trả JSON hợp lệ nhưng ok=false', fg=typer.colors.YELLOW)
        except Exception as e:
            _fail(f"chat_json lỗi: {e}")
            healthy = False

    if not healthy:
        raise typer.Exit(1)
    typer.secho("Tất cả kiểm tra đều OK.", fg=typer.colors.GREEN, bold=True)


@app.command()
def periods(check: bool = typer.Option(False, "--check", help="Kiểm tra khoảng năm hở/chồng")):
    """In cây era → period từ configs/periods.yaml. (M2)"""
    _todo("periods", "M2")


@app.command()
def ingest(profile: str = typer.Option("mini", help=PROFILE_HELP)):
    """Thu thập bài Wikipedia + Wikidata → data/raw/<period>/articles.jsonl. (M3)"""
    _todo("ingest", "M3")


@app.command()
def parse():
    """wikitext → sections, infobox, links. (M3)"""
    _todo("parse", "M3")


@app.command()
def chunk():
    """Chia chunk theo section/câu, gắn header, cutoff 1945. (M3)"""
    _todo("chunk", "M3")


@app.command()
def extract(
    structured: bool = typer.Option(False, "--structured", help="Chỉ backbone + Wikidata + infobox"),
    era: str = typer.Option(None, help="Giới hạn theo era id"),
    period: str = typer.Option(None, help="Giới hạn theo period id"),
    tier: str = typer.Option(None, help="A | B"),
):
    """Trích xuất thực thể + quan hệ bằng LLM local. (M4)"""
    _todo("extract", "M4")


@app.command()
def resolve():
    """Hợp nhất thực thể (QID → alias → fuzzy). (M5)"""
    _todo("resolve", "M5")


@app.command()
def load():
    """Nạp Era/Period/backbone/Article/Chunk/Entity/Relation vào Neo4j. (M5)"""
    _todo("load", "M5")


@app.command()
def embed():
    """Embed Chunk + Entity bằng bge-m3 → vector index. (M5)"""
    _todo("embed", "M5")


@app.command()
def build(profile: str = typer.Option("mini", help=PROFILE_HELP)):
    """Chạy ingest → parse → chunk → extract → resolve → load → embed → stats. (M9)"""
    _todo("build", "M9")


@app.command()
def stats(by_period: bool = typer.Option(False, "--by-period")):
    """Thống kê bài/chunk/entity/relation, cảnh báo giai đoạn thiếu dữ liệu. (M5)"""
    _todo("stats", "M5")


@app.command()
def ask(question: str, mode: str = typer.Option("graphrag", help="graphrag | vector")):
    """Hỏi một câu từ terminal. (M6)"""
    _todo("ask", "M6")


@app.command("eval")
def eval_cmd():
    """Chạy bộ eval GraphRAG vs baseline → eval/report.md. (M8)"""
    _todo("eval", "M8")


if __name__ == "__main__":
    app()
