# Graph Schema: Chatbot Lịch sử Việt Nam (GraphRAG Local)

> **Mục đích tài liệu:** Xác lập hợp đồng giao diện dữ liệu (data contract) giữa **Phần B** (Trích xuất tri thức, Hợp nhất thực thể, Nạp Neo4j) và **Phần C** (Truy hồi lai Graph+Vector, Xây dựng ngữ cảnh và Tạo câu trả lời) trước khi thực hiện viết lại mã nguồn trích xuất.
> **Căn cứ thiết kế:** [PLAN.md Mục 4](file:///d:/Desktop/5/SEG301/Vietnam-History-Chatbot/PLAN.md#L335-L387), [configs/ontology.yaml](file:///d:/Desktop/5/SEG301/Vietnam-History-Chatbot/configs/ontology.yaml), [configs/periods.yaml](file:///d:/Desktop/5/SEG301/Vietnam-History-Chatbot/configs/periods.yaml), [src/hgr/extract/schemas.py](file:///d:/Desktop/5/SEG301/Vietnam-History-Chatbot/src/hgr/extract/schemas.py), [src/hgr/graph/schema.cypher](file:///d:/Desktop/5/SEG301/Vietnam-History-Chatbot/src/hgr/graph/schema.cypher).

---

## A. Mô hình Node (Đỉnh)

Mỗi node trong Neo4j đại diện cho một thực thể tri thức, đơn vị văn bản hoặc đơn vị phân kỳ lịch sử.

### 1. Nhãn chính và Nhãn phụ
- **Node tri thức:** Mang nhãn chính `:Entity` và **bắt buộc mang thêm đúng 1 nhãn phụ** theo phân loại loại thực thể:
  - `:Person`: Nhân vật lịch sử (vua, tướng, quan lại, thủ lĩnh, chí sĩ, nhà cách mạng, nhân vật truyền thuyết).
  - `:Event`: Biến cố, sự kiện lịch sử (trận đánh, chiến tranh, khởi nghĩa, hòa ước, cải cách, phong trào, đảo chính, thành lập).
  - `:Place`: Địa danh, kinh đô, thành lũy, sông, núi, di chỉ khảo cổ.
  - `:Polity`: Quốc gia, triều đại, nhà nước, chính quyền lịch sử.
  - `:Organization`: Tổ chức chính trị, đảng phái, hội ái quốc, mặt trận.
  - `:Work`: Tác phẩm văn học, thư tịch lịch sử, bộ luật, chiếu, hịch, truyền thuyết.
  - `:Culture`: Văn hóa khảo cổ (Đông Sơn, Hòa Bình, Sa Huỳnh, Óc Eo...).
- **Node phân kỳ lịch sử:**
  - `:Era`: Thời kỳ lớn (5 thời kỳ: Tiền sử, Dựng nước, Bắc thuộc, Phong kiến, Cận đại).
  - `:Period`: Giai đoạn lịch sử cụ thể (29 giai đoạn trên trục chính + 3 giai đoạn thuộc nhánh song song).
- **Node văn bản:**
  - `:Article`: Bài viết gốc từ Wikipedia tiếng Việt.
  - `:Chunk`: Đoạn văn bản đã phân đoạn (~500 token) có ngữ cảnh tiêu đề.

---

### 2. Bảng thuộc tính từng loại Node

#### Bảng 1: Thuộc tính Node `:Entity` (kèm nhãn phụ)
| Thuộc tính | Kiểu dữ liệu | Bắt buộc | Ý nghĩa và Quy ước |
|---|---|---|---|
| `id` | String | **Có** | Định danh duy nhất toàn hệ thống (`qid:Q...` hoặc `local:...`). Unique Constraint. |
| `name` | String | **Có** | Tên chuẩn hóa tiếng Việt có dấu, dạng phổ biến nhất (ví dụ: "Lý Thường Kiệt"). |
| `display_name` | String | **Có** | Tên hiển thị trên giao diện và đồ thị; **kèm năm nếu trùng tên** (ví dụ: "Trận Bạch Đằng (1288)"). |
| `type` | String | **Có** | Khớp với nhãn phụ: `Person`, `Event`, `Place`, `Polity`, `Organization`, `Work`, `Culture`. |
| `subtype` | String | Không | Phân loại con (áp dụng cho `Event`): `Battle`, `War`, `Uprising`, `Treaty`, `Reform`, `Movement`, `Coup`, `Founding`. |
| `aliases` | List[String] | Không | Danh sách các tên gọi khác (tên húy, miếu hiệu, niên hiệu, bí danh, tên chữ Hán/Pháp). |
| `aliases_text` | String | Không | Chuỗi nối `name` và `aliases` bằng khoảng trắng để đánh chỉ mục Fulltext. |
| `description` | String | Không | Câu tóm tắt ngắn về vai trò/bản chất thực thể (sinh từ infobox/Wikidata/LLM). |
| `start_year` | Integer | Không | Năm bắt đầu hoặc năm sinh/xuất hiện (TCN là số âm). Index phục vụ lọc thời gian. |
| `end_year` | Integer | Không | Năm kết thúc hoặc năm mất/suy tàn (TCN là số âm). |
| `year_precision`| String | Không | Độ chính xác thời gian: `day`, `month`, `year`, `century`, `millennium`, `approx`. |
| `legendary` | Boolean | Không | `true` nếu là nhân vật/yếu tố truyền thuyết (Hùng Vương, An Dương Vương, Thánh Gióng...). |
| `disputed` | Boolean | Không | `true` nếu mốc thời gian/sự kiện còn tranh cãi học thuật. |
| `period_ids` | List[String] | Không | Danh sách mã giai đoạn mà thực thể hoạt động hoặc tồn tại. |
| `degree` | Integer | Không | Bậc đồ thị (số cạnh liên kết), tính toán sau khi nạp để lọc hub node và tính PPR. |
| `embedding` | List[Float] | Không | Vector nhúng 1024 chiều từ mô hình `bge-m3` qua Ollama. Vector Index. |
| `historical_names`| String (JSON)| Không | Riêng cho `:Place`: chuỗi JSON danh sách tên theo thời kỳ `[{"name": "Thăng Long", "start": 1010, "end": 1397}, ...]`. |

#### Bảng 2: Thuộc tính Node `:Chunk`
| Thuộc tính | Kiểu dữ liệu | Bắt buộc | Ý nghĩa và Quy ước |
|---|---|---|---|
| `id` | String | **Có** | Mã chunk duy nhất dạng `<page_id>-<index:03d>` (ví dụ: `1582-001`). Unique Constraint. |
| `page_id` | Integer | **Có** | Mã trang Wikipedia tương ứng. |
| `page_title` | String | **Có** | Tiêu đề bài viết Wikipedia tiếng Việt. |
| `section_path` | String | **Có** | Đường dẫn tiêu đề mục trong bài viết (ví dụ: "Thân thế và sự nghiệp > Kháng chiến chống Tống"). |
| `header` | String | **Có** | Header ngữ cảnh tạo sẵn: `[Bài: ... \| Mục: ... \| Chủ thể: ... \| Giai đoạn: ...]`. |
| `text` | String | **Có** | Nội dung đoạn văn thuần túy (đã chuẩn hóa Unicode NFC). Fulltext Index. |
| `tokens` | Integer | **Có** | Số token ước tính của đoạn. |
| `min_year` | Integer | Không | Năm nhỏ nhất đề cập trong đoạn (dùng để lọc và đánh index). |
| `max_year` | Integer | Không | Năm lớn nhất đề cập trong đoạn. |
| `period_id` | String | **Có** | Mã giai đoạn chính mà bài viết/đoạn văn thuộc về. Range Index. |
| `chunk_index` | Integer | Không | Chỉ số thứ tự của chunk trong bài viết (0-indexed). |
| `tier` | String | Không | Cấp độ trích xuất bài viết: `A` (toàn văn) hoặc `B` (tối đa `max_chunks_b` chunk đầu). |
| `embedding` | List[Float] | Không | Vector nhúng 1024 chiều của `header + \n + text` (`bge-m3`). Vector Index. |

#### Bảng 3: Thuộc tính Node `:Period` và `:Era`
| Node | Thuộc tính | Kiểu dữ liệu | Bắt buộc | Ý nghĩa |
|---|---|---|---|---|
| `:Era` | `id` | String | **Có** | `tiensu`, `dungnuoc`, `bacthuoc`, `phongkien`, `candai`, `songsong`. Unique. |
| `:Era` | `name` | String | **Có** | Tên thời kỳ ("Phong kiến độc lập",...). |
| `:Era` | `start` / `end` | Integer | **Có** | Khoảng năm bao quát thời kỳ (TCN là số âm). |
| `:Era` | `color` | String | **Có** | Mã màu hex (ví dụ: `#b5452f`) dùng để hiển thị UI Streamlit. |
| `:Period` | `id` | String | **Có** | Mã giai đoạn duy nhất (`vanlang`, `tran`, `champa`,...). Unique. |
| `:Period` | `name` | String | **Có** | Tên giai đoạn lịch sử ("Nhà Trần", "Khởi nghĩa Hai Bà Trưng",...). |
| `:Period` | `era_id` | String | **Có** | ID của Era cha chứa Period này. |
| `:Period` | `start` / `end` | Integer | **Có** | Khoảng năm của giai đoạn. |
| `:Period` | `parallel` | Boolean | **Có** | `true` nếu thuộc nhánh song song (Phù Nam, Chăm Pa, Chân Lạp - Nam Bộ). |
| `:Period` | `legendary` | Boolean | Không | `true` nếu giai đoạn mang tính truyền thuyết (Hồng Bàng - Văn Lang). |
| `:Period` | `disputed` | Boolean | Không | `true` nếu mốc thời gian còn tranh luận học thuật. |
| `:Period` | `alt_start`/`alt_end`| Integer | Không | Năm thay thế theo quan điểm học thuật khác (ví dụ: Triệu Đà -208 thay vì -179). |

---

## B. Mô hình Quan hệ (Cạnh)

### 1. Quan hệ cấu trúc và phân kỳ
| Tên quan hệ | Chiều | Head hợp lệ | Tail hợp lệ | Ý nghĩa và Quy ước |
|---|---|---|---|---|
| `PART_OF` | `(p)-[:PART_OF]->(e)` | `:Period` | `:Era` | Phân cấp giai đoạn thuộc về thời kỳ lớn. |
| `NEXT` | `(p1)-[:NEXT]->(p2)` | `:Period` | `:Period` | Thứ tự thời gian kế tiếp trên trục chính (không áp dụng cho nhánh `parallel: true`). |
| `HAS_CHUNK` | `(a)-[:HAS_CHUNK]->(c)` | `:Article` | `:Chunk` | Bài viết sở hữu các chunk phân đoạn. |
| `ABOUT` | `(a)-[:ABOUT]->(e)` | `:Article` | `:Entity` | Bài viết có chủ thể chính là thực thể `e`. |
| `MENTIONS` | **`(c)-[:MENTIONS]->(e)`** | **`:Chunk`** | **`:Entity`** | **Chunk nhắc tới thực thể. Bắt buộc chiều Chunk → Entity.** |
| `IN_PERIOD` | `(e)-[:IN_PERIOD]->(p)` | `:Entity` | `:Period` | Thực thể tồn tại/hoạt động trong giai đoạn (tính theo overlap năm hoặc gán seed). |

### 2. Quan hệ ngữ nghĩa tri thức (Ontology Domain → Range)
Định nghĩa 21 loại quan hệ nghiệp vụ, khớp tuyệt đối với [configs/ontology.yaml](file:///d:/Desktop/5/SEG301/Vietnam-History-Chatbot/configs/ontology.yaml#L14-L35):

| STT | Tên quan hệ | Chiều Head → Tail | Domain (Head hợp lệ) | Range (Tail hợp lệ) | Ý nghĩa nghiệp vụ |
|---|---|---|---|---|---|
| 1 | `CHILD_OF` | `(a)-[:CHILD_OF]->(b)` | `Person` | `Person` | `a` là con đẻ hoặc con nuôi của `b`. |
| 2 | `SPOUSE_OF` | `(a)-[:SPOUSE_OF]->(b)` | `Person` | `Person` | `a` là vợ/chồng/phối ngẫu của `b`. |
| 3 | `MEMBER_OF` | `(a)-[:MEMBER_OF]->(b)` | `Person` | `Polity`, `Organization` | `a` là thành viên/đảng viên của tổ chức/chính thể `b`. |
| 4 | `BORN_IN` | `(a)-[:BORN_IN]->(b)` | `Person` | `Place` | `a` sinh ra tại địa danh `b`. |
| 5 | `DIED_IN` | `(a)-[:DIED_IN]->(b)` | `Person` | `Place` | `a` mất hoặc hi sinh tại địa danh `b`. |
| 6 | `RULED` | `(a)-[:RULED]->(b)` | `Person` | `Polity` | `a` là vua/quân vương trị vì chính thể/triều đại `b`. |
| 7 | `RULED_OVER` | `(a)-[:RULED_OVER]->(b)` | `Polity`, `Person` | `Place`, `Polity` | `a` cai trị/đô hộ lãnh thổ/chính quyền `b` (kèm `role`: thái thú, toàn quyền...). |
| 8 | `SUCCEEDED` | `(a)-[:SUCCEEDED]->(b)` | `Person`, `Polity`, `Culture` | `Person`, `Polity`, `Culture` | `a` kế nhiệm/kế thừa vị trí của `b`. |
| 9 | `FOUNDED` | `(a)-[:FOUNDED]->(b)` | `Person` | `Polity`, `Organization`, `Place` | `a` sáng lập/xây dựng nên chính thể, tổ chức hoặc kinh thành `b`. |
| 10 | `CAPITAL_OF` | `(a)-[:CAPITAL_OF]->(b)` | `Place` | `Polity` | `a` là kinh đô/thủ phủ của triều đại/quốc gia `b`. |
| 11 | `COMMANDED` | `(a)-[:COMMANDED]->(b)` | `Person` | `Event` | `a` là tướng soái/chỉ huy trong sự kiện/trận đánh `b`. |
| 12 | `PARTICIPATED_IN` | `(a)-[:PARTICIPATED_IN]->(b)` | `Person`, `Polity`, `Organization` | `Event` | `a` tham gia vào sự kiện/chiến dịch `b` (kèm `side`, `role`). |
| 13 | `OPPOSED` | `(a)-[:OPPOSED]->(b)` | `Person`, `Polity`, `Organization` | `Person`, `Polity`, `Organization` | `a` đối đầu, kháng cự hoặc giao tranh với `b`. |
| 14 | `OCCUPIED` | `(a)-[:OCCUPIED]->(b)` | `Polity` | `Place`, `Polity` | Chính thể `a` chiếm đóng/chiếm cứ lãnh thổ `b`. |
| 15 | `OCCURRED_AT` | `(a)-[:OCCURRED_AT]->(b)` | `Event` | `Place` | Sự kiện `a` diễn ra tại địa điểm `b`. |
| 16 | `PART_OF` | `(a)-[:PART_OF]->(b)` | `Event`, `Place` | `Event`, `Place` | Sự kiện/địa điểm `a` là một phần của sự kiện/địa danh lớn hơn `b`. |
| 17 | `CAUSED` | `(a)-[:CAUSED]->(b)` | `Event` | `Event` | Sự kiện `a` là nguyên nhân trực tiếp dẫn tới biến cố `b`. |
| 18 | `LED_TO` | `(a)-[:LED_TO]->(b)` | `Event` | `Event` | Sự kiện `a` dẫn tới kết quả/bước ngoặt `b`. |
| 19 | `SIGNED` | `(a)-[:SIGNED]->(b)` | `Person`, `Polity` | `Event` | `a` ký kết hòa ước/hiệp định/văn kiện `b`. |
| 20 | `AUTHORED` | `(a)-[:AUTHORED]->(b)` | `Person` | `Work` | `a` là tác giả/người soạn thảo văn bản/tác phẩm `b`. |
| 21 | `FOUND_AT` | `(a)-[:FOUND_AT]->(b)` | `Culture` | `Place` | Văn hóa khảo cổ `a` được phát hiện/khai quật tại di chỉ `b`. |

### 3. Bảng thuộc tính bắt buộc trên cạnh ngữ nghĩa
Mỗi cạnh quan hệ ngữ nghĩa (từ STT 1–21) **bắt buộc mang đầy đủ các thuộc tính sau** để phục vụ việc trích dẫn nguồn `[n]` ở Phần C:
| Thuộc tính cạnh | Kiểu dữ liệu | Bắt buộc | Ý nghĩa và Quy ước |
|---|---|---|---|
| `id` | String | **Có** | Khóa định danh cạnh: `rel:<head_id>:<REL_TYPE>:<tail_id>`. |
| `start_year` | Integer | Không | Năm bắt đầu của quan hệ/sự kiện (TCN là số âm). |
| `end_year` | Integer | Không | Năm kết thúc của quan hệ/sự kiện. |
| `role` | String | Không | Vai trò cụ thể: "thái thú", "chủ tịch", "tổng chỉ huy"... |
| `side` | String | Không | Phía/phe tham chiến: "Đại Việt", "Quân Nguyên", "Việt Minh"... |
| `confidence` | Float | **Có** | Độ tin cậy (từ 0.0 đến 1.0; trích xuất LLM: `0.7-0.9`, curated/wikidata: `0.95-1.0`). |
| `source` | String | **Có** | Nguồn gốc tạo cạnh: `curated` (backbone), `wikidata`, `infobox`, `llm`. |
| `evidence` | String | **Có** | Câu văn trích dẫn nguyên văn chứng minh mối quan hệ. |
| **`evidence_chunk_ids`**| **List[String]**| **Có** | **Mảng chứa ID các chunk làm bằng chứng (ví dụ: `["1582-001", "2401-003"]`). Bắt buộc cho Phần C.** |
| `evidence_quotes` | List[String] | Không | Mảng chứa các câu trích tương ứng từ từng chunk. |

---

## C. Quy ước ID Thực thể (Entity Resolution Contract)

Nhằm đảm bảo tính duy nhất, tránh phân mảnh và tránh gộp sai, ID của Node `:Entity` tuân thủ quy tắc sau:

1. **Thực thể có Wikidata QID:**
   - Định dạng: `qid:Q<số>` (ví dụ: `qid:Q7186` cho Chủ tịch Hồ Chí Minh, `qid:Q10798229` cho Ngô Quyền).
   - Được ưu tiên cao nhất khi thực thể liên kết thành công với Wikidata bài viết hoặc wikilink.

2. **Thực thể cục bộ (không có QID hoặc từ LLM):**
   - Định dạng: `local:<slug>`
   - **Quy tắc sinh slug (thống nhất với [resolver.py:18-24](file:///d:/Desktop/5/SEG301/Vietnam-History-Chatbot/src/hgr/resolve/resolver.py#L18-L24)):**
     1. Chuẩn hóa NFC văn bản gốc.
     2. Đổi chữ hoa sang chữ thường (`lower()`), thay chữ `đ` thành `d`.
     3. Chuẩn hóa NFKD và loại bỏ hoàn toàn dấu kết hợp combining diacritics.
     4. Xóa bỏ toàn bộ ký tự không phải `[a-z0-9\s\-]`.
     5. Thay thế khoảng trắng liên tiếp bằng dấu gạch ngang đơn `-`, cắt bỏ gạch ngang ở đầu/cuối.
     - *Ví dụ:* `"Lý Thường Kiệt"` → `local:ly-thuong-kiet`.

3. **Quy tắc giải quyết thực thể trùng tên khác thời kỳ (Disambiguation Contract):**
   - **Đối với `Event`:** Nếu trùng tên nhưng diễn ra ở các năm/giai đoạn khác nhau (như các trận Bạch Đằng, chiến tranh Tống - Việt), **bắt buộc tạo ID riêng có gắn đuôi năm**:
     - `local:tran-bach-dang-938` (giai đoạn `ngo`, năm 938).
     - `local:tran-bach-dang-981` (giai đoạn `tienle`, năm 981).
     - `local:tran-bach-dang-1288` (giai đoạn `tran`, năm 1288).
     - Thuộc tính `display_name` tương ứng: `"Trận Bạch Đằng (938)"`, `"Trận Bạch Đằng (981)"`, `"Trận Bạch Đằng (1288)"`.
   - **Đối với `Person`:** Các nhân vật trùng miếu hiệu/tên (Lê Thái Tổ, Lý Thái Tổ; Lê Thái Tông, Trần Thái Tông) phải phân biệt qua triều đại/năm trị vì trong slug nếu không có QID (ví dụ: `local:ly-thai-to`, `local:le-thai-to`).

---

## D. Quy ước Thời gian và Lịch sử

1. **Trục năm (Timeline):**
   - Biểu diễn thời gian thống nhất bằng số nguyên `Integer`.
   - **Năm TCN (Trước Công Nguyên):** Lưu bằng **số âm**. Ví dụ: năm 179 TCN ghi là `-179`, năm 2879 TCN ghi là `-2879`. Quy ước không có năm 0 (1 TCN = `-1`, sau đó đến năm 1 SCN).
   - **Thế kỷ và thiên niên kỷ:** Quy đổi thành khoảng đóng `[start_year, end_year]`. Ví dụ: "Thế kỷ X" → `start_year: 901, end_year: 1000`; "Thế kỷ III TCN" → `start_year: -300, end_year: -201`.

2. **Mốc cắt 1945 (Temporal Cutoff):**
   - Phạm vi dữ liệu của hệ thống kết thúc vào ngày **31/12/1945**.
   - Cạnh sự kiện có `start_year > 1945` sẽ bị loại bỏ ở khâu trích xuất.
   - Thuộc tính của nhân vật sinh trước 1945 nhưng mất sau 1945 (như năm mất 1969 của Hồ Chí Minh) vẫn được bảo lưu đầy đủ trên node thực thể.

3. **Gắn cờ truyền thuyết và tranh luận:**
   - Nếu thực thể hoặc sự kiện thuộc giai đoạn truyền thuyết (Hồng Bàng, An Dương Vương): gán `legendary: true`. Khi truy hồi trả lời ở Phần C, câu trả lời sẽ mở đầu bằng *"Theo truyền thuyết..."*.
   - Nếu mốc thời gian còn tranh cãi học thuật: gán `disputed: true` và lưu các mốc năm thay thế trong `alt_start`, `alt_end`.

---

## E. Chỉ mục và Ràng buộc (Neo4j Constraints & Indexes)

Các lệnh sau được khai báo trong [schema.cypher](file:///d:/Desktop/5/SEG301/Vietnam-History-Chatbot/src/hgr/graph/schema.cypher) và được thực thi tự động ở bước `hgr load`:

```cypher
// 1. Ràng buộc duy nhất (Unique Constraints)
CREATE CONSTRAINT entity_id IF NOT EXISTS FOR (e:Entity) REQUIRE e.id IS UNIQUE;
CREATE CONSTRAINT chunk_id  IF NOT EXISTS FOR (c:Chunk)  REQUIRE c.id IS UNIQUE;
CREATE CONSTRAINT period_id IF NOT EXISTS FOR (p:Period) REQUIRE p.id IS UNIQUE;
CREATE CONSTRAINT era_id    IF NOT EXISTS FOR (e:Era)    REQUIRE e.id IS UNIQUE;
CREATE CONSTRAINT article_id IF NOT EXISTS FOR (a:Article) REQUIRE a.page_id IS UNIQUE;

// 2. Chỉ mục toàn văn (Fulltext Indexes)
CREATE FULLTEXT INDEX entity_names IF NOT EXISTS FOR (e:Entity) ON EACH [e.name, e.aliases_text];
CREATE FULLTEXT INDEX chunk_text   IF NOT EXISTS FOR (c:Chunk)  ON EACH [c.text];
CREATE FULLTEXT INDEX period_names IF NOT EXISTS FOR (p:Period) ON EACH [p.name, p.aliases_text];

// 3. Chỉ mục Vector (Vector Indexes - 1024 chiều, Cosine)
CREATE VECTOR INDEX entity_vec IF NOT EXISTS FOR (e:Entity) ON e.embedding
  OPTIONS {indexConfig: {`vector.dimensions`: 1024, `vector.similarity_function`: 'cosine'}};
CREATE VECTOR INDEX chunk_vec IF NOT EXISTS FOR (c:Chunk) ON c.embedding
  OPTIONS {indexConfig: {`vector.dimensions`: 1024, `vector.similarity_function`: 'cosine'}};

// 4. Chỉ mục phạm vi (Range Indexes)
CREATE INDEX entity_start IF NOT EXISTS FOR (e:Entity) ON (e.start_year);
CREATE INDEX chunk_min    IF NOT EXISTS FOR (c:Chunk)  ON (c.min_year);
CREATE INDEX chunk_period IF NOT EXISTS FOR (c:Chunk)  ON (c.period_id);
```

---

## F. Truy vấn Mẫu dành cho Phần C (Retrieval Cypher Templates)

Dưới đây là 4 mẫu truy vấn Cypher chuẩn mà Phần C sẽ sử dụng trực tiếp trên đồ thị do Phần B cung cấp:

### 1. Lấy Subgraph 2 bước cục bộ quanh thực thể Seed (có lọc thời gian và bậc Hub Node)
```cypher
// Đầu vào: $seeds (list entity IDs), $y0, $y1 (khoảng năm lọc), $maxdeg (ngưỡng lọc hub node, ví dụ 150)
MATCH (s:Entity) WHERE s.id IN $seeds
CALL (s) {
  MATCH p=(s)-[r*1..2]-(n:Entity)
  WHERE all(x IN r WHERE ($y0 IS NULL OR x.start_year IS NULL OR
            (x.start_year <= $y1 + 5 AND coalesce(x.end_year, x.start_year) >= $y0 - 5)))
    AND all(m IN nodes(p)[1..] WHERE m.degree <= $maxdeg)
  RETURN p LIMIT 400
}
RETURN p
```

### 2. Truy xuất chuỗi sự kiện theo thứ tự thời gian trong một giai đoạn
```cypher
// Đầu vào: $period_id (ví dụ: 'bacthuoc_2' hoặc 'tran')
MATCH (e:Event)-[:IN_PERIOD]->(p:Period {id: $period_id})
WHERE e.start_year IS NOT NULL
OPTIONAL MATCH (leader:Person)-[:COMMANDED]->(e)
RETURN e.display_name AS su_kien,
       e.start_year AS nam_bat_dau,
       e.end_year AS nam_ket_thuc,
       e.subtype AS loai_su_kien,
       collect(DISTINCT leader.display_name) AS lanh_dao
ORDER BY e.start_year ASC;
```

### 3. Tìm đường liên kết ngắn nhất giữa hai thực thể (Quan hệ A ↔ B)
```cypher
// Đầu vào: $id_a, $id_b (ví dụ: Quang Trung và Gia Long)
MATCH (a:Entity {id: $id_a}), (b:Entity {id: $id_b})
MATCH p = allShortestPaths((a)-[*..4]-(b))
WHERE all(n IN nodes(p)[1..-1] WHERE n.degree < 200) // Loại bỏ các node quá lớn như "Việt Nam"
RETURN p LIMIT 5;
```

### 4. Truy vết ngược từ cạnh quan hệ sang các Chunk dẫn chứng nguyên văn
```cypher
// Đầu vào: $rel_id (ví dụ: 'rel:local:ngo-quyen:COMMANDED:local:tran-bach-dang-938')
MATCH (a:Entity)-[r {id: $rel_id}]->(b:Entity)
UNWIND r.evidence_chunk_ids AS chunk_id
MATCH (c:Chunk {id: chunk_id})
RETURN a.display_name AS head,
       type(r) AS relation,
       b.display_name AS tail,
       r.evidence AS trich_doan_ngan,
       c.id AS chunk_id,
       c.page_title AS bai_goc,
       c.section_path AS muc,
       c.text AS noi_dung_day_du;
```

---

## G. Điểm lệch giữa Code hiện tại và Schema này (Technical Debt cần sửa)

Các điểm lệch cụ thể trong codebase hiện tại so với hợp đồng schema:

1. **Chiều quan hệ `MENTIONS` bị ngược trong Neo4j Loader:**
   - *Vị trí:* [src/hgr/graph/loader.py:184](file:///d:/Desktop/5/SEG301/Vietnam-History-Chatbot/src/hgr/graph/loader.py#L184)
   - *Hiện trạng:* Đang nạp `MERGE (e)-[:MENTIONS]->(c)` (Entity chỉ tới Chunk).
   - *Cần sửa:* Đổi thành `MERGE (c)-[:MENTIONS]->(e)` (Chunk chỉ tới Entity).

2. **Thiếu nhãn phụ (`:Person`, `:Event`,...) trên node `:Entity`:**
   - *Vị trí:* [src/hgr/graph/loader.py:121](file:///d:/Desktop/5/SEG301/Vietnam-History-Chatbot/src/hgr/graph/loader.py#L121)
   - *Hiện trạng:* Chỉ chạy `MERGE (e:Entity {id: row.id}) SET e += row.props`, không gắn thêm nhãn phụ theo `type`.
   - *Cần sửa:* Dùng `apoc.create.addLabels(e, [row.props.type])` khi nạp.

3. **Cạnh quan hệ chưa lưu mảng `evidence_chunk_ids`:**
   - *Vị trí:* [src/hgr/resolve/resolver.py:156-168](file:///d:/Desktop/5/SEG301/Vietnam-History-Chatbot/src/hgr/resolve/resolver.py#L156-L168) và [src/hgr/graph/loader.py:131-136](file:///d:/Desktop/5/SEG301/Vietnam-History-Chatbot/src/hgr/graph/loader.py#L131-L136)
   - *Hiện trạng:* Chỉ lưu chuỗi đơn `evidence: str` và không truyền `chunk_id` sang bảng quan hệ đã resolve.
   - *Cần sửa:* Cập nhật model `Triplet` và pipeline resolve để gom mảng `evidence_chunk_ids: list[str]`.

4. **Trùng tên sự kiện bị gộp sai thành 1 thực thể:**
   - *Vị trí:* [src/hgr/resolve/resolver.py:59](file:///d:/Desktop/5/SEG301/Vietnam-History-Chatbot/src/hgr/resolve/resolver.py#L59)
   - *Hiện trạng:* Mọi thực thể không có QID đều trả về `local:{_slug(name)}`, khiến 3 trận Bạch Đằng (938, 981, 1288) bị nhập thành một ID `local:tran-bach-dang`.
   - *Cần sửa:* Thêm logic kiểm tra loại `Event` và năm/giai đoạn để tách thành các slug có hậu tố năm.

5. **`display_name` chưa được gắn năm phân biệt khi trùng tên:**
   - *Vị trí:* [src/hgr/graph/loader.py:214](file:///d:/Desktop/5/SEG301/Vietnam-History-Chatbot/src/hgr/graph/loader.py#L214)
   - *Hiện trạng:* Đang gán cứng `e.display_name = coalesce(e.name, e.id)`.
   - *Cần sửa:* Bổ sung Cypher phát hiện các node trùng `name` để thêm ` (start_year)` vào `display_name`.

6. **Quan hệ `IN_PERIOD` chưa tự động tính theo overlap năm:**
   - *Vị trí:* [src/hgr/graph/loader.py:205-207](file:///d:/Desktop/5/SEG301/Vietnam-History-Chatbot/src/hgr/graph/loader.py#L205-L207)
   - *Hiện trạng:* Chỉ nạp từ mảng `e.period_ids` có sẵn, bỏ qua các thực thể có `start_year`/`end_year` nhưng mảng `period_ids` rỗng.
   - *Cần sửa:* Thêm câu lệnh Cypher tính overlap giữa khoảng năm thực thể và Period.

7. **Trích xuất Infobox làm ngược chiều quan hệ:**
   - *Vị trí:* [src/hgr/extract/structured_seed.py:101-109](file:///d:/Desktop/5/SEG301/Vietnam-History-Chatbot/src/hgr/extract/structured_seed.py#L101-L109)
   - *Hiện trạng:* Gán cứng `head = article_title`, `tail = field_value`, làm đảo ngược ý nghĩa của `COMMANDED` và `CAPITAL_OF`.
   - *Cần sửa:* Đọc cấu hình `subject` / `object` từ [configs/infobox_map.yaml](file:///d:/Desktop/5/SEG301/Vietnam-History-Chatbot/configs/infobox_map.yaml) để đặt đúng head/tail.

---

## H. Câu hỏi mở cần chốt với Người làm Phần C

Trước khi triển khai sửa đổi mã nguồn ở Phần B, người phụ trách Phần B cần chốt với người làm Phần C các vấn đề sau:

1. **Phương thức truy vấn Node Type trong Cypher:**
   - Phần C ưu tiên truy vấn theo nhãn phụ (`MATCH (p:Person)-[:RULED]->(pol:Polity)`) hay truy vấn theo thuộc tính (`MATCH (e:Entity {type: 'Person'})`)?
   - *Khuyến nghị:* Cung cấp cả hai (gán cả nhãn phụ và thuộc tính `type`) để tối ưu hiệu năng Cypher index.
2. **Quy ước định dạng `display_name` cho sự kiện trùng tên:**
   - Người làm C muốn định dạng tên hiển thị của các trận đánh trùng tên là `"Trận Bạch Đằng (1288)"` hay `"Trận Bạch Đằng năm 1288"` hay `"Trận Bạch Đằng III"`?
3. **Mức độ lọc Hub Node trên đồ thị:**
   - Ngưỡng bậc tối đa `max_degree` khi duyệt đường đi (PPR / Path A↔B) là giá trị cố định (ví dụ degree ≤ 150) hay lấy động theo phân vị 99 (p99)?
4. **Tiêu chuẩn dẫn chứng khi xuất câu trả lời:**
   - Khi hiển thị card nguồn `[n]` dưới câu trả lời, Phần C cần lấy trích đoạn ngắn lưu trên cạnh (`r.evidence`) hay sẽ luôn `MATCH` ngược về node `:Chunk` qua `r.evidence_chunk_ids` để lấy toàn văn đoạn?
5. **Xử lý các thực thể thuộc Nhánh song song (Chăm Pa, Phù Nam):**
   - Khi người dùng hỏi một câu không nêu rõ giai đoạn mà liên quan đến miền Trung/Nam thời cổ, Phần C có tự động mở rộng truy vấn sang các node nối với Period thuộc `era: songsong` không?
