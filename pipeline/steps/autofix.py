"""BƯỚC 2/4 — Sửa tự động những lỗi bắt buộc mà máy sửa được AN TOÀN.   ★★

Test:  pytest tests/test_autofix.py -q

`fix(ds, issues, cfg) -> list[dict]`: duyệt `issues` (chỉ lỗi severity ERROR), sửa thẳng vào thư mục `ds`,
và trả về danh sách thay đổi; mỗi phần tử có khoá: image, line, action, before, after
(đây chính là file `03_fixes.csv` — bằng chứng pipeline đã làm gì, người có thể kiểm lại).

| code lỗi                                       | cách sửa                                    | action           |
|------------------------------------------------|---------------------------------------------|------------------|
| BAD_FORMAT, BAD_CLASS_ID, BOX_ZERO, DUP_BOX    | xoá dòng đó khỏi file nhãn                  | "drop_line"      |
| BOX_OUT_OF_IMAGE                               | cắt box về trong [0,1] (giữ nguyên lớp)     | "clip_box"       |
| MISSING_LABEL_FILE                             | KHÔNG sửa file: ghi 1 dòng fix              | "needs_label"    |
| BAD_CLASS_NAME                                 | ghi lại `names` trong data.yaml             | "rename_classes" |
| DUP_IMAGE_*, LEAK_TEST, CORRUPT_IMAGE, BAD_SIZE| xoá ảnh + nhãn khỏi `ds`                    | "remove_image"   |
"""
from collections import defaultdict
import yaml

from ..common import ERROR, parse_yolo_line

REMOVE_IMAGE_CODES = {"LEAK_TEST", "CORRUPT_IMAGE", "BAD_SIZE"}
DROP_LINE_CODES = {"BAD_FORMAT", "BAD_CLASS_ID", "BOX_ZERO", "DUP_BOX"}


def fix(ds, issues, cfg):
    # Chỉ xử lý các lỗi bắt buộc (severity == ERROR)
    error_issues = [i for i in issues if i.severity == ERROR]
    fixes = []

    # 1. BAD_CLASS_NAME -> cập nhật data.yaml
    for i in error_issues:
        if i.code == "BAD_CLASS_NAME":
            yaml_path = ds.yaml_path
            d = {}
            if yaml_path.exists():
                d = yaml.safe_load(yaml_path.read_text(encoding="utf-8")) or {}
            before_val = str(d.get("names", ""))
            d["names"] = list(cfg["classes"])
            yaml_path.write_text(yaml.safe_dump(d, allow_unicode=True), encoding="utf-8")
            fixes.append({
                "image": "data.yaml",
                "line": None,
                "action": "rename_classes",
                "before": before_val,
                "after": str(cfg["classes"]),
            })
            break

    # 2. Xóa ảnh và nhãn (DUP_IMAGE_*, LEAK_TEST, CORRUPT_IMAGE, BAD_SIZE)
    removed_images = set()
    for i in error_issues:
        if i.code.startswith("DUP_IMAGE") or i.code in REMOVE_IMAGE_CODES:
            stem = i.image
            if stem in removed_images:
                continue
            removed_images.add(stem)

            # Xóa ảnh
            img_p = ds.image_path(stem)
            if img_p and img_p.exists():
                img_p.unlink()

            # Xóa nhãn
            lbl_p = ds.label_path(stem)
            if lbl_p and lbl_p.exists():
                lbl_p.unlink()

            if hasattr(ds, "_size_cache") and stem in ds._size_cache:
                del ds._size_cache[stem]

            fixes.append({
                "image": stem,
                "line": None,
                "action": "remove_image",
                "before": f"xóa ảnh/nhãn {stem}",
                "after": "(đã xóa)",
            })

    # 3. MISSING_LABEL_FILE -> ghi nhận chuyển người duyệt, không tạo file
    for i in error_issues:
        if i.code == "MISSING_LABEL_FILE":
            stem = i.image
            if stem in removed_images:
                continue
            fixes.append({
                "image": stem,
                "line": None,
                "action": "needs_label",
                "before": "(không có file)",
                "after": "chuyển người gán",
            })

    # 4. Sửa lỗi dòng trong file nhãn (drop_line, clip_box)
    file_issues = defaultdict(lambda: defaultdict(list))
    for i in error_issues:
        stem = i.image
        if stem in removed_images or i.line is None:
            continue
        if i.code in DROP_LINE_CODES or i.code == "BOX_OUT_OF_IMAGE":
            file_issues[stem][i.line].append(i)

    for stem in sorted(file_issues.keys()):
        lbl_p = ds.label_path(stem)
        if not lbl_p.exists():
            continue

        raw_lines = lbl_p.read_text(encoding="utf-8", errors="replace").splitlines()
        new_lines = []
        line_map = file_issues[stem]

        for lineno, original_text in enumerate(raw_lines, 1):
            if lineno not in line_map:
                new_lines.append(original_text)
                continue

            issues_on_line = line_map[lineno]
            codes = {iss.code for iss in issues_on_line}

            # Nếu có lỗi cần drop_line (kể cả khi đồng thời có BOX_OUT_OF_IMAGE, drop_line luôn thắng)
            if any(c in DROP_LINE_CODES for c in codes):
                fixes.append({
                    "image": stem,
                    "line": lineno,
                    "action": "drop_line",
                    "before": original_text,
                    "after": "(xoá dòng)",
                })
            elif "BOX_OUT_OF_IMAGE" in codes:
                try:
                    c, x, y, w, h = parse_yolo_line(original_text)
                    left = x - w / 2.0
                    right = x + w / 2.0
                    top = y - h / 2.0
                    bottom = y + h / 2.0

                    left_c = max(0.0, left)
                    right_c = min(1.0, right)
                    top_c = max(0.0, top)
                    bottom_c = min(1.0, bottom)

                    w_c = right_c - left_c
                    h_c = bottom_c - top_c

                    if w_c <= 0 or h_c <= 0:
                        fixes.append({
                            "image": stem,
                            "line": lineno,
                            "action": "drop_line",
                            "before": original_text,
                            "after": "(xoá dòng: box ngoài ảnh)",
                        })
                    else:
                        x_c = (left_c + right_c) / 2.0
                        y_c = (top_c + bottom_c) / 2.0
                        # Định dạng chuẩn số thực
                        new_line = f"{int(c)} {x_c:.6g} {y_c:.6g} {w_c:.6g} {h_c:.6g}"
                        fixes.append({
                            "image": stem,
                            "line": lineno,
                            "action": "clip_box",
                            "before": original_text,
                            "after": new_line,
                        })
                        new_lines.append(new_line)
                except ValueError:
                    fixes.append({
                        "image": stem,
                        "line": lineno,
                        "action": "drop_line",
                        "before": original_text,
                        "after": "(xoá dòng)",
                    })

        lbl_p.write_text("\n".join(new_lines) + ("\n" if new_lines else ""), encoding="utf-8")

    return fixes
