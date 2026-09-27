# Chatbot Lịch sử Việt Nam – GraphRAG, 100% Local LLM

Chatbot hỏi đáp lịch sử Việt Nam **từ tiền sử đến hết năm 1945**. Nguồn tri thức là Wikipedia tiếng Việt và Wikidata. Kiến trúc là GraphRAG, kết hợp Knowledge Graph trong Neo4j với Vector Search. Toàn bộ LLM chạy local qua Ollama.

Kế hoạch chi tiết (kiến trúc, phân kỳ, workflow, milestone) nằm trong [PLAN.md](PLAN.md).

> **Trạng thái:** xong M1 (hạ tầng, `hgr doctor`), M2 (phân kỳ) và M3 (thu thập + xử lý dữ liệu). Các module từ M4 (trích xuất) trở đi đang triển khai (xem PLAN.md Mục 8).

## Yêu cầu

- Windows 10/11, Python 3.11+, Docker Desktop, Ollama
- GPU ≥ 6 GB VRAM (khuyến nghị), RAM ≥ 16 GB

## Cài đặt và chạy

```powershell
powershell -ExecutionPolicy Bypass -File scripts\setup.ps1                  # venv, pip, model, Neo4j
powershell -ExecutionPolicy Bypass -File scripts\build_index.ps1 -Profile mini
powershell -ExecutionPolicy Bypass -File scripts\run_demo.ps1               # http://localhost:8501
```

## Profile build

| Profile | Nội dung | Thời gian ước tính |
|---|---|---|
| `mini` | 18 bài, rải đều 5 thời kỳ (~470 đoạn) | trích xuất ~1–1,5 giờ |
| `period:<id>` | Một giai đoạn (id lấy trong `configs/periods.yaml`) | 20 phút – 1,5 giờ |
| `era:<id>` | Một thời kỳ: `tiensu`, `dungnuoc`, `bacthuoc`, `songsong`, `phongkien`, `candai` | 1–6 giờ |
| `core` | ~256 bài Tier A | ~8–9 giờ |
| `full` | ~940 bài (~12.300 đoạn; ~4.350 đoạn tier A) | trích xuất tier A ~10–15 giờ, cả tier B ~14–21 giờ (chia nhiều đêm) |

## Chuẩn bị dữ liệu (M3)

```powershell
hgr periods --check                 # kiểm tra trục thời gian không bị hở
hgr ingest --profile full --fresh   # Wikipedia + Wikidata → data/raw/<giai đoạn>/articles.jsonl
hgr parse                           # → data/processed/articles.jsonl (mục, infobox, link, bảng, trích dẫn)
hgr chunk                           # → data/processed/chunks.jsonl (đầu vào cho bước trích xuất)
```

- `ingest` mặc định **gộp** với dữ liệu đã có; `--fresh` xóa dữ liệu các giai đoạn trước khi ghi.
- Phản hồi API được cache 7 ngày trong `data/cache/api/`: lần đầu `full` mất 15 phút đến vài giờ (tùy Wikidata có bận không, code tự chờ và thử lại), các lần sau chưa tới 1 phút.
- Báo cáo trong `data/reports/`: `missing_seeds.txt` (tiêu đề seed không tồn tại, phải rỗng), `rejected_p31.tsv` (bài bị bộ lọc loại, dùng để chỉnh `allowed_p31`).
- Seed, quota tier A, gợi ý prompt theo giai đoạn: `configs/periods.yaml`; bộ lọc bài mở rộng: `ingest` trong `configs/settings.yaml`.

## Cấu trúc thư mục

```
configs/    settings, ontology, periods (5 thời kỳ / 29 giai đoạn + 3 nhánh song song), seeds, backbone/
data/       đầu ra từng bước pipeline (JSONL, cache LLM) - không commit
src/hgr/    llm · ingest · process · extract · resolve · graph · embed · retrieve · generate · api · cli
ui/         Streamlit
eval/       bộ câu hỏi, baseline RAG, script eval
scripts/    setup / build_index / run_demo (PowerShell)
tests/      pytest (test đánh dấu `todo` được tự động skip)
```

## Lệnh CLI

```
hgr doctor | periods | ingest | parse | chunk | extract | resolve | load | embed | build | stats | ask | eval
```
