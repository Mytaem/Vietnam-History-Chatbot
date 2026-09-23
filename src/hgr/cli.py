"""CLI `hgr` - mỗi bước pipeline là một lệnh (PLAN.md Mục 6)."""
import typer

app = typer.Typer(help="History GraphRAG - chatbot lịch sử Việt Nam", no_args_is_help=True)

PROFILE_HELP = "mini | core | full | era:<id> | period:<id>"


def _todo(step: str, milestone: str) -> None:
    typer.secho(f"[{step}] chưa triển khai ({milestone})", fg=typer.colors.YELLOW)
    raise typer.Exit(1)


@app.command()
def doctor():
    """Kiểm tra Neo4j, Ollama, model đã pull. (M1)"""
    _todo("doctor", "M1")


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
