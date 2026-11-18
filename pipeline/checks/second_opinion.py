"""CHECK 6 — Ý kiến thứ hai: so nhãn với một model LỚN HƠN (yolo26l).   ★★★ (khó nhất, đáng điểm nhất)

Test:  pytest tests/test_second_opinion.py -q

Máy kiểm quy tắc, người kiểm ý nghĩa (slide). Các lỗi như thiếu nhãn / gán nhầm lớp hợp lệ / box lỏng
KHÔNG bắt được bằng quy tắc cú pháp. Ta nhờ một model mạnh hơn "nhìn lại" và CHỈ CẢNH BÁO (model cũng có thể sai):
những ảnh bị cờ sẽ vào hàng đợi cho NGƯỜI duyệt.

`preds[stem]` = list `[id_lớp, conf, cx, cy, w, h]` của model (lấy qua `get_preds(ds, cfg, "checker")` nếu preds=None).
`L = ds.valid_boxes(stem)` = list `(id_lớp, cx, cy, w, h)` của nhãn (đã bỏ dòng hỏng).
Ngưỡng ở `cfg["second_opinion"]`: conf, min_area_px, fp_conf, iou_missing, iou_match, iou_loose.
"""
from ..common import WARN, Issue, iou_xywh, parse_yolo_line
from ..model_cache import get_preds


def run(ds, cfg, preds=None):
    if preds is None:
        preds = get_preds(ds, cfg, "checker")
    if preds is None:
        return []

    so_cfg = cfg.get("second_opinion", {})
    conf_thresh = so_cfg.get("conf", 0.25)
    min_area_px = so_cfg.get("min_area_px", 600)
    fp_conf = so_cfg.get("fp_conf", 0.1)
    iou_missing = so_cfg.get("iou_missing", 0.3)
    iou_match = so_cfg.get("iou_match", 0.5)
    iou_loose = so_cfg.get("iou_loose", 0.5)

    issues = []

    for img_p in ds.image_files():
        stem = img_p.stem
        if stem not in preds:
            continue

        raw_label_lines = ds.read_label_lines(stem)
        if raw_label_lines is None:
            continue

        # Parse valid labels with line numbers
        valid_labels = []
        for lineno, text in raw_label_lines:
            try:
                b = parse_yolo_line(text)
            except ValueError:
                continue
            if 0 <= b[0] < len(ds.classes):
                valid_labels.append((lineno, b))

        img_sz = ds.image_size(stem)
        W, H = img_sz if img_sz else (1, 1)

        raw_preds = preds.get(stem, [])

        # Predictions for second-opinion checks (conf >= conf_thresh and area >= min_area_px)
        # Keep original prediction order
        pred_issues = []
        for p in raw_preds:
            p_cls, p_conf, p_cx, p_cy, p_w, p_h = p
            area_px = (p_w * W) * (p_h * H)
            if p_conf < conf_thresh or area_px < min_area_px:
                continue

            p_box = (p_cx, p_cy, p_w, p_h)

            # Find candidates with iou >= iou_missing
            same_class_cands = []
            diff_class_cands = []

            for lineno, (l_cls, l_cx, l_cy, l_w, l_h) in valid_labels:
                iou = iou_xywh(p_box, (l_cx, l_cy, l_w, l_h))
                if iou >= iou_missing:
                    if l_cls == p_cls:
                        same_class_cands.append(iou)
                    else:
                        diff_class_cands.append(iou)

            # (1) Không có candidates nào -> POSSIBLE_MISSING
            if not same_class_cands and not diff_class_cands:
                pred_issues.append(Issue(
                    "second_opinion", WARN, "POSSIBLE_MISSING", stem,
                    f"model dự đoán lớp {p_cls} (conf={p_conf:.2f}) nhưng nhãn thiếu",
                    line=None, extra={"conf": p_conf, "cls": p_cls}
                ))
            # (2) Có candidates cùng lớp
            elif same_class_cands:
                best_same_iou = max(same_class_cands)
                if best_same_iou < iou_loose:
                    pred_issues.append(Issue(
                        "second_opinion", WARN, "POSSIBLE_LOOSE_BOX", stem,
                        f"box nhãn cùng lớp nhưng lệch/lỏng (IoU={best_same_iou:.2f} < {iou_loose})",
                        line=None, extra={"conf": p_conf, "iou": best_same_iou}
                    ))
                # Ngược lại best_same_iou >= iou_loose: nhãn chuẩn, không cờ
            # (3) Không có candidates cùng lớp, chỉ có khác lớp
            else:
                best_diff_iou = max(diff_class_cands)
                if best_diff_iou >= iou_match:
                    pred_issues.append(Issue(
                        "second_opinion", WARN, "POSSIBLE_WRONG_CLASS", stem,
                        f"nghi ngờ gán nhầm lớp: model dự đoán lớp {p_cls} khớp box (IoU={best_diff_iou:.2f})",
                        line=None, extra={"conf": p_conf, "iou": best_diff_iou}
                    ))
                # nếu best_diff_iou trong [iou_missing, iou_match) -> không cờ

        # False positive checks for label lines
        # Dùng mọi dự đoán có conf >= fp_conf (không lọc min_area_px)
        fp_preds = [
            (p[0], p[2], p[3], p[4], p[5])
            for p in raw_preds
            if p[1] >= fp_conf
        ]

        fp_issues = []
        for lineno, (l_cls, l_cx, l_cy, l_w, l_h) in valid_labels:
            l_box = (l_cx, l_cy, l_w, l_h)
            max_iou = 0.0
            for fp_p in fp_preds:
                iou = iou_xywh(l_box, (fp_p[1], fp_p[2], fp_p[3], fp_p[4]))
                if iou > max_iou:
                    max_iou = iou

            if max_iou < iou_missing:
                fp_issues.append(Issue(
                    "second_opinion", WARN, "POSSIBLE_FALSE_POS", stem,
                    f"box nhãn không khớp dự đoán nào của model (max IoU={max_iou:.2f} < {iou_missing})",
                    line=lineno, extra={"max_iou": max_iou}
                ))

        issues.extend(pred_issues)
        issues.extend(fp_issues)

    return issues
