"""CHECK 2 — Dòng nhãn YOLO: sai định dạng, ID lớp lạ, box tràn ảnh, box rỗng, box lặp.   (Script 2 trong slide)   ★★

Test:  pytest tests/test_label_format.py -q

Mỗi dòng nhãn: `id cx cy w h` (5 số, toạ độ 0–1). Trả về list[Issue]; `Issue.line` = số dòng (đếm từ 1).

| code             | severity | khi nào                                                                  |
|------------------|----------|--------------------------------------------------------------------------|
| BAD_FORMAT       | ERROR    | không đúng 5 cột số (dùng `parse_yolo_line`, bắt `ValueError`)           |
| BAD_CLASS_ID     | ERROR    | id lớp ngoài 0..len(ds.classes)-1                                        |
| BOX_ZERO         | ERROR    | w <= 0 hoặc h <= 0                                                       |
| BOX_OUT_OF_IMAGE | ERROR    | mép box vượt [0,1] quá `cfg["label_format"]["overflow_tol"]`; extra={"overflow": mức tràn} |
| DUP_BOX          | ERROR    | cùng lớp với một dòng TRƯỚC ĐÓ và IoU > `dup_box_iou`; báo ở dòng SAU    |
| BOX_TINY         | WARN     | cạnh ngắn của box (px) < `min_box_px`  (cần `ds.image_size(stem)`)       |
| BOX_HUGE         | WARN     | w*h > `max_box_frac`                                                     |
"""
from ..common import ERROR, WARN, Issue, iou_xywh, parse_yolo_line


def run(ds, cfg):
    issues = []
    cfg_lf = cfg.get("label_format", {})
    overflow_tol = cfg_lf.get("overflow_tol", 0.002)
    min_box_px = cfg_lf.get("min_box_px", 12)
    max_box_frac = cfg_lf.get("max_box_frac", 0.95)
    dup_box_iou = cfg_lf.get("dup_box_iou", 0.9)
    num_classes = len(ds.classes)

    for p in ds.label_files():
        stem = p.stem
        lines = ds.read_label_lines(stem)
        if lines is None:
            continue
        valid_prev_boxes = []
        img_sz = ds.image_size(stem)

        for lineno, text in lines:
            try:
                c, x, y, w, h = parse_yolo_line(text)
            except ValueError:
                issues.append(Issue("label_format", ERROR, "BAD_FORMAT", stem, "định dạng không đúng 5 cột số", line=lineno))
                continue

            if c < 0 or c >= num_classes:
                issues.append(Issue("label_format", ERROR, "BAD_CLASS_ID", stem, f"id lớp {c} không hợp lệ", line=lineno))
                continue

            if w <= 0 or h <= 0:
                issues.append(Issue("label_format", ERROR, "BOX_ZERO", stem, f"kích thước w={w}, h={h} <= 0", line=lineno))
                continue

            # Geometry checks
            left = x - w / 2.0
            right = x + w / 2.0
            top = y - h / 2.0
            bottom = y + h / 2.0
            over = max(0.0, -left, -top, right - 1.0, bottom - 1.0)
            if over > overflow_tol:
                issues.append(Issue("label_format", ERROR, "BOX_OUT_OF_IMAGE", stem, f"box tràn ảnh {over:.4f}", line=lineno, extra={"overflow": over}))

            # DUP_BOX
            for prev_c, prev_box in valid_prev_boxes:
                if prev_c == c and iou_xywh((x, y, w, h), prev_box) > dup_box_iou:
                    issues.append(Issue("label_format", ERROR, "DUP_BOX", stem, "trùng lặp với box trước đó", line=lineno))
                    break
            valid_prev_boxes.append((c, (x, y, w, h)))

            # BOX_TINY (warning)
            if img_sz:
                if min(w * img_sz[0], h * img_sz[1]) < min_box_px:
                    issues.append(Issue("label_format", WARN, "BOX_TINY", stem, f"box quá nhỏ (< {min_box_px}px)", line=lineno))

            # BOX_HUGE (warning)
            if w * h > max_box_frac:
                issues.append(Issue("label_format", WARN, "BOX_HUGE", stem, f"box chiếm > {max_box_frac*100:.0f}% ảnh", line=lineno))

    return issues
