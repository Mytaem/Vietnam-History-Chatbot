"""CLI `hgr` - mỗi bước pipeline là một lệnh (PLAN.md Mục 6)."""
import json
from pathlib import Path

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


def _fmt_year(y: int) -> str:
    return f"{-y} TCN" if y < 0 else str(y)


@app.command()
def periods(check: bool = typer.Option(False, "--check", help="Kiểm tra khoảng năm hở/chồng")):
    """In cây era → period từ configs/periods.yaml. (M2)"""
    from hgr.periods import find_gaps, load_eras

    for era in load_eras():
        tag = " [song song]" if era.parallel else ""
        typer.echo(f"{era.id:<12} {era.name}{tag} ({_fmt_year(era.start)} – {_fmt_year(era.end)})")
        for period in era.periods:
            flags = []
            if period.legendary:
                flags.append("truyền thuyết")
            if period.disputed:
                flags.append("tranh luận")
            flag_str = f" [{', '.join(flags)}]" if flags else ""
            typer.echo(
                f"  {period.id:<14} {period.name}{flag_str} "
                f"({_fmt_year(period.start)} – {_fmt_year(period.end)}) A={period.tier_a_quota}"
            )

    if check:
        gaps = find_gaps()
        if gaps:
            typer.secho(f"\n[FAIL] Phát hiện {len(gaps)} khoảng năm bị hở trên trục chính:", fg=typer.colors.RED)
            for start, end in gaps:
                typer.secho(f"  {_fmt_year(start)} – {_fmt_year(end)} không thuộc period nào", fg=typer.colors.RED)
            raise typer.Exit(1)
        typer.secho("\n[OK] Không có khoảng năm nào bị hở trên trục chính.", fg=typer.colors.GREEN)


def _data_dir() -> Path:
    from hgr.config import get_settings

    settings = get_settings()
    return Path(settings.project_root) / settings.paths.data_dir


def _read_jsonl(path: Path):
    with open(path, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                yield json.loads(line)


@app.command()
def ingest(
    profile: str = typer.Option("mini", help=PROFILE_HELP),
    fresh: bool = typer.Option(False, "--fresh", help="Xóa data/raw trước (mặc định: gộp với dữ liệu đã có)"),
):
    """Thu thập bài Wikipedia + Wikidata → data/raw/<period>/articles.jsonl. (M3)"""
    from hgr.ingest.collector import collect

    summary = collect(profile, fresh=fresh)
    for period_id, count in summary["articles"].items():
        typer.echo(f"  {period_id:<14} {count} bài")
    total = sum(summary["articles"].values())
    on_disk = summary["total_on_disk"]
    _ok(f"Lần này: {total} bài ({summary['tier_a']} tier A). Trên đĩa: {sum(on_disk.values())} bài, "
        f"{len(on_disk)} giai đoạn → data/raw/<period>/articles.jsonl")
    if summary["missing_seeds"]:
        typer.secho(
            f"[WARN] {len(summary['missing_seeds'])} tiêu đề seed không tồn tại (xem data/reports/missing_seeds.txt):",
            fg=typer.colors.YELLOW,
        )
        for title, period_id in summary["missing_seeds"]:
            typer.echo(f"  {title}  ({period_id or '-'})")
    typer.echo(f"  Bỏ: {len(summary['off_topic'])} bài lạc đề (không link tới seed), "
               f"{len(summary['too_young'])} người sinh quá muộn, "
               f"{len(summary['dropped_out_of_scope'])} bài ngoài phạm vi profile")
    for title in summary["dropped_after_cutoff"]:
        typer.secho(f"[INFO] Bỏ bài bắt đầu sau mốc cắt: {title}", fg=typer.colors.CYAN)
    for title in summary["unassigned"]:
        typer.secho(f"[WARN] Không gán được giai đoạn: {title}", fg=typer.colors.YELLOW)


@app.command()
def parse():
    """wikitext → sections, infobox, links. (M3)"""
    from hgr.config import get_settings
    from hgr.process.parser import parse_article

    settings = get_settings()
    data = _data_dir()
    raw_files = sorted((data / "raw").glob("*/articles.jsonl"))
    if not raw_files:
        _fail("Chưa có data/raw/<period>/articles.jsonl, hãy chạy 'hgr ingest' trước.")
        raise typer.Exit(1)
    out = data / "processed" / "articles.jsonl"
    out.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with open(out, "w", encoding="utf-8") as f:
        for path in raw_files:
            for article in _read_jsonl(path):
                wikitext = article.pop("wikitext", None) or ""
                article.update(parse_article(wikitext, settings.chunk.drop_sections))
                f.write(json.dumps(article, ensure_ascii=False) + "\n")
                count += 1
    _ok(f"{count} bài → {out.relative_to(data.parent)}")


@app.command()
def chunk():
    """Chia chunk theo section/câu, gắn header, cutoff 1945. (M3)"""
    from hgr.config import get_settings
    from hgr.process.chunker import chunk_article

    settings = get_settings()
    data = _data_dir()
    source = data / "processed" / "articles.jsonl"
    if not source.exists():
        _fail("Chưa có data/processed/articles.jsonl, hãy chạy 'hgr parse' trước.")
        raise typer.Exit(1)
    out = data / "processed" / "chunks.jsonl"
    per_period: dict[str, int] = {}
    total_tokens = 0
    with open(out, "w", encoding="utf-8") as f:
        for article in _read_jsonl(source):
            chunks = chunk_article(
                article,
                target_tokens=settings.chunk.target_tokens,
                overlap_sentences=settings.chunk.overlap_sentences,
                min_tokens=settings.chunk.min_tokens,
                max_year=settings.scope.max_year,
                drop_post_cutoff=settings.chunk.drop_post_cutoff,
                max_chunks_b=settings.extract.max_chunks_b,
            )
            for c in chunks:
                f.write(json.dumps(c, ensure_ascii=False) + "\n")
                total_tokens += c["tokens"]
            per_period[article["period_id"]] = per_period.get(article["period_id"], 0) + len(chunks)
    total = sum(per_period.values())
    for period_id, count in sorted(per_period.items()):
        typer.echo(f"  {period_id:<14} {count} chunk")
    avg = total_tokens // total if total else 0
    _ok(f"{total} chunk (trung bình ~{avg} token) → {out.relative_to(data.parent)}")


@app.command()
def extract(
    structured: bool = typer.Option(False, "--structured", help="Chỉ backbone + Wikidata + infobox"),
    era: str = typer.Option(None, help="Giới hạn theo era id"),
    period: str = typer.Option(None, help="Giới hạn theo period id"),
    tier: str = typer.Option(None, help="A | B"),
):
    """Trích xuất thực thể + quan hệ bằng LLM local. (M4)"""
    from hgr.extract.extractor import run

    run(era=era, period=period, tier=tier, structured=structured)


@app.command()
def resolve():
    """Hợp nhất thực thể (QID → alias → fuzzy). (M5)"""
    from hgr.resolve.resolver import run

    run()


@app.command()
def load():
    """Nạp Era/Period/backbone/Article/Chunk/Entity/Relation vào Neo4j. (M5)"""
    from hgr.config import get_settings
    from hgr.graph.loader import (
        compute_degree_and_display_names,
        link_periods,
        load_articles_chunks,
        load_backbone,
        load_periods,
        load_resolved,
    )
    from hgr.graph.store import Neo4jStore
    from hgr.periods import load_eras

    settings = get_settings()
    store = Neo4jStore(
        settings.neo4j.uri, settings.neo4j.user, settings.neo4j.password, settings.neo4j.database
    )
    try:
        if not store.ping():
            _fail(f"Không kết nối được Neo4j ({settings.neo4j.uri}); hãy chạy 'docker compose up -d'.")
            raise typer.Exit(1)
        schema = Path(settings.project_root) / "src" / "hgr" / "graph" / "schema.cypher"
        store.apply_schema(str(schema))
        eras = load_eras()
        load_periods(store, eras)
        data_dir = Path(settings.project_root) / settings.paths.data_dir
        load_resolved(store, str(data_dir / "resolved"))
        load_backbone(store, str(Path(settings.project_root) / settings.scope.backbone_dir))
        load_articles_chunks(store, str(data_dir))
        link_periods(store)
        compute_degree_and_display_names(store)
        _ok("Neo4j schema, periods, articles, chunks, entities và relations đã được nạp")
    finally:
        store.close()


@app.command()
def embed():
    """Embed Chunk + Entity bằng bge-m3 → vector index. (M5)"""
    from hgr.config import get_settings
    from hgr.embed.embedder import embed_chunks, embed_entities
    from hgr.graph.store import Neo4jStore
    from hgr.llm.ollama_client import OllamaClient

    settings = get_settings()
    store = Neo4jStore(
        settings.neo4j.uri, settings.neo4j.user, settings.neo4j.password, settings.neo4j.database
    )
    client = OllamaClient(
        settings.llm.host,
        settings.llm.chat_model,
        settings.llm.embed_model,
        settings.llm.num_ctx,
        max_retries=settings.llm.max_retries,
    )
    try:
        if not store.ping():
            _fail(f"Không kết nối được Neo4j ({settings.neo4j.uri}); hãy chạy 'docker compose up -d'.")
            raise typer.Exit(1)
        count_chunks = embed_chunks(store, client)
        count_entities = embed_entities(store, client)
        _ok(f"Embedded {count_chunks} chunk và {count_entities} entity")
    finally:
        store.close()


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
