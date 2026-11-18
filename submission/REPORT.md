# Báo cáo Day 09 — Nguyễn Quốc Hưng, 2A202604038

## 1. Kết luận trước

Pipeline kết luận: **Hold** (Tạm giữ thẩm định).
- **Số lượng ảnh**: Tiếp nhận 224 ảnh thô ban đầu; loại bỏ 21 ảnh không đạt ở cửa vào Bước 1 (gồm 3 ảnh nhỏ không đạt chuẩn `BAD_SIZE`, 2 ảnh hỏng `CORRUPT_IMAGE`, 8 ảnh trùng lặp tuyệt đối byte `DUP_IMAGE_EXACT`, 4 ảnh trùng lặp gần đúng `DUP_IMAGE_NEAR`, 4 ảnh rò rỉ từ tập test `LEAK_TEST`). Tổng cộng **203 ảnh** được đưa vào pipeline xử lý và xuất bản nháp tại `submission/export/clean_v1`.
- **Lý do chính**: Toàn bộ các lỗi bắt buộc (critical errors) đã được sửa tự động hoặc được người duyệt xử lý triệt để (0 lỗi bắt buộc còn lại ở vòng 3). Tuy nhiên, tỉ lệ ảnh còn cảnh báo nghi ngờ là **18.72%** (38/203 ảnh), vượt ngưỡng trần cho phép 10.00% của cửa chặn Hold. Lô dữ liệu cần được QA Lead thẩm định sâu hoặc cấp thêm ngân sách người duyệt trước khi phát hành chính thức.

---

## 2. Lỗi và phân việc

Thống kê từ `02_error_list_v1` (gom theo mã lỗi thực tế xuất hiện trong lô raw 224 ảnh):

| Mã lỗi | Số ảnh/dòng | Ai sửa (máy/người) | Vì sao |
|---|---:|---|---|
| `BAD_CLASS_NAME` | 2 dòng (data.yaml) | Máy sửa (autofix) | Quy tắc tên lớp cố định; script map lại tên lớp chuẩn trong `configs/pipeline.yaml`. |
| `BAD_SIZE` | 3 ảnh | Máy sửa (loại bỏ) | Cạnh ngắn ảnh < 250px không đủ độ phân giải chuẩn của camera, loại ở Bước 1. |
| `CORRUPT_IMAGE` | 2 ảnh | Máy sửa (loại bỏ) | Ảnh hỏng header/không giải mã được bytes, loại bỏ ngay cửa vào. |
| `DUP_IMAGE_EXACT` | 8 ảnh | Máy sửa (loại bỏ) | Trùng lặp byte 100% (MD5 hash), loại bỏ chống thiên lệch phân phối. |
| `DUP_IMAGE_NEAR` | 4 ảnh | Máy sửa (loại bỏ) | Trùng lặp khung hình gần đúng qua perceptual hash (`phash <= 8`), loại ở Bước 1. |
| `LEAK_TEST` | 4 ảnh | Máy sửa (loại bỏ) | Trùng lặp với ảnh trong kho test/val, bắt buộc loại để chống data leakage (metric ảo). |
| `BAD_CLASS_ID` | 6 dòng | Máy sửa (autofix) | ID lớp ngoài danh mục (93, -1, 4, 7); máy xoá dòng vi phạm (`drop_line`). |
| `BAD_FORMAT` | 3 dòng | Máy sửa (autofix) | Dòng thiếu cột hoặc chứa giá trị `nan`/chữ; máy xoá dòng vi phạm (`drop_line`). |
| `BOX_ZERO` | 4 dòng | Máy sửa (autofix) | Box có chiều rộng hoặc chiều cao $\le 0$; máy xoá dòng rỗng (`drop_line`). |
| `DUP_BOX` | 7 dòng | Máy sửa (autofix) | Box cùng lớp trùng lặp với box trước đó (IoU > 0.9); máy xoá box trùng sau. |
| `BOX_OUT_OF_IMAGE` | 8 dòng | Máy sửa (autofix) | Tọa độ box tràn ra ngoài viền ảnh; máy cắt (`clip_box`) về [0, 1] hoặc xoá nếu lọt ngoài. |
| `MISSING_LABEL_FILE` | 6 ảnh | Người sửa (hàng đợi) | Máy không thể bịa nhãn cho ảnh; đưa vào hàng đợi ưu tiên cao nhất để annotator gán tay. |
| `EMPTY_LABEL` | 12 ảnh | Người duyệt | File nhãn rỗng (0 KB): người cần xác định là ảnh nền (negative sample) hay sót nhãn. |
| `BOX_TINY` / `BOX_HUGE` | 6 tiny, 3 huge | Người duyệt | Box quá nhỏ (< 12px) hoặc chiếm > 95% ảnh: người thẩm định ngữ cảnh. |
| `SECOND_OPINION` (*) | 153 cảnh báo | Người duyệt | Model lớn nghi ngờ thiếu nhãn/nhầm lớp/box lệch; người xem xét và hiệu chỉnh. |

*(*) Gồm `POSSIBLE_MISSING`, `POSSIBLE_WRONG_CLASS`, `POSSIBLE_LOOSE_BOX`, `POSSIBLE_FALSE_POS`.*

### Giải thích hàng đợi người duyệt (`05_review_queue.csv`):
- **Cơ chế xếp hạng**: Hàng đợi tính điểm ưu tiên dựa trên trọng số nguy cơ (`review.weights`). Ảnh `img_0020` đứng đầu danh sách (11.524 điểm) vì kết hợp nhiều nguy cơ: vừa bị máy xoá dòng sai ID 93 (`FIXED_DROP_LINE`), vừa có cảnh báo thiếu nhãn (`POSSIBLE_MISSING`) và nghi ngờ nhầm lớp (`POSSIBLE_WRONG_CLASS`). Xếp ngay sau là 6 ảnh hoàn toàn chưa có file nhãn (`NEEDS_LABEL`, trọng số 10.0 điểm).
- **Hiệu quả ngân sách 80 ảnh**: Với 80 ảnh được duyệt mô phỏng, người đã giải quyết 100% 6 ca thiếu nhãn nghiêm trọng và xử lý toàn bộ các ca xung đột nhãn nặng nhất ở đầu hàng đợi. Tuy nhiên, tổng hàng đợi có tới 125 ảnh; 45 ảnh còn lại nằm ngoài ngân sách duyệt (trong đó có 38 ảnh mang cảnh báo nhẹ) khiến tỉ lệ cảnh báo chưa duyệt dừng ở mức 18.72%.

---

## 3. Calibration (2 ngưỡng)

| Tham số | Khởi đầu | Đã chọn | Precision / Recall (trước → sau) | Lý do (đánh đổi) |
|---|---|---|---|---|
| `duplicates.phash_dist` | 2 | **8** | NEAR: 1.00 / 0.50 → 1.00 / 0.67 | Tại khoảng cách 2, máy bỏ sót 50% ảnh near-duplicate; nâng lên 8 giúp bắt thêm các ảnh bị nén/thu nhỏ nhẹ mà Precision vẫn giữ tuyệt đối 1.00 (không xoá nhầm ảnh sạch). Dù mức 16 đạt Recall 0.83 trên calib nhưng quá lỏng, dễ xoá nhầm trên ảnh đường phố thật. |
| `second_opinion.conf` | 0.25 | **0.60** | MISSING: 0.50 / 1.00 → 0.57 / 1.00<br>WRONG_CLASS: 0.56 / 0.83 → 0.62 / 0.83 | Ngưỡng 0.25 quá thấp khiến Precision chỉ đạt 50% (50% cảnh báo giả), làm phình to hàng đợi lên 145 ảnh. Nâng lên 0.60 giúp tăng Precision, giảm cảnh báo ảo từ 273 xuống 153 cảnh báo, mà vẫn giữ trọn vẹn Recall = 1.00 cho lỗi thiếu nhãn. |

### Một chỗ calibration có thể đánh lừa bạn:
Tập calibration chỉ có 39 ảnh dựng sẵn với các lỗi nhân tạo rõ ràng. Trên tập calib, `phash_dist = 16` cho F1 cao nhất (0.91), nhưng trên tập raw thật gồm nhiều khung hình camera xe cố định góc nhìn, khoảng cách 16 quá lớn sẽ coi các xe khác nhau di chuyển cùng vị trí góc đường là "ảnh trùng" và xoá nhầm dữ liệu huấn luyện quý giá (False Positive trong thực tế). Ngoài ra, calib không có ca `LEAK_TEST` và phân bố nhầm lớp chủ yếu là person $\rightarrow$ car, khác với thực tế raw hay nhầm giữa car/truck/bus.

---

## 4. Cửa chặn và điều pipeline KHÔNG bắt được

### (a) Chứng minh cửa chặn (Gate) hoạt động chính xác:
Khi thực hiện thí nghiệm không có người duyệt bằng lệnh:
```bash
python -m pipeline.run --budget 0 --reports work/rep_nb --export-dir work/exp_nb
```
Kết quả: 6 ảnh thiếu nhãn (`MISSING_LABEL_FILE`) không được annotator gán bù, do đó bước kiểm tra vòng 3 phát hiện vẫn còn nguyên 6 lỗi bắt buộc. Cửa chặn gate lập tức kết luận **REWORK**, tiến trình dừng với mã thoát **20**, và **hoàn toàn từ chối xuất bản dataset** sang thư mục đích. Điều này chứng minh cửa chặn hoạt động nghiêm ngặt, không cho phép lọt dữ liệu bẩn.

### (b) Ít nhất 2 điểm mù đã biết của pipeline:
1. **Bounding box lỏng nhẹ hoặc lệch nhẹ trong khoảng chấp nhận**: Nếu box của người gán có IoU với model checker nằm trong khoảng $[0.5, 0.7]$, hệ thống coi đây là khớp hợp lệ (`iou_match = 0.5`), bỏ qua và không kích hoạt `POSSIBLE_LOOSE_BOX` (ngưỡng loose quy định $< 0.5$).
2. **Gán nhầm giữa 2 lớp tương đồng mà model checker cũng không tự tin**: Ví dụ phân biệt giữa xe tải nhỏ (truck) và xe buýt nhỏ (bus); nếu model checker dự đoán với độ tin cậy thấp ($conf < 0.60$), cảnh báo nhầm lớp sẽ bị bỏ qua và không lọt vào hàng đợi duyệt.
3. **Ảnh trùng lặp bị crop quá mạnh (> 50%) hoặc đổi góc quay**: Khoảng cách Hamming của perceptual hash vượt quá 8, thuật toán băm ảnh không thể phát hiện được sự trùng lặp này.

---

## 5. Train: raw vs clean (tùy chọn, chấm riêng)

Chưa chạy: Môi trường máy tính cục bộ hiện tại không trang bị GPU hỗ trợ huấn luyện mạng nơ-ron sâu YOLO. Bộ dữ liệu sau làm sạch đã được đóng gói chuẩn quy cách tại `submission/export/clean_v1/` và sẵn sàng đồng bộ lên Google Colab để chạy so sánh theo notebook `notebooks/day09_train_compare.ipynb` khi có nhu cầu.

---

## 6. Quyết định và ghi chú AI

### (a) Quyết định cuối cùng:
Kết luận hiện tại là **HOLD**.
- **Điều kiện để chuyển sang RELEASE**:
  1. Tăng ngân sách người duyệt từ 80 lên tối thiểu **125 ảnh** để đội ngũ annotator xử lý dứt điểm 38 ảnh còn cảnh báo nghi ngờ; HOẶC
  2. QA Lead mở 38 ảnh này trong CVAT, rà soát nhanh và xác nhận các cảnh báo của `second_opinion` là báo động giả (False Alarm) do model checker phán đoán sai ngữ cảnh.

### (b) Ghi chú sử dụng AI hỗ trợ:
- **Prompt chính**: Dựa trên docstring và mô tả kiểm thử TDD trong các module `label_format.py`, `gate.py`, `autofix.py`, `second_opinion.py` để sinh khung thuật toán so khớp hình học và điều kiện lọc.
- **Cách kiểm tra code AI**: Chạy bộ unit test 79 ca kiểm thử liên tục; tự viết thêm các ca kiểm tra biên (ảnh hỏng bytes, dòng chứa giá trị `nan`, toạ độ âm, box tràn viền).
- **Một lần AI đề xuất sai**: Ban đầu trong `autofix.py`, AI đề xuất xoá từng dòng trực tiếp trong vòng lặp đọc file, dẫn đến việc làm xô lệch số thứ tự dòng (`lineno`) của các lỗi xuất hiện phía sau trong cùng một file nhãn; sau đó mã nguồn đã được sửa lại theo cơ chế gom nhóm theo file và đọc/ghi lại toàn bộ file một lần duy nhất.
