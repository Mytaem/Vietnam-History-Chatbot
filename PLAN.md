# Kế hoạch triển khai: Chatbot Lịch sử Việt Nam (GraphRAG, 100% Local LLM)

> Phạm vi: **toàn bộ lịch sử Việt Nam, từ thời tiền sử đến hết ngày 31/12/1945**. Nội dung được chia thành **5 thời kỳ, 29 giai đoạn và 3 nhánh song song** (Phù Nam, Chăm Pa, Chân Lạp – Nam Bộ).

## 0. Context

**Mục tiêu:** xây dựng một chatbot hỏi đáp lịch sử Việt Nam, **chạy được demo hoàn chỉnh trên máy hiện tại**.
- **Nguồn tri thức:** Wikipedia tiếng Việt và Wikidata.
- **Kiến trúc:** GraphRAG, tức Knowledge Graph trong Neo4j kết hợp với Vector Search.
- **Hạ tầng:** toàn bộ LLM và embedding chạy local qua Ollama.













**Quy mô dữ liệu:** khoảng 900–950 bài Wikipedia, tương đương khoảng 5.500–6.500 chunk.

**Profile build.** Có nhiều profile để lúc nào cũng có sẵn một bản chạy được demo:

| Profile | Nội dung | Số bài | Thời gian ước tính (RTX 4050) |
|---|---|---|---|
| `mini` | 18 bài trụ cột, rải đều cả 5 thời kỳ | 18 | ~1–1,5 giờ (469 chunk, đo thực tế) |
| `era:<id>` | Một thời kỳ lớn, ví dụ `era:phongkien` | 60–420 | 1–6 giờ |
| `period:<id>` | Một giai đoạn, ví dụ `period:tran` | 15–60 | 20 phút – 1,5 giờ |
| `core` | Các bài Tier A của cả 29+3 giai đoạn (~256 bài) | ~256 | ~8–9 giờ |
| `full` | `core` cộng các bài Tier B | ~930 | ~13–14 giờ, chạy trong 2–3 đêm, dừng giữa chừng rồi chạy tiếp được |

**Tiêu chí "chạy tốt":**
- Chạy `scripts/run_demo.ps1` là lên đủ DB, API và UI.
- Trả lời được 5 dạng câu hỏi, mỗi câu trả lời đều có trích dẫn: câu hỏi đơn (factoid), câu hỏi nhiều bước (multi-hop), câu hỏi theo thời gian, câu hỏi quan hệ A↔B, và câu hỏi tổng quan về một giai đoạn.
- Mọi giai đoạn đều có dữ liệu.
- Hiển thị được subgraph và timeline đã dùng để trả lời.
- Độ trễ mỗi câu trả lời dưới khoảng 10 giây.

---

## 1. Tech Stack

Nguyên tắc chung là tối giản: **chỉ dùng một database (Neo4j)** cho cả graph, vector và fulltext, và không phụ thuộc framework nặng.

| Tầng | Công nghệ | Ghi chú |
|---|---|---|
| LLM server | **Ollama** | `num_ctx=8192`, `OLLAMA_NUM_PARALLEL=2` |
| LLM trích xuất và trả lời | **`qwen3:4b-instruct-2507`** (Q4_K_M, ~2.6 GB) | Tiếng Việt tốt, không có chế độ thinking. Model dự phòng: `qwen2.5:3b-instruct`. Muốn chất lượng cao hơn thì dùng `qwen3:8b` (~5.2 GB), đổi lại chậm hơn |
| Embedding | **`bge-m3`** chạy qua Ollama (dim 1024) | Đa ngôn ngữ, ngữ cảnh 8K |
| Reranker (tùy chọn) | `BAAI/bge-reranker-v2-m3`, chạy CPU | Bật bằng `retrieval.rerank: true`. Mỗi câu hỏi tốn thêm khoảng 1–2 giây |
| Graph, Vector, Fulltext | **Neo4j 5.x Community** (Docker) + APOC | Vector index native và fulltext Lucene |
| Thuật toán đồ thị | **networkx** (Personalized PageRank) | Không cần plugin GDS |
| Nguồn dữ liệu | MediaWiki API (`vi.wikipedia.org`) + Wikidata `wbgetentities` | Gọi API, không cào HTML |
| Parse wikitext | `mwparserfromhell` | Tách infobox, wikilink, section |
| Xử lý tiếng Việt | `underthesea` (tách câu), `unicodedata` (chuẩn hóa NFC) | |
| Schema và JSON | `pydantic` v2 | Truyền JSON schema vào tham số `format=` của Ollama |
| Fuzzy match | `rapidfuzz` | Kiểm tra evidence, hợp nhất tên thực thể |
| Backend | **FastAPI** + `uvicorn` | Stream câu trả lời qua SSE |
| Frontend | **Streamlit** + `streamlit-agraph` | Chat, đồ thị, timeline, nguồn, khám phá giai đoạn |
| CLI | `typer` | Mỗi bước pipeline là một lệnh riêng |
| Test và Eval | `pytest`, script eval tự viết (LLM-judge chạy local) | |

---

## 2. Phân kỳ lịch sử Việt Nam (tiền sử → 1945)

`configs/periods.yaml` là **nguồn sự thật duy nhất** về phân kỳ. Các phần sau đều đọc từ file này:
- chọn bài để thu thập;
- tính quota Tier A;
- tạo node `:Period`;
- lọc dữ liệu theo thời gian khi truy hồi;
- map tên gọi giai đoạn trong câu hỏi sang khoảng năm;
- bộ lọc và timeline trên UI.

**Quy ước:**
- Năm TCN ghi bằng số âm.
- `~` là năm xấp xỉ.
- `*` là mốc truyền thuyết hoặc còn tranh luận. Các giai đoạn này có `disputed: true` và thêm trường năm thay thế `alt_start`/`alt_end`.
- Cột **A** là quota số bài Tier A (trích xuất đầy đủ) của giai đoạn đó.

### Thời kỳ I: Tiền sử và sơ sử (`era: tiensu`)

| # | id | Giai đoạn | Năm | Trọng tâm: văn hóa, di chỉ, sự kiện | A |
|---|---|---|---|---|---|
| 1 | `paleolithic` | Thời đồ đá cũ | … → ~−10000 | Núi Đọ, văn hóa Sơn Vi, Ngườm | 3 |
| 2 | `neolithic` | Thời đồ đá giữa và đồ đá mới | ~−18000 → ~−2000 | Văn hóa Hòa Bình, Bắc Sơn, Quỳnh Văn, Đa Bút, Bàu Tró | 4 |
| 3 | `bronze_early` | Thời kim khí sớm (tiền Đông Sơn) | ~−2000 → ~−700 | Phùng Nguyên, Đồng Đậu, Gò Mun; Sa Huỳnh (miền Trung); Đồng Nai (miền Nam) | 4 |

### Thời kỳ II: Dựng nước buổi đầu (`era: dungnuoc`)

| # | id | Giai đoạn | Năm | Trọng tâm | A |
|---|---|---|---|---|---|
| 4 | `vanlang` | Hồng Bàng – Văn Lang, văn hóa Đông Sơn | −2879* → −258 | Kinh Dương Vương, Lạc Long Quân – Âu Cơ, 18 đời Hùng Vương, Phong Châu, trống đồng Đông Sơn, Thánh Gióng, Sơn Tinh – Thủy Tinh | 8 |
| 5 | `aulac` | Âu Lạc – An Dương Vương | −257 → −179* (alt −208) | Thục Phán, thành Cổ Loa, nỏ thần, Mỵ Châu – Trọng Thủy, Cao Lỗ, Triệu Đà thôn tính Âu Lạc | 6 |

### Thời kỳ III: Bắc thuộc và đấu tranh giành độc lập (`era: bacthuoc`)

| # | id | Giai đoạn | Năm | Trọng tâm | A |
|---|---|---|---|---|---|
| 6 | `bacthuoc_1` | Bắc thuộc lần 1 | −179* (alt −111) → 40 | Nam Việt nhà Triệu, Tây Hán, quận Giao Chỉ, Cửu Chân, Nhật Nam, Tích Quang, Nhâm Diên | 6 |
| 7 | `haibatrung` | Khởi nghĩa Hai Bà Trưng | 40 → 43 | Trưng Trắc, Trưng Nhị, Mê Linh, Tô Định, Mã Viện, Lãng Bạc | 5 |
| 8 | `bacthuoc_2` | Bắc thuộc lần 2 | 43 → 544 | Đông Hán, Đông Ngô, Tấn, Nam triều; Sĩ Nhiếp; khởi nghĩa Bà Triệu (248); Lý Trường Nhân | 8 |
| 9 | `vanxuan` | Nhà Tiền Lý – nước Vạn Xuân | 544 → 602 | Lý Nam Đế, Triệu Quang Phục (Triệu Việt Vương), đầm Dạ Trạch, Hậu Lý Nam Đế (Lý Phật Tử) | 6 |
| 10 | `bacthuoc_3` | Bắc thuộc lần 3 | 602 → 905 | Tùy, Đường, An Nam đô hộ phủ; Lý Tự Tiên, Mai Thúc Loan (713/722), Phùng Hưng (766–791), Dương Thanh, Nam Chiếu, Cao Biền | 8 |
| 11 | `tuchu` | Thời kỳ tự chủ | 905 → 938 | Khúc Thừa Dụ, Khúc Hạo (cải cách), Khúc Thừa Mỹ, Dương Đình Nghệ, Kiều Công Tiễn | 6 |

### Nhánh song song: các quốc gia cổ miền Trung và miền Nam (`era: songsong`)

Các giai đoạn này **không nằm trên trục thời gian chính**. Chúng được nối với trục chính qua các quan hệ `OPPOSED`, `RULED_OVER` và `SUCCEEDED`.

| # | id | Giai đoạn | Năm | Trọng tâm | A |
|---|---|---|---|---|---|
| P1 | `phunam` | Vương quốc Phù Nam, văn hóa Óc Eo | ~TK I → ~TK VII | Óc Eo, Nền Chùa, Hỗn Điền, Liễu Diệp, sau đó bị Chân Lạp thôn tính | 5 |
| P2 | `champa` | Lâm Ấp – Chăm Pa | 192 → 1832 | Khu Liên, Mỹ Sơn, Trà Kiệu, Indrapura, Vijaya (Đồ Bàn), Chế Bồng Nga, Chế Mân – Huyền Trân, sáp nhập dưới thời Minh Mạng | 10 |
| P3 | `chanlap_nambo` | Chân Lạp và công cuộc khai phá Nam Bộ | ~TK VII → 1757 | Thủy Chân Lạp, Mạc Cửu (Hà Tiên), Nguyễn Hữu Cảnh lập Gia Định (1698), các cuộc Nam tiến | 5 |

### Thời kỳ IV: Phong kiến độc lập (`era: phongkien`)

| # | id | Giai đoạn | Năm | Trọng tâm | A |
|---|---|---|---|---|---|
| 12 | `ngo` | Nhà Ngô và Loạn 12 sứ quân | 938 → 968 | Trận Bạch Đằng (938), Ngô Quyền, Dương Tam Kha, Ngô Xương Văn, 12 sứ quân | 7 |
| 13 | `dinh` | Nhà Đinh – Đại Cồ Việt | 968 → 980 | Đinh Bộ Lĩnh (Đinh Tiên Hoàng), Hoa Lư, Đinh Liễn, Nguyễn Bặc, Thái hậu Dương Vân Nga | 6 |
| 14 | `tienle` | Nhà Tiền Lê | 980 → 1009 | Lê Hoàn, kháng chiến chống Tống (981), Chi Lăng, Lê Long Đĩnh | 6 |
| 15 | `ly` | Nhà Lý | 1009 → 1225 | Lý Công Uẩn, Chiếu dời đô, Thăng Long, quốc hiệu Đại Việt (1054), Văn Miếu (1070), Lý Thường Kiệt, trận Như Nguyệt (1077), Nam quốc sơn hà, Ỷ Lan | 12 |
| 16 | `tran` | Nhà Trần | 1225 → 1400 | Trần Thủ Độ, Trần Thái Tông, ba lần kháng chiến chống Nguyên Mông (1258, 1285, 1287–1288), Trần Hưng Đạo, Hịch tướng sĩ, trận Bạch Đằng (1288), Trần Nhân Tông, Thiền phái Trúc Lâm | 14 |
| 17 | `ho` | Nhà Hồ – Đại Ngu | 1400 → 1407 | Hồ Quý Ly, cải cách (tiền giấy, hạn điền), Tây Đô, kháng chiến chống Minh | 5 |
| 18 | `thuocminh` | Thuộc Minh, nhà Hậu Trần, khởi nghĩa Lam Sơn | 1407 → 1427 | Giản Định Đế, Trùng Quang Đế, Đặng Dung; Lê Lợi, Nguyễn Trãi, Hội thề Lũng Nhai, trận Tốt Động – Chúc Động, Chi Lăng – Xương Giang, Hội thề Đông Quan | 10 |
| 19 | `leso` | Lê sơ | 1428 → 1527 | Lê Thái Tổ, Bình Ngô đại cáo, Lê Thánh Tông, Luật Hồng Đức, Hội Tao Đàn, Đại Việt sử ký toàn thư, chinh phạt Chăm Pa (1471) | 10 |
| 20 | `nambactrieu` | Nam – Bắc triều (Mạc và Lê trung hưng) | 1527 → 1592 | Mạc Đăng Dung, Nguyễn Kim, Trịnh Kiểm, chiến tranh Lê – Mạc; nhà Mạc giữ Cao Bằng đến 1677 | 8 |
| 21 | `trinhnguyen` | Trịnh – Nguyễn phân tranh (Đàng Ngoài – Đàng Trong) | 1593 → 1777 (tính cả giai đoạn Lê trung hưng 1593–1626 trước trận đầu năm 1627) | Chúa Trịnh, chúa Nguyễn, sông Gianh, 7 lần giao chiến (1627–1672), Đào Duy Từ, Hội An, Phố Hiến, chữ Quốc ngữ (Alexandre de Rhodes) | 10 |
| 22 | `tayson` | Tây Sơn | 1771 → 1802 | Nguyễn Nhạc, Nguyễn Huệ (Quang Trung), Nguyễn Lữ; trận Rạch Gầm – Xoài Mút (1785), Ngọc Hồi – Đống Đa (1789), Chiếu Cần học, Ngô Thì Nhậm | 10 |
| 23 | `nguyen_doclap` | Nhà Nguyễn thời độc lập | 1802 → 1858 | Nguyễn Phúc Ánh (Gia Long), Minh Mạng, Thiệu Trị, Tự Đức; kinh đô Huế; quốc hiệu Việt Nam (1804) và Đại Nam (1839); Hoàng Việt luật lệ, Lê Văn Duyệt | 12 |

### Thời kỳ V: Cận đại, Pháp thuộc và cách mạng (`era: candai`)

| # | id | Giai đoạn | Năm | Trọng tâm | A |
|---|---|---|---|---|---|
| 24 | `phap_xamluoc` | Pháp xâm lược | 1858 → 1884 | Liên quân Pháp – Tây Ban Nha tấn công Đà Nẵng (1858), Gia Định (1859); Hòa ước Nhâm Tuất (1862), Giáp Tuất (1874), Harmand (1883), Patenôtre (1884); Nguyễn Tri Phương, Trương Định, Nguyễn Trung Trực, Hoàng Diệu, Lưu Vĩnh Phúc | 10 |
| 25 | `canvuong` | Phong trào Cần Vương và kháng chiến vũ trang | 1885 → 1896 | Phản công ở kinh thành Huế (1885), Hàm Nghi, Tôn Thất Thuyết, Chiếu Cần Vương, Phan Đình Phùng, khởi nghĩa Hương Khê, Ba Đình, Bãi Sậy; khởi nghĩa Yên Thế – Hoàng Hoa Thám (1884–1913) | 10 |
| 26 | `dau_tk20` | Khai thác thuộc địa lần 1, phong trào yêu nước đầu TK XX | 1897 → 1918 | Paul Doumer, Phan Bội Châu, Duy Tân hội, phong trào Đông Du, Phan Châu Trinh, phong trào Duy Tân, Đông Kinh Nghĩa Thục (1907), chống thuế Trung Kỳ (1908), Việt Nam Quang phục hội (1912), vua Duy Tân (1916) | 10 |
| 27 | `1919_1930` | Khai thác thuộc địa lần 2, phong trào dân tộc | 1919 → 1930 | Nguyễn Ái Quốc (Bản yêu sách 1919), Hội Việt Nam Cách mạng Thanh niên (1925), Tân Việt, Việt Nam Quốc dân Đảng (1927), Nguyễn Thái Học, khởi nghĩa Yên Bái (1930), thành lập Đảng Cộng sản Việt Nam (3/2/1930) | 10 |
| 28 | `1930_1939` | Cao trào cách mạng 1930–1939 | 1930 → 1939 | Xô viết Nghệ – Tĩnh (1930–1931), Trần Phú, Luận cương chính trị, Mặt trận Dân chủ Đông Dương (1936–1939), Lê Hồng Phong, Hà Huy Tập | 8 |
| 29 | `1939_1945` | Chiến tranh thế giới II, Cách mạng Tháng Tám | 1939 → 31/12/1945 | Nhật vào Đông Dương (1940); khởi nghĩa Bắc Sơn, Nam Kỳ, binh biến Đô Lương (1940); Mặt trận Việt Minh (1941), Pác Bó; Nhật đảo chính Pháp (9/3/1945); Đế quốc Việt Nam – Trần Trọng Kim; nạn đói Ất Dậu; Cách mạng Tháng Tám; Bảo Đại thoái vị; Tuyên ngôn độc lập (2/9/1945); Nam Bộ kháng chiến (23/9/1945); quân Tưởng và quân Anh vào Đông Dương | 14 |

**Tổng quota Tier A là 256 bài.** Quota được chia theo độ quan trọng và mức độ phủ của Wikipedia, để đồ thị không lệch về thời cận đại vốn có nhiều bài hơn.

### Dữ liệu xương sống tuyển chọn thủ công (`configs/backbone/*.yaml`)

Đây là các dữ kiện "trục" được nhập tay và nạp thẳng vào đồ thị với `source=curated`, `confidence=1.0`. Chúng làm khung để mọi dữ liệu trích xuất khác bám vào, và dùng để kiểm tra chất lượng.

**`quoc_hieu.yaml`**

| Quốc hiệu | Năm |
|---|---|
| Văn Lang | −2879* → −258 |
| Âu Lạc | −257 → −179* |
| Vạn Xuân | 544 → 602 |
| Đại Cồ Việt | 968 → 1054 |
| Đại Việt | 1054 → 1400 |
| Đại Ngu | 1400 → 1407 |
| Đại Việt | 1428 → 1804 |
| Việt Nam | 1804 → 1839 |
| Đại Nam | 1839 → 1945 |
| Đế quốc Việt Nam | 4/1945 → 8/1945 |
| Việt Nam Dân chủ Cộng hòa | từ 2/9/1945 |

**`kinh_do.yaml`**

| Kinh đô | Triều đại / thời kỳ |
|---|---|
| Phong Châu | Văn Lang |
| Cổ Loa | Âu Lạc, nhà Ngô |
| Hoa Lư | Đinh, Tiền Lê |
| Thăng Long | Lý, Trần, Lê sơ, Mạc, Lê trung hưng |
| Tây Đô | Hồ |
| Phú Xuân / Huế | Tây Sơn thời Quang Trung, Nguyễn |
| Đông Kinh | tên gọi Thăng Long thời Lê sơ |

**`trieu_dai.yaml`**

| Triều đại | Năm |
|---|---|
| Ngô | 939–965 |
| Đinh | 968–980 |
| Tiền Lê | 980–1009 |
| Lý | 1009–1225 |
| Trần | 1225–1400 |
| Hồ | 1400–1407 |
| Hậu Trần | 1407–1414 |
| Lê sơ | 1428–1527 |
| Mạc | 1527–1677 |
| Lê trung hưng | 1533–1789 |
| Tây Sơn | 1778–1802 |
| Nguyễn | 1802–1945 |

Mỗi triều đại được nối với kinh đô qua `CAPITAL_OF` và với giai đoạn qua `IN_PERIOD`. Danh sách vua của từng triều đại lấy từ Wikidata (P1365/P1366 tiền nhiệm/kế nhiệm, P39 chức vụ), sau đó đối chiếu với file này.

### Định dạng `configs/periods.yaml`

```yaml
eras:
  - id: bacthuoc
    name: Bắc thuộc và đấu tranh giành độc lập
    aliases: [thời Bắc thuộc, nghìn năm Bắc thuộc, thời kỳ Bắc thuộc, thời kỳ đô hộ phương Bắc]
    start: -179
    end: 938
    color: "#8c6d46"
    periods:
      - id: bacthuoc_2
        name: Bắc thuộc lần 2
        aliases: [Bắc thuộc lần thứ hai, thời thuộc Đông Hán, thời thuộc Ngô – Tấn – Nam triều]
        start: 43
        end: 544
        disputed: false
        tier_a_quota: 8
        seed_titles: [Bắc thuộc lần thứ hai, Sĩ Nhiếp, Khởi nghĩa Bà Triệu, Lý Trường Nhân]
        seed_categories: [Thể loại:Bắc thuộc lần 2]
        role_vocab: [thái thú, thứ sử, đô hộ, thủ lĩnh khởi nghĩa]   # gợi ý cho prompt trích xuất
        polities: [Đông Hán, Đông Ngô, Nhà Tấn, Lưu Tống, Nam Tề, Nhà Lương]
  # ... 5 era, 29 period + 3 parallel (era: songsong, parallel: true)
```

Tiêu đề bài trong `seed_titles` được `collector` resolve qua API ở bước M2, gồm cả việc đi theo redirect. Tiêu đề nào không tồn tại sẽ được ghi vào `data/reports/missing_seeds.txt` để sửa tay.

### Đặc thù trích xuất theo thời kỳ

Nội dung của từng giai đoạn (`role_vocab`, `polities`, ghi chú) được chèn vào prompt trích xuất dưới dạng **gợi ý ngữ cảnh**.

| Thời kỳ | Loại thực thể chủ đạo | Quan hệ chủ đạo | Lưu ý |
|---|---|---|---|
| I. Tiền sử | `Culture` (văn hóa khảo cổ), `Place` (di chỉ) | `FOUND_AT`, `SUCCEEDED`, `PART_OF` | Năm chỉ là xấp xỉ (`precision: millennium`). Rất ít thực thể là người |
| II. Dựng nước | `Person` (truyền thuyết), `Polity`, `Work` (truyền thuyết) | `RULED`, `CHILD_OF`, `CAPITAL_OF`, `FOUNDED` | Gắn `legendary: true`. Câu trả lời phải ghi "theo truyền thuyết" |
| III. Bắc thuộc | `Person` (quan cai trị, thủ lĩnh), `Event:Uprising`, `Polity` phương Bắc | `RULED_OVER` (role: thái thú...), `COMMANDED`, `OPPOSED` | Nhiều triều đại Trung Hoa. Cần phân biệt thủ lĩnh khởi nghĩa với quan đô hộ |
| Song song | `Polity`, `Person` (vua Chăm), `Place` (tháp, thành) | `OPPOSED`, `RULED`, `SPOUSE_OF`, `RULED_OVER` | Tên Chăm và Khmer có nhiều cách phiên âm, phải lấy alias từ Wikidata |
| IV. Phong kiến | `Person` (vua, tướng), `Event:Battle/War/Reform`, `Work` | `RULED`, `SUCCEEDED`, `COMMANDED`, `AUTHORED`, `CAPITAL_OF` | Một người có nhiều tên (húy, miếu hiệu, niên hiệu). Trận trùng tên (Bạch Đằng 938/981/1288) |
| V. Cận đại | `Organization` (đảng, hội), `Event:Movement/Treaty/Uprising`, `Person` | `FOUNDED`, `MEMBER_OF`, `SIGNED`, `OPPOSED`, `LED_TO` | Mốc cắt 1945. Người có nhiều bí danh (Nguyễn Ái Quốc…). Ngày tháng chính xác đến từng ngày |

### Lịch build đề xuất (`full`, chạy qua đêm)

| Đêm | Nội dung | Số bài | Ước tính |
|---|---|---|---|
| 0 (chiều) | `mini`, kiểm tra end-to-end | 18 | 25 phút |
| 1 | `era:phongkien` Tier A (giai đoạn 12–23) | ~110 A | ~4 giờ |
| 2 | `era:candai` Tier A + `era:tiensu`, `era:dungnuoc`, `era:bacthuoc`, `era:songsong` Tier A | ~146 A | ~4,5 giờ |
| 3 | Tier B của toàn bộ | ~680 B | ~4,5 giờ |

Sau mỗi đêm chạy `hgr load && hgr embed` là có ngay bản demo lớn hơn.

---

## 3. Chiến lược mở rộng và xử lý thời gian

### 3.1 Trích xuất theo tầng (Tiered Extraction)

| Tầng | Bài nào | Xử lý | Chi phí LLM |
|---|---|---|---|
| **Tier S (structured)** | Tất cả ~930 bài | Dùng Wikidata, infobox và backbone, **không gọi LLM**. Tạo node, alias, năm, quan hệ cha/con, kế vị, địa điểm, bên tham chiến | 0 |
| **Tier A (full)** | 256 bài chọn theo quota từng giai đoạn: lấy seed trước, còn thiếu thì lấy bài có nhiều in-link trong phạm vi | Trích xuất 2 pass trên **mọi chunk** | ~65% thời gian |
| **Tier B (lead)** | ~680 bài còn lại | Chỉ trích xuất phần mở đầu (lead) và 1–2 section đầu, tối đa `max_chunks_b=3` | ~35% thời gian |

**Mọi chunk đều được embed** (khoảng 5–7 phút cho ~6.000 chunk). Vì vậy vector search vẫn phủ toàn bộ dữ liệu, kể cả phần đồ thị ở Tier B còn thưa.

### 3.2 Mốc cắt 1945

1. `chunker` ghi vào mỗi chunk `years[]`, `min_year`, `max_year`. Chunk mà **mọi năm đều > 1945** bị loại, trừ khi đó là phần mở đầu (lead) của một bài trong phạm vi.
2. `validator` loại những triplet sự kiện có `start_year > 1945`. **Thuộc tính** của thực thể vẫn giữ nguyên, ví dụ năm mất 1969 của Hồ Chí Minh.
3. `collector` bỏ các bài có năm bắt đầu > 1945, ví dụ Chiến dịch Điện Biên Phủ.
4. `answerer`: nếu `time_range` của câu hỏi nằm hoàn toàn sau 1945, trả lời "Nằm ngoài phạm vi dữ liệu (đến hết năm 1945)".

### 3.3 Chuẩn hóa thời gian (`process/normalize.py`)

| Dạng trong văn bản | Chuẩn hóa thành |
|---|---|
| "năm 938" | `{start: 938, end: 938, precision: year}` |
| "179 TCN", "năm 208 trước Công nguyên" | `{start: -179}` (không có năm 0: 1 TCN = −1) |
| "thế kỷ III TCN" | `{-300, -201, precision: century}` |
| "thế kỷ XIII", "cuối thế kỷ XVIII", "nửa đầu thế kỷ XV" | `{1201, 1300}`, `{1767, 1800}`, `{1401, 1450}` |
| "thiên niên kỷ I TCN", "cách đây 10.000 năm" | `{-1000, -1, millennium}`, `{~-8000, precision: approx}` |
| "khoảng 2879 TCN" | `{-2879, legendary: true}` |
| "năm Ất Dậu (1945)" | Lấy năm dương lịch nằm trong ngoặc |
| "tháng Chạp năm Mậu Thân" (không có năm dương lịch) | Map can chi theo khoảng năm của giai đoạn của bài (Mậu Thân + Tây Sơn → 1788) |
| "19 tháng 8 năm 1945", "ngày 2/9/1945" | `{1945-08-19, precision: day}` |
| "niên hiệu Hồng Đức thứ 14" | Tra `configs/backbone/nien_hieu.yaml` (niên hiệu → năm đầu), rồi cộng thêm số năm |

Mọi phép lọc thời gian đều dùng **giao nhau giữa hai khoảng** (overlap): `start ≤ y1 AND end ≥ y0`. Nhờ vậy các mốc chỉ chính xác đến thế kỷ hoặc thiên niên kỷ vẫn khớp đúng.

---

## 4. Kiến trúc hệ thống

```
┌──────────────────────────── OFFLINE: INDEXING PIPELINE (CLI) ────────────────────────────┐
│                                                                                          │
│ periods.yaml ┐                                                                           │
│ seeds.yaml   ├► [1 Ingest] ─► [2 Parse+Normalize] ─► [3 Chunk] ─► [4 Extract (LLM)]      │
│ backbone/    ┘   Wiki API       infobox, links,        section-      tier A/B,           │
│                  + Wikidata     NFC, năm/niên hiệu     aware, 1945   entity + relation   │
│                  period+tier    ▼                      cutoff        + role_vocab        │
│           raw/<period>/articles.jsonl   chunks.jsonl         extractions.jsonl           │
│                                                                        │                 │
│   [5 Validate] ─► [6 Resolve Entities] ─► [7 Load Neo4j] ─► [8 Embed] ─► [9 Stats/QA]    │
│   schema,          QID / alias / fuzzy     backbone + Period   vector      theo giai đoạn │
│   evidence,1945    + period-aware          + IN_PERIOD         index                     │
└──────────────────────────────────────────────────────────────────────────────────────────┘
                                             │
                                             ▼
                          ┌──────────────────────────────────────┐
                          │         Neo4j (Docker :7687)          │
                          │ (:Era)<-[:PART_OF]-(:Period)-[:NEXT]->│
                          │ (:Entity:Person|Event|Place|Polity|…) │
                          │ (:Chunk)-[:MENTIONS]->(:Entity)       │
                          │ vector idx + fulltext idx             │
                          └──────────────────┬───────────────────┘
                                             │
┌──────────────────────────── ONLINE: QUERY PIPELINE (FastAPI) ────────────────────────────┐
│                                                                                          │
│ Câu hỏi ─► [A0 Period rules] ─► [A Analyze LLM] ─► [B Link entities] ─┬► [C1 Vector+FT] ─┐│
│            alias giai đoạn,      intent, entities,  fulltext alias      ├► [C2 Graph+PPR] ─┤│
│            thế kỷ, 1945 check    rewrite            + vector            ├► [C3 Path A↔B]  ─┤│
│                                                                         └► [C4 Period seed]┘│
│      [D Fusion RRF + boost evidence (+ rerank)] ─► [E Context có cấu trúc] ─► [F LLM]    │
│                                        answer + citations + subgraph + timeline          │
└──────────────────────────────────────────────────────────────────────────────────────────┘
                                             │ HTTP/SSE (:8000)
                                             ▼
         Streamlit UI (:8501): Chat | Đồ thị | Timeline | Nguồn | Khám phá giai đoạn | Debug

         Ollama (:11434): qwen3:4b-instruct-2507 (chat/extract), bge-m3 (embed)
```

### Mô hình dữ liệu Neo4j

**Node `:Era`** (5 node)
- Thuộc tính: `id, name, aliases[], start_year, end_year, color`.

**Node `:Period`** (32 node: 29 giai đoạn chính + 3 nhánh song song)
- Thuộc tính: `id, name, aliases[], start_year, end_year, disputed, alt_start, alt_end, parallel`.
- Nối lên thời kỳ: `(:Period)-[:PART_OF]->(:Era)`.
- Nối các giai đoạn liên tiếp trên trục chính: `(:Period)-[:NEXT]->(:Period)`.

**Node `:Entity`** mang thêm một nhãn phụ để phân loại:

| Nhãn phụ | Phân loại con / ghi chú |
|---|---|
| `Person` | |
| `Event` | `subtype`: Battle, War, Uprising, Treaty, Reform, Movement, Coup, Founding |
| `Place` | |
| `Polity` | Triều đại, quốc gia |
| `Organization` | |
| `Work` | Văn bản, tác phẩm, truyền thuyết |
| `Culture` | Văn hóa khảo cổ |

- Thuộc tính: `id, qid, name, display_name` (kèm năm nếu tên trùng, ví dụ "Trận Bạch Đằng (1288)"), `aliases[], aliases_text, description, start_year, end_year, year_precision, legendary, period_ids[], degree, embedding[1024]`.
- Riêng `Place` có thêm `historical_names[{name, start, end}]`, ví dụ Đại La → Thăng Long → Đông Kinh → Hà Nội.

**Node `:Chunk`**
- Thuộc tính: `id, page_title, section_path, text, min_year, max_year, period_id, tier, embedding[1024]`.

**Node `:Article`**
- Thuộc tính: `page_id, title, qid, url, revision_id, period_id, tier`.

**Quan hệ nghiệp vụ** (định nghĩa domain → range trong `ontology.yaml`):

| Nhóm | Quan hệ |
|---|---|
| Con người | `CHILD_OF`, `SPOUSE_OF`, `MEMBER_OF`, `BORN_IN`, `DIED_IN` |
| Quyền lực | `RULED` (Person→Polity), `RULED_OVER` (Polity/Person→Place/Polity, role: thái thú, toàn quyền...), `SUCCEEDED`, `FOUNDED`, `CAPITAL_OF` |
| Xung đột | `COMMANDED`, `PARTICIPATED_IN` (role, side), `OPPOSED`, `OCCUPIED` |
| Sự kiện | `OCCURRED_AT`, `PART_OF`, `CAUSED`, `LED_TO`, `SIGNED` |
| Văn hóa | `AUTHORED`, `FOUND_AT` (Culture→Place) |
| Dự phòng | `RELATED_TO` (role = động từ gốc) |

- Mỗi cạnh đều có: `start_year, end_year, role, side, confidence, source (curated|wikidata|infobox|llm), evidence_chunk_ids[], evidence_quotes[]`.
- **Gắn giai đoạn:** cạnh `(:Entity)-[:IN_PERIOD]->(:Period)` được tính tự động từ việc khoảng năm của thực thể giao với khoảng năm của giai đoạn. Chỉ tính với thực thể có năm.
- **Quan hệ cấu trúc:** `(:Article)-[:HAS_CHUNK]->(:Chunk)-[:MENTIONS]->(:Entity)`, `(:Article)-[:ABOUT]->(:Entity)`.

**Index**
- Unique constraint: `Entity.id`, `Chunk.id`, `Period.id`, `Era.id`.
- Fulltext: `entity_names(name, aliases_text)`, `chunk_text(text)`, `period_names(name, aliases_text)`.
- Vector: `entity_vec`, `chunk_vec` (cosine, 1024).
- Range: `Entity.start_year`, `Chunk.min_year`, `Chunk.period_id`.

---

## 5. Cấu trúc thư mục

```
F:\search engines\
├── PLAN.md                       # tài liệu này
├── pyproject.toml                # package hgr + entry point CLI `hgr` + cấu hình pytest
├── README.md                     # cài đặt, chạy demo, ví dụ câu hỏi
├── requirements.txt
├── requirements-rerank.txt       # sentence-transformers (tùy chọn)
├── .env.example                  # NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD, OLLAMA_HOST
├── .gitignore                    # data/, .neo4j/, .venv/
├── docker-compose.yml            # neo4j:5-community + APOC, volume ./.neo4j
├── configs\
│   ├── settings.yaml             # model, chunk, top-k, trọng số fusion, profile
│   ├── ontology.yaml             # nhãn, quan hệ, domain→range, mô tả cho prompt
│   ├── periods.yaml              # 5 era, 29 period + 3 nhánh song song (Mục 2)
│   ├── seeds.yaml                # profile mini (18 bài) + bổ sung thủ công
│   ├── infobox_map.yaml          # trường infobox → quan hệ ("chỉ huy1" → COMMANDED)
│   └── backbone\
│       ├── quoc_hieu.yaml        # quốc hiệu theo thời gian
│       ├── kinh_do.yaml          # kinh đô theo triều đại
│       ├── trieu_dai.yaml        # triều đại, năm, kinh đô
│       ├── nien_hieu.yaml        # niên hiệu → năm bắt đầu (để quy đổi năm)
│       └── dia_danh.yaml         # tên cũ/mới của địa danh chính kèm khoảng năm
├── data\                         # (gitignore) đầu ra từng bước, JSONL
│   ├── raw\<period_id>\articles.jsonl
│   ├── processed\chunks.jsonl
│   ├── extracted\structured.jsonl, extractions.jsonl, rejects.jsonl
│   ├── resolved\entities.jsonl, relations.jsonl
│   ├── reports\missing_seeds.txt, build_report.md, period_stats.csv
│   └── cache\llm\<sha1>.json     # cache LLM theo hash(prompt_version+input)
├── src\hgr\                      # package "history graph rag"
│   ├── __init__.py
│   ├── config.py                 # settings.yaml + .env → Settings (pydantic-settings)
│   ├── periods.py                # load periods.yaml; find_by_alias(), periods_for_range()
│   ├── log.py                    # log có cấu trúc (rich); không đặt tên logging.py để tránh trùng thư viện chuẩn
│   ├── cli.py                    # typer: doctor|ingest|parse|chunk|extract|resolve|load|embed|build|stats|ask|eval
│   ├── llm\
│   │   ├── ollama_client.py      # chat(), chat_json(schema), embed(batch), retry, đếm token
│   │   └── cache.py              # cache đĩa theo sha1, resume
│   ├── ingest\
│   │   ├── wiki_client.py        # wikitext, revision, pageprops(QID), redirects, links, categories
│   │   ├── wikidata_client.py    # wbgetentities: label/alias vi+en, P31, P569/P570/P580/P582/P585...
│   │   └── collector.py          # seed/category/1-hop → lọc P31 + năm + 1945 → gán period, tier
│   ├── process\
│   │   ├── parser.py             # wikitext → sections[], infobox{}, links[] (surface→target)
│   │   ├── normalize.py          # NFC, dấu thanh, parse thời gian (Mục 3.3)
│   │   └── chunker.py            # section/câu-aware, ~500 token, header, years[], cutoff 1945
│   ├── extract\
│   │   ├── schemas.py            # Pydantic: Entity, Triplet, EntityOutput, RelationOutput
│   │   ├── prompts.py            # prompt entity/relation/gleaning + few-shot theo era, PROMPT_VERSION
│   │   ├── structured_seed.py    # triplet từ backbone + infobox + Wikidata (không LLM)
│   │   ├── extractor.py          # pass 1→2→(3), tier A/B, 2 worker, resume
│   │   └── validator.py          # domain/range, evidence ⊂ chunk, năm hợp lệ, cutoff, conf
│   ├── resolve\
│   │   └── resolver.py           # QID → alias → fuzzy (blocking theo type+period) → canonical
│   ├── graph\
│   │   ├── schema.cypher         # constraints + indexes
│   │   ├── store.py              # Neo4jStore: run(), batch upsert, get_subgraph()
│   │   └── loader.py             # Era/Period/backbone → Article/Chunk/Entity/Rel → IN_PERIOD, degree
│   ├── embed\
│   │   └── embedder.py           # embed Chunk và Entity → setNodeVectorProperty
│   ├── retrieve\
│   │   ├── period_rules.py       # alias giai đoạn, "thế kỷ X", "năm Y", kiểm tra > 1945
│   │   ├── analyzer.py           # LLM → QueryPlan(intent, entities, rel_hints, rewritten)
│   │   ├── linker.py             # mention → top-k entity (fulltext + vector, RRF, ưu tiên period)
│   │   ├── chunk_search.py       # vector + fulltext trên Chunk, lọc năm/period
│   │   ├── graph_search.py       # k-hop + PPR (networkx); path A↔B; period seed
│   │   ├── fusion.py             # RRF theo intent, boost evidence, rerank
│   │   └── pipeline.py           # retrieve(question, history, period_filter) → RetrievalResult
│   ├── generate\
│   │   ├── context_builder.py    # Entities | Relations | Paths | Timeline | Sources [n]
│   │   └── answerer.py           # prompt trả lời + trích dẫn + ghi chú truyền thuyết/tranh luận
│   └── api\
│       ├── main.py               # FastAPI
│       └── models.py             # request/response schemas
├── ui\
│   ├── app.py                    # Streamlit: Chat + tabs
│   └── components.py             # vẽ graph (agraph), timeline theo era color, source cards
├── eval\
│   ├── questions.jsonl           # ~120 câu (Mục 10)
│   ├── baseline_rag.py           # RAG thuần vector để so sánh
│   └── run_eval.py               # 2 hệ, LLM-judge, xuất eval/report.md theo intent & era
├── scripts\
│   ├── setup.ps1                 # venv, pip, ollama pull, docker compose up, hgr doctor
│   ├── build_index.ps1           # -Profile mini|core|full|era:<id>|period:<id>
│   └── run_demo.ps1              # uvicorn :8000 + streamlit :8501
└── tests\
    ├── test_normalize.py         # TCN, thế kỷ, can chi, niên hiệu, ngày
    ├── test_periods.py           # alias → range, overlap, parallel branch
    ├── test_parser.py
    ├── test_chunker.py           # không cắt giữa câu, header, cutoff 1945
    ├── test_validator.py
    ├── test_resolver.py          # alias gộp đúng, trùng tên không gộp
    └── test_e2e_smoke.py         # cần Neo4j + Ollama: build mini → hỏi 5 câu
```

---

## 6. Workflow chi tiết

### 6.1 Workflow tổng

```
setup.ps1 ─► build_index.ps1 -Profile mini ─► run_demo.ps1 ─► http://localhost:8501
   │                │                                 │
   │ venv, pip,     │ hgr build = ingest→parse→chunk→ │ uvicorn hgr.api.main:app :8000
   │ ollama pull,   │ extract→resolve→load→embed→stats│ streamlit run ui/app.py :8501
   │ docker up,     │ (idempotent, cache, resume)     │
   │ hgr doctor     │                                 │
   ▼                ▼
          build_index.ps1 -Profile era:phongkien / era:candai / ... / full  (chạy qua đêm)
```

Mỗi lệnh CLI đọc file JSONL của bước trước và ghi ra JSONL cho bước sau. Nhờ đó:
- chạy lại được **từng bước riêng lẻ**;
- mở file trung gian ra xem được bằng mắt;
- không phải gọi lại LLM, vì kết quả đã có trong cache.

Mọi lệnh đều nhận tham số `--era`/`--period` để chỉ xử lý một phần dữ liệu.

### 6.2 Indexing pipeline từng bước

| # | Lệnh | Input → Output | Logic chính |
|---|---|---|---|
| 1 | `hgr ingest --profile …` | `periods.yaml`, `seeds.yaml` → `raw/<period>/articles.jsonl` | Xem chi tiết bên dưới bảng |
| 2 | `hgr parse` | Bổ sung `sections[]`, `infobox{}`, `links[]` | `mwparserfromhell`: tách infobox trước, giữ wikilink dạng `(surface, target)`, bỏ `<ref>`, navbox và các mục Tham khảo/Xem thêm/Liên kết ngoài. Chuẩn hóa NFC |
| 3 | `hgr chunk` | → `processed/chunks.jsonl` | Cắt theo section rồi theo câu, ~500 token, chồng 1 câu. Thêm header `[Bài … \| Mục … \| Chủ thể … \| Giai đoạn …]`. Ghi `links[]`, `years[]`, `min/max_year`, `period_id`, `tier`. Áp mốc cắt 1945 và giới hạn Tier B tối đa `extract.max_chunks_b` chunk đầu |
| 4a | `hgr extract --structured` | → `extracted/structured.jsonl` | Sinh triplet từ backbone (`curated`, 1.0), Wikidata (P22/P25 cha mẹ, P26 vợ/chồng, P1365/P1366 tiền nhiệm/kế nhiệm, P276 địa điểm, P710 bên tham gia, P112 người sáng lập, P36 thủ đô) và infobox (0.95) |
| 4b | `hgr extract [--era] [--period] [--tier]` | → `extractions.jsonl` | Xem chi tiết bên dưới bảng |
| 5 | (trong extract) `validator` | Bản ghi sai → `rejects.jsonl` kèm lý do | Kiểm tra domain→range; `partial_ratio(evidence, chunk) ≥ 90`; năm trong [-40000, 1945] đối với sự kiện; `confidence ≥ 0.6` |
| 6 | `hgr resolve` | → `resolved/*.jsonl` | Xem chi tiết bên dưới bảng |
| 7 | `hgr load` | → Neo4j | Xem chi tiết bên dưới bảng |
| 8 | `hgr embed` | Neo4j → Neo4j | Embed `Chunk.text` và `display_name: description` của Entity bằng bge-m3, mỗi lô 32 |
| 9 | `hgr stats --by-period` | → `reports/period_stats.csv`, `build_report.md` | Thống kê số bài, chunk, entity, relation theo từng giai đoạn. Cảnh báo giai đoạn nào có dưới 3% tổng số entity |

**Bước 1: `hgr ingest`.** Có ba nguồn bài:
- `seed_titles` của từng giai đoạn;
- `seed_categories`, duyệt sâu tối đa 2 cấp;
- mở rộng thêm 1 bước theo link từ các bài trên.

Bài chỉ được **giữ lại** khi thỏa cả ba điều kiện:
- P31 thuộc tập được phép (xem `settings.yaml`);
- năm của bài (lấy từ Wikidata hoặc infobox) giao với khoảng năm của giai đoạn;
- năm bắt đầu ≤ 1945.

Mỗi bài được gán `period_id`. Nếu một bài giao với nhiều giai đoạn thì chọn giai đoạn có phần giao lớn nhất, còn các giai đoạn khác ghi vào `period_ids[]`. Bài cũng được gán `tier` theo quota. Thông tin Wikidata lấy qua `wbgetentities`, mỗi lô 50.

**Bước 4b: `hgr extract`.**
- Tier A xử lý mọi chunk; Tier B chỉ xử lý tối đa `max_chunks_b` chunk đầu (được giới hạn từ bước chunk).
- **Pass 1 (Entity):** đưa vào prompt các link có trong chunk và `role_vocab`/`polities` của giai đoạn làm gợi ý.
- **Pass 2 (Relation):** chỉ được dùng thực thể lấy ra từ Pass 1.
- Dùng few-shot riêng cho từng thời kỳ (5 bộ).
- `temperature=0`, `format=<json schema>`, 2 worker chạy song song.
- Cache theo `sha1(PROMPT_VERSION+chunk)`.

**Bước 6: `hgr resolve`.** Mỗi thực thể trích ra đi qua các bước sau, dừng ở bước đầu tiên khớp:
1. Nếu surface là một link, lấy target của link, rồi lấy QID.
2. Tra từ điển alias (Wikidata, redirect, backbone), đã chuẩn hóa NFC và chữ thường.
3. Fuzzy match với `token_set_ratio ≥ 92`, **chỉ so trong cùng type và cùng hoặc liền kề giai đoạn**. Với Event, năm phải khớp trong khoảng ±1.
4. Nếu vẫn không khớp, tạo thực thể mới với id `local:<slug>`.

Sau cùng, gộp các cạnh trùng.

**Bước 7: `hgr load`.**
1. Chạy `schema.cypher`.
2. Nạp `Era`/`Period` (`PART_OF`, `NEXT`), rồi đến backbone.
3. Upsert Article, Chunk, Entity, Relation, mỗi lô 500 (dùng `apoc.merge.relationship`).
4. Tạo `MENTIONS` và `IN_PERIOD` (theo overlap năm).
5. Tính `degree` và `display_name` (thêm năm vào tên nếu bị trùng).

**Ước lượng thời gian** với qwen3:4b trên RTX 4050 (~70 token/s): khoảng 8–12 giây mỗi chunk cho 2 pass.

| Profile | Khối lượng | Thời gian |
|---|---|---|
| `mini` | ~130 chunk | ~25 phút |
| `core` | ~3.000 chunk Tier A | ~8–9 giờ |
| `full` | thêm ~1.700 chunk Tier B | tổng ~13–14 giờ (Mục 2, lịch build) |

### 6.3 Query pipeline (online)

```python
# src/hgr/retrieve/pipeline.py (pseudocode)
def retrieve(question, history, period_filter=None) -> RetrievalResult:
    rules = period_rules.parse(question)          # alias giai đoạn, "thế kỷ", năm, > 1945?
    if rules.out_of_scope: return RetrievalResult.out_of_scope()

    plan = analyzer.analyze(question, history)    # LLM → QueryPlan
    plan.time_range = rules.time_range or period_filter or plan.time_range   # luật > UI > LLM
    plan.periods    = rules.periods or periods.periods_for_range(plan.time_range)

    seeds = linker.link_all(plan.entities, prefer_periods=plan.periods)
    if not seeds and plan.periods:                # câu hỏi tổng quan theo giai đoạn
        seeds = graph_search.period_seeds(plan.periods, top=10)   # entity degree cao IN_PERIOD

    chunks_v = chunk_search.search(plan.rewritten, k=20, years=plan.time_range)
    sub      = graph_search.local(seeds, hops=2, rel_types=plan.rel_hints,
                                  years=plan.time_range, max_degree=settings.max_degree)
    ranked   = graph_search.ppr(sub, seeds, top_n=25)
    paths    = graph_search.paths(seeds[0], seeds[1]) if plan.intent == "relational" else []

    fused = fusion.rrf([chunks_v, ranked.evidence_chunks, paths.evidence_chunks],
                       weights=settings.fusion[plan.intent], k=60)
    fused = fusion.boost_evidence(fused, ranked.evidence_ids, factor=1.3)
    if settings.retrieval.rerank: fused = fusion.rerank(question, fused[:30])
    return RetrievalResult(plan, fused[:8], ranked.triplets, paths, sub.trim(ranked.node_ids))
```

**Bước A0: luật về giai đoạn (`period_rules.py`).** Bước này chạy trước LLM và **có độ ưu tiên cao hơn LLM**, vì model 4B hay đoán sai năm. Ví dụ:

| Trong câu hỏi | Kết quả |
|---|---|
| "thời Bắc thuộc" | era `bacthuoc` → [−179, 938] |
| "Bắc thuộc lần 2" | period → [43, 544] (khớp tên dài nhất) |
| "thời Pháp thuộc" | [1858, 1945] |
| "thế kỷ XV" | [1401, 1500] |
| "sau năm 1954" | `out_of_scope` |

**Bước A: phân tích bằng LLM.** Kết quả là `QueryPlan` gồm:
- `intent`: `factoid | multihop | temporal | relational | comparison | overview`;
- `entities[]`, `rel_hints[]`;
- `rewritten`: câu hỏi viết lại, đã giải đại từ theo lịch sử hội thoại.

**Trọng số fusion** theo thứ tự `[vector, graph, path]`:

| Intent | Trọng số | Ghi chú |
|---|---|---|
| factoid | 0.5 / 0.5 / 0 | |
| multihop | 0.3 / 0.7 / 0 | |
| temporal | 0.4 / 0.6 / 0 | Bắt buộc lọc theo năm |
| relational | 0.2 / 0.4 / 0.4 | |
| comparison | 0.4 / 0.6 / 0 | Tách thành 2 lượt truy hồi, mỗi thực thể một lượt, rồi ghép lại |
| overview | 0.6 / 0.4 / 0 | Seed từ `Period`, `top_chunks=12` |

**Cypher lấy subgraph** (lọc năm theo overlap):
```cypher
MATCH (s:Entity) WHERE s.id IN $seeds
CALL (s) {
  MATCH p=(s)-[r*1..2]-(n:Entity)
  WHERE all(x IN r WHERE (size($rels)=0 OR type(x) IN $rels)
        AND ($y0 IS NULL OR x.start_year IS NULL OR
             (x.start_year <= $y1 + 5 AND coalesce(x.end_year, x.start_year) >= $y0 - 5)))
    AND all(m IN nodes(p)[1..] WHERE m.degree <= $maxdeg)
  RETURN p LIMIT 400 }
RETURN p
```

**Seed theo giai đoạn** (dùng cho câu hỏi overview):
```cypher
MATCH (p:Period) WHERE p.id IN $periods
MATCH (e:Entity)-[:IN_PERIOD]->(p)
RETURN e.id ORDER BY e.degree DESC LIMIT $top
```

**Fallback:**
- Lọc theo `rel_hints` ra rỗng thì bỏ lọc.
- Không link được thực thể và cũng không có giai đoạn thì chỉ dùng vector search.
- Tìm đường A↔B dùng `allShortestPaths((a)-[*..4]-(b))`, loại các node hub, `LIMIT 5`.

**Context gửi cho LLM:**
```
### PHẠM VI        Giai đoạn: Nhà Trần (1225–1400) · Thời kỳ: Phong kiến độc lập
### THỰC THỂ       (≤12, theo PPR; tên hiển thị, loại, năm, [truyền thuyết]/[mốc tranh luận])
### QUAN HỆ        (≤25: A —REL(role, năm)→ B [n])
### ĐƯỜNG LIÊN KẾT (nếu relational)
### DÒNG THỜI GIAN (sắp tăng dần, TCN hiển thị "179 TCN")
### NGUỒN          [n] (Bài › Mục) "trích đoạn…"   (≤8 chunk, ≤1.200 token)
```

**Prompt trả lời** yêu cầu model:
- chỉ dùng thông tin trong context;
- mỗi ý đều kèm trích dẫn `[n]`;
- khi thiếu thông tin thì nói "Dữ liệu hiện có chưa đề cập…";
- với thực thể có nhãn `[truyền thuyết]`, mở đầu bằng "Theo truyền thuyết…";
- với mốc có nhãn `[mốc tranh luận]`, nêu cả hai năm;
- viết tiếng Việt, ngắn gọn, có cấu trúc.

### 6.4 API (FastAPI)

| Endpoint | Mô tả |
|---|---|
| `POST /chat` | body `{question, history[], period_filter?, mode: graphrag\|vector}` → SSE: `plan`, `token`…, `done{answer, citations[], subgraph, timeline[]}` |
| `POST /retrieve` | Chỉ chạy truy hồi, dùng cho debug và eval |
| `GET /periods` | Cây era → period, kèm số entity mỗi giai đoạn |
| `GET /periods/{id}` | Thực thể tiêu biểu (top degree), sự kiện theo năm, giai đoạn trước và sau |
| `GET /entity/{id}` | Chi tiết thực thể và các láng giềng 1-hop |
| `GET /health` | Tình trạng kết nối Neo4j, Ollama và các model |
| `GET /stats` | Số node và cạnh theo loại và theo giai đoạn |

### 6.5 UI (Streamlit)

- **Chat (cột trái):** hội thoại nhiều lượt, câu trả lời hiện dần theo luồng stream, trích dẫn `[n]` hiển thị thành chip. Có nhãn "Truyền thuyết"/"Mốc tranh luận" khi cần.
- **Các tab bên phải:**
  - **Đồ thị:** tô màu node theo loại, nhãn cạnh là tên quan hệ. Bấm vào một node thì câu hỏi "Kể về X" được điền sẵn.
  - **Timeline:** trục năm từ TCN đến 1945, dải nền tô màu theo 5 thời kỳ, sự kiện là các điểm.
  - **Nguồn:** trích đoạn kèm link về Wikipedia.
  - **Khám phá giai đoạn:** chọn thời kỳ, rồi chọn giai đoạn. Hiển thị mô tả, nhân vật và sự kiện tiêu biểu, và 3 câu hỏi gợi ý.
  - **Debug:** QueryPlan, kết quả luật giai đoạn, danh sách seed, điểm số fusion, thời gian từng bước.
- **Sidebar:**
  - `/health`;
  - bộ lọc "Giới hạn theo giai đoạn" (truyền `period_filter` vào API);
  - công tắc chuyển chế độ GraphRAG ↔ chỉ vector;
  - công tắc bật/tắt rerank;
  - danh sách câu hỏi mẫu cho từng thời kỳ.

---

## 7. Cấu hình chính (`configs/settings.yaml`)

```yaml
llm:      {host: http://localhost:11434, chat_model: qwen3:4b-instruct-2507,
           extract_model: qwen3:4b-instruct-2507, embed_model: bge-m3,
           num_ctx: 8192, temperature: 0.0, timeout_s: 120, workers: 2}
neo4j:    {uri: bolt://localhost:7687, user: neo4j, password: ${NEO4J_PASSWORD}}
scope:    {max_year: 1945, periods_file: configs/periods.yaml, backbone_dir: configs/backbone}
ingest:   {lang: vi, expand_hops: 1, category_depth: 2,
           max_articles: {mini: 18, core: 280, full: 1000, era: 450, period: 80},
           allowed_p31: [Q5, Q178561, Q198, Q164950, Q3024240, Q1190554, Q124734,
                         Q131569, Q7278, Q47461344, Q465299, Q839954, Q486972]}
           # người, trận, chiến tranh, triều đại, nhà nước cũ, sự kiện, khởi nghĩa,
           # hiệp ước, đảng phái, tác phẩm, văn hóa khảo cổ, di chỉ khảo cổ, khu dân cư
           # (danh sách QID được kiểm tra lại ở M2 bằng wbgetentities)
chunk:    {target_tokens: 500, overlap_sentences: 1, min_tokens: 80, drop_post_cutoff: true}
extract:  {prompt_version: v1, gleaning: false, min_confidence: 0.6, evidence_ratio: 90,
           max_chunks_b: 3, few_shot_by_era: true}
resolve:  {fuzzy_threshold: 92, event_year_tolerance: 1, period_blocking: adjacent}
retrieval:{chunk_k: 20, hops: 2, max_degree: p99, ppr_alpha: 0.85, top_chunks: 8,
           rerank: false,
           fusion: {factoid: [0.5,0.5,0], multihop: [0.3,0.7,0], temporal: [0.4,0.6,0],
                    relational: [0.2,0.4,0.4], comparison: [0.4,0.6,0], overview: [0.6,0.4,0]}}
```

**`docker-compose.yml`:**
- image `neo4j:5-community`;
- `NEO4J_AUTH`, `NEO4J_PLUGINS=["apoc"]`;
- `NEO4J_server_memory_heap_max__size=3G`, `NEO4J_server_memory_pagecache_size=1G`;
- mở cổng 7474 và 7687;
- volume `./.neo4j/data`.

**Profile `mini` trong `seeds.yaml`** (18 bài rải đều 5 thời kỳ và nhánh song song):
Văn hóa Hòa Bình · Văn hóa Bắc Sơn · Văn hóa Đông Sơn · Hùng Vương · An Dương Vương · Hai Bà Trưng · Lý Nam Đế · Ngô Quyền · Trận Bạch Đằng (938) · Chăm Pa · Lý Thường Kiệt · Trần Hưng Đạo · Trận Bạch Đằng (1288) · Lê Lợi · Quang Trung · Gia Long · Phong trào Cần Vương · Cách mạng Tháng Tám

---

## 8. Thứ tự triển khai (xong mốc nào cũng chạy được)

| M | Nội dung | File chính | Điều kiện coi là "xong" |
|---|---|---|---|
| **M1** Hạ tầng | docker-compose, requirements, config, ollama_client, store, `hgr doctor` | `docker-compose.yml`, `config.py`, `llm/ollama_client.py`, `graph/store.py`, `scripts/setup.ps1` | `hgr doctor`: Neo4j OK, 2 model đã được pull, `chat_json` trả JSON hợp lệ |
| **M2** Phân kỳ và backbone | `periods.yaml` (5 era, 32 period), `backbone/*.yaml`, `periods.py` | `configs/periods.yaml`, `configs/backbone/*`, `src/hgr/periods.py` | `pytest tests/test_periods.py` pass. `hgr periods --check` không báo khoảng năm nào bị hở ngoài ý muốn |
| **M3** Ingest và Process | wiki/wikidata client, collector, parser, normalize, chunker | `ingest/*`, `process/*`, `configs/seeds.yaml` | `hgr ingest/parse/chunk --profile mini` ra khoảng 130 chunk có header và `period_id`. `missing_seeds.txt` rỗng. Test normalize, parser, chunker pass |
| **M4** Extract | schemas, prompts (few-shot theo era), structured_seed, extractor, validator, cache | `extract/*`, `configs/ontology.yaml`, `configs/infobox_map.yaml` | Chạy thử 10 chunk rải các thời kỳ: 100% JSON hợp lệ, bị loại dưới 30%. Chạy lại lần 2 dùng cache |
| **M5** Resolve, Load, Embed | resolver, loader (Era/Period/backbone/IN_PERIOD), embedder | `resolve/resolver.py`, `graph/loader.py`, `embed/embedder.py` | "Trần Hưng Đạo" chỉ có 1 node. Hai trận Bạch Đằng 938 và 1288 là 2 node riêng. Mỗi `Period` có ít nhất 1 `IN_PERIOD`. Các index ở trạng thái ONLINE |
| **M6** Retrieval và Answer | period_rules, analyzer, linker, chunk_search, graph_search, fusion, context, answerer | `retrieve/*`, `generate/*` | `hgr ask` trả lời đúng 5 câu mẫu của profile mini, có `[n]`. Câu hỏi về năm 1954 bị từ chối |
| **M7** API và UI | FastAPI SSE, `/periods`, Streamlit (6 tab/khu vực) | `api/*`, `ui/*`, `scripts/run_demo.ps1` | Demo chạy trên trình duyệt: chat, đồ thị, timeline theo thời kỳ, khám phá giai đoạn |
| **M8** Eval và baseline | questions.jsonl (~120 câu), baseline_rag, run_eval | `eval/*` | Có `eval/report.md`, điểm chia theo intent và theo thời kỳ |
| **M9** Build `core`, rồi `full` | Chạy theo lịch build (Mục 2), tinh chỉnh quota và prompt cho các giai đoạn yếu | `scripts/build_index.ps1`, `configs/periods.yaml` | `hgr stats --by-period`: 32/32 giai đoạn có dữ liệu, không giai đoạn nào dưới 3% entity |
| **M10** Hoàn thiện | Rerank, README, e2e test, dọn code | `README.md`, `tests/test_e2e_smoke.py` | `pytest` pass toàn bộ. `setup.ps1` rồi `build mini` rồi `run_demo.ps1` chạy trót lọt trên máy sạch |
| *(Sau demo)* | Community detection (Leiden) để tóm tắt từng giai đoạn; vLLM trên WSL2; giao diện Next.js | – | – |

---

## 9. Các điểm kỹ thuật quyết định chất lượng

1. **Luôn đặt `num_ctx`.** Giá trị mặc định của Ollama có thể lặng lẽ cắt bớt prompt. Cần log số token và cảnh báo khi dùng quá 90%.
2. **Dùng JSON schema qua `format=` với `temperature=0`.** Parse lỗi thì retry tối đa 2 lần, sau đó bỏ qua và ghi log.
3. **Chuẩn hóa NFC ở mọi điểm vào**: dữ liệu Wiki, output của LLM và câu hỏi của người dùng.
4. **Tận dụng nguồn có sẵn: wikilink, Wikidata, infobox và backbone.** Chúng cho độ tin cậy cao và không tốn LLM. Backbone là khung trục để các dữ liệu khác bám vào.
5. **Evidence phải là câu trích nguyên văn** có trong chunk. Đây là chốt chặn chống bịa.
6. **Lọc node hub** theo phân vị 99 của degree (các node như Việt Nam, Trung Quốc, Pháp, Nhà Nguyễn), và dùng PPR thay cho BFS thuần.
7. **Luôn có fallback**, theo thứ tự: luật giai đoạn → LLM → chỉ vector.
8. **Không cho model 4B tự viết Cypher (Text2Cypher tự do).** Câu hỏi thống kê dùng Cypher template có sẵn.
9. **Trùng tên giữa các giai đoạn**, ví dụ Trận Bạch Đằng 938/981/1288, Nhà Lý và Nhà Tiền Lý, Hậu Lý Nam Đế, Lê Hoàn và Lê Lợi, các vua trùng miếu hiệu (Thái Tổ, Thái Tông, Nhân Tông…). Khi resolve bắt buộc so năm và giai đoạn. `display_name` kèm năm.
10. **Một người nhiều tên** (tên húy, miếu hiệu, niên hiệu, tước hiệu, bí danh), ví dụ Nguyễn Huệ = Quang Trung = Bắc Bình Vương; Nguyễn Tất Thành = Nguyễn Ái Quốc = Hồ Chí Minh.
11. **Địa danh đổi tên** (Đại La → Thăng Long → Đông Kinh → Hà Nội; Gia Định → Sài Gòn; Phú Xuân → Huế). Mỗi địa danh là 1 node, với `historical_names` ghi kèm khoảng năm.
12. **Truyền thuyết và mốc còn tranh luận** (Hồng Bàng, Âu Lạc, thời điểm bắt đầu Bắc thuộc) được gắn cờ. Câu trả lời phải nói rõ.
13. **Nhánh song song** (Chăm Pa, Phù Nam, Chân Lạp) không nối vào chuỗi `NEXT`. Câu hỏi về miền Trung và miền Nam trước thế kỷ XVII phải xét cả nhánh này.
14. **Dữ liệu lệch giữa các giai đoạn.** Quota Tier A theo từng giai đoạn cùng cảnh báo trong `stats` giúp đồ thị cân bằng.
15. **Few-shot riêng cho từng thời kỳ.** Ví dụ trích xuất cho thời tiền sử (văn hóa, di chỉ) khác hẳn thời cận đại (tổ chức, phong trào). Nếu dùng một bộ few-shot chung, model 4B sẽ trích xuất lệch.

---

## 10. Verification

1. **Unit test** (không cần dịch vụ ngoài): `pytest tests -m "not e2e"`

   | Nhóm | Nội dung kiểm tra |
   |---|---|
   | normalize | NFC; "179 TCN" → −179; "thế kỷ III TCN" → [−300, −201]; "cuối thế kỷ XVIII"; can chi có năm trong ngoặc; "niên hiệu Hồng Đức thứ 14" → 1483; "2/9/1945" |
   | periods | "thời Bắc thuộc" → [−179, 938]; "Bắc thuộc lần 2" → [43, 544] (khớp tên dài nhất); năm 1300 → `tran` + `champa` (nhánh song song); 1954 → ngoài phạm vi |
   | chunker | Không cắt giữa câu; có header; loại chunk chỉ chứa năm > 1945 |
   | validator | Loại sai domain/range; loại evidence bịa; loại sự kiện > 1945 |
   | resolver | Nguyễn Ái Quốc = Hồ Chí Minh; không gộp Bạch Đằng 938/981/1288; không gộp Nhà Lý với Nhà Tiền Lý; không gộp Lý Thái Tổ với Lê Thái Tổ |

2. **Hạ tầng:** `hgr doctor`.
3. **Build mini:** `scripts\build_index.ps1 -Profile mini`.
   - Kỳ vọng: 18 bài, khoảng 470 chunk (đo thực tế; bài Wikipedia dài hơn ước tính ban đầu ~130), cả 5 thời kỳ đều có dữ liệu.
   - Kiểm tra trùng tên: `MATCH (e:Entity) WITH toLower(e.name) n, count(*) c WHERE c>1 RETURN n,c` phải chỉ còn các trường hợp trùng tên hợp lệ (đã có năm trong `display_name`).
4. **Phân bố dữ liệu:** sau khi build `core` hoặc `full`, `hgr stats --by-period` phải cho thấy 32/32 giai đoạn có entity và relation, và không giai đoạn nào dưới 3%.
5. **E2E:** `pytest tests/test_e2e_smoke.py -m e2e`. Test hỏi 5 câu (mỗi thời kỳ 1 câu) và kiểm tra câu trả lời có từ khóa đúng cùng ít nhất một `[n]`.
6. **Demo thủ công** tại http://localhost:8501. Bật/tắt chế độ "chỉ vector" để thấy khác biệt. Bộ câu mẫu theo thời kỳ:

   | Thời kỳ | Câu hỏi | Kỳ vọng |
   |---|---|---|
   | I. Tiền sử | "Văn hóa Hòa Bình và văn hóa Bắc Sơn khác nhau thế nào?" | Năm ghi dạng xấp xỉ |
   | II. Dựng nước | "An Dương Vương xây thành Cổ Loa ở đâu và vì sao Âu Lạc mất nước?" | Có ghi "theo truyền thuyết" |
   | III. Bắc thuộc | "Kể tên các cuộc khởi nghĩa thời Bắc thuộc theo thứ tự thời gian." | Đi qua các giai đoạn 6–11 |
   | III. Bắc thuộc | "Khúc Thừa Dụ và Dương Đình Nghệ có vai trò gì trong thời kỳ tự chủ?" | |
   | Song song | "Chế Bồng Nga đã tấn công Đại Việt những lần nào?" | Kết nối nhánh Chăm Pa với nhà Trần |
   | IV. Phong kiến | "Ba trận Bạch Đằng (938, 981, 1288) khác nhau thế nào về người chỉ huy và đối thủ?" | Không gộp nhầm các trận |
   | IV. Phong kiến | "Vị vua nào trị vì khi diễn ra trận Bạch Đằng năm 1288, và cha của vị vua đó là ai?" | Multi-hop |
   | IV. Phong kiến | "Thăng Long có những tên gọi nào qua các thời kỳ?" | |
   | IV. Phong kiến | "Quang Trung và Gia Long có quan hệ gì?" | Relational: tìm đường A↔B |
   | V. Cận đại | "Hòa ước Patenôtre năm 1884 quy định những gì?" | |
   | V. Cận đại | "Nguyễn Ái Quốc thành lập những tổ chức nào trước năm 1945?" | |
   | V. Cận đại | "Sự kiện nào diễn ra ở Nam Bộ ngày 23/9/1945?" | |
   | Tổng quan | "Tóm tắt thời kỳ Trịnh – Nguyễn phân tranh." | Seed từ `Period` |
   | Ngoài phạm vi | "Chiến dịch Điện Biên Phủ diễn ra thế nào?" | "Nằm ngoài phạm vi dữ liệu (đến hết năm 1945)" |
   | Không có dữ liệu | "Nhà Trần có quan hệ gì với Napoleon?" | "Dữ liệu hiện có chưa đề cập…" |

7. **Eval:** `hgr eval` sinh `eval/report.md`.
   - Bộ câu hỏi khoảng 120 câu: mỗi giai đoạn khoảng 3 câu (~96), thêm 15 câu xuyên giai đoạn, 5 câu ngoài phạm vi và 4 câu truyền thuyết/tranh luận.
   - Báo cáo có accuracy (LLM-judge) chia theo intent và theo thời kỳ, cùng độ trễ p50/p95.
   - Kỳ vọng GraphRAG vượt baseline ở nhóm multihop, temporal, relational và overview.
