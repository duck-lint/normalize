"""Recover manual page-crop boundaries from PDF content/image transforms.

This is read-only research tooling. It never copies or writes source/crop PDFs.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
from pathlib import Path
from typing import Any

import pymupdf

ROOT = Path(__file__).resolve().parents[2]
DPI = 144
SPLIT_X_PX = 792
FIXTURES = {
    "relativity_pdf10_pp26-27": ("einstein", "Einstein, Albert - Relativity 10"),
    "relativity_pdf17_pp40-41": ("einstein", "Einstein, Albert - Relativity 17"),
    "relativity_pdf23_pp52-53": ("einstein", "Einstein, Albert - Relativity 23"),
    "stella_maris_pdf03_session-I": ("mccarthy", "McCarthy, Cormac - Stella Maris.pt2 3"),
    "stella_maris_pdf06_dense-dialogue": ("mccarthy", "McCarthy, Cormac - Stella Maris.pt2 6"),
    "stella_maris_pdf18_session-II_p35": ("mccarthy", "McCarthy, Cormac - Stella Maris.pt2 18"),
}
BOX_KEYS = ("MediaBox", "CropBox", "BleedBox", "TrimBox", "ArtBox", "Rotate", "UserUnit")
_CM_RE = re.compile(
    r"([-+]?(?:\d+(?:\.\d*)?|\.\d+))\s+"
    r"([-+]?(?:\d+(?:\.\d*)?|\.\d+))\s+"
    r"([-+]?(?:\d+(?:\.\d*)?|\.\d+))\s+"
    r"([-+]?(?:\d+(?:\.\d*)?|\.\d+))\s+"
    r"([-+]?(?:\d+(?:\.\d*)?|\.\d+))\s+"
    r"([-+]?(?:\d+(?:\.\d*)?|\.\d+))\s+cm\b"
)
_DO_RE = re.compile(r"/(\w+)\s+Do\b")


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def apply_pdf_matrix(matrix: tuple[float, ...], x: float, y: float) -> tuple[float, float]:
    """Apply PDF's [a b c d e f] convention to a point."""
    a, b, c, d, e, f = matrix
    return a * x + c * y + e, b * x + d * y + f


def invert_pdf_matrix_point(
    matrix: tuple[float, ...], x: float, y: float
) -> tuple[float, float]:
    """Invert a non-singular PDF affine matrix at a page-space point."""
    a, b, c, d, e, f = matrix
    determinant = a * d - b * c
    if abs(determinant) < 1e-12:
        raise ValueError("image placement CTM is singular")
    dx, dy = x - e, y - f
    return (d * dx - c * dy) / determinant, (-b * dx + a * dy) / determinant


def affine_homogeneous(matrix: tuple[float, ...]) -> list[list[float]]:
    a, b, c, d, e, f = matrix
    return [[a, c, e], [b, d, f], [0.0, 0.0, 1.0]]


def multiply_3x3(left: list[list[float]], right: list[list[float]]) -> list[list[float]]:
    return [
        [sum(left[row][k] * right[k][column] for k in range(3)) for column in range(3)]
        for row in range(3)
    ]


def invert_3x3_affine(matrix: list[list[float]]) -> list[list[float]]:
    a, c, e = matrix[0]
    b, d, f = matrix[1]
    determinant = a * d - b * c
    if abs(determinant) < 1e-12:
        raise ValueError("image-to-raster affine matrix is singular")
    return [
        [d / determinant, -c / determinant, (c * f - d * e) / determinant],
        [-b / determinant, a / determinant, (b * e - a * f) / determinant],
        [0.0, 0.0, 1.0],
    ]


def image_pixel_to_page(
    matrix: tuple[float, ...], width: int, height: int, x_px: float, y_px: float
) -> tuple[float, float]:
    """Map top-left-origin JPEG pixel coordinates to PDF user space.

    PDF image space has its origin at bottom left. A source pixel row y is
    therefore mapped to normalized image coordinate v = 1 - y / height.
    """
    u, v = x_px / width, 1.0 - y_px / height
    return apply_pdf_matrix(matrix, u, v)


def page_to_image_pixel(
    matrix: tuple[float, ...], width: int, height: int, x_page: float, y_page: float
) -> tuple[float, float]:
    u, v = invert_pdf_matrix_point(matrix, x_page, y_page)
    return u * width, (1.0 - v) * height


def polygon_edge_deviations(points_tl_tr_br_bl: list[tuple[float, float]]) -> dict[str, float]:
    tl, tr, br, bl = points_tl_tr_br_bl
    return {
        "top_y_delta_px": abs(tr[1] - tl[1]),
        "right_x_delta_px": abs(br[0] - tr[0]),
        "bottom_y_delta_px": abs(br[1] - bl[1]),
        "left_x_delta_px": abs(bl[0] - tl[0]),
    }


def polygon_bounds(points: list[tuple[float, float]]) -> list[float]:
    return [
        min(point[0] for point in points),
        min(point[1] for point in points),
        max(point[0] for point in points),
        max(point[1] for point in points),
    ]


def _parse_pdf_rectangle(raw_value: str) -> tuple[float, float, float, float]:
    values = [float(value) for value in re.findall(r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)", raw_value)]
    if len(values) != 4:
        raise ValueError(f"expected four PDF rectangle coordinates, got {raw_value!r}")
    return tuple(values)  # type: ignore[return-value]


def _raw_page_record(doc: pymupdf.Document, page: pymupdf.Page) -> dict[str, Any]:
    xref = page.xref
    entries = {}
    for key in BOX_KEYS:
        state, value = doc.xref_get_key(xref, key)
        entries[key] = {"state": state, "raw_value": value}
    return {
        "page_xref": xref,
        "page_object": doc.xref_object(xref, compressed=False),
        "document_metadata": doc.metadata,
        "dictionary_entries": entries,
        "resolved_boxes_pt": {
            "media": list(page.mediabox),
            "crop": list(page.cropbox),
            "bleed": list(page.bleedbox),
            "trim": list(page.trimbox),
            "art": list(page.artbox),
            "display_rect": list(page.rect),
            "rotation_degrees": int(page.rotation),
        },
        "page_transformation_matrix": list(page.transformation_matrix),
        "page_rotation_matrix": list(page.rotation_matrix),
    }


def _page_image_record(doc: pymupdf.Document, page: pymupdf.Page) -> dict[str, Any]:
    contents = page.get_contents()
    streams = [doc.xref_stream(xref) or b"" for xref in contents]
    content_bytes = b"\n".join(streams)
    content_text = content_bytes.decode("latin1")
    matrices = [tuple(float(value) for value in groups) for groups in _CM_RE.findall(content_text)]
    names = _DO_RE.findall(content_text)
    images = page.get_images(full=True)
    forms = page.get_xobjects()
    clips = re.findall(r"(?:^|\s)(?:W\*?)(?=\s|$)", content_text)
    if len(matrices) != 1 or len(names) != 1 or len(images) != 1:
        raise ValueError(
            f"expected one direct image placement; contents={contents}, matrices={matrices}, "
            f"Do={names}, images={images}"
        )
    image = next((row for row in images if row[7] == names[0]), None)
    if image is None or forms or clips:
        raise ValueError(f"unexpected Form/clipping/resource structure: image={image}, forms={forms}, clips={clips}")
    image_xref = image[0]
    image_object = doc.xref_object(image_xref, compressed=False)
    extracted = doc.extract_image(image_xref)
    image_matrix = matrices[0]
    image_width, image_height = extracted["width"], extracted["height"]
    normalized_top_left_corners = [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)]
    pdf_pixel_corners = [(0.0, 0.0), (float(image_width), 0.0),
                         (float(image_width), float(image_height)), (0.0, float(image_height))]
    raw_visible_box = doc.xref_get_key(page.xref, "CropBox")[1]
    visible_box = _parse_pdf_rectangle(raw_visible_box) if raw_visible_box else tuple(page.mediabox)
    visible_x0, visible_y0, visible_x1, visible_y1 = visible_box
    direct_unrotated_corners = []
    for x_px, y_px in pdf_pixel_corners:
        x_pdf, y_pdf = image_pixel_to_page(image_matrix, image_width, image_height, x_px, y_px)
        direct_unrotated_corners.append((x_pdf - visible_x0, visible_y1 - y_pdf))
    placements = page.get_image_rects(image, transform=True)
    if len(placements) != 1:
        raise ValueError(f"expected one rendered image placement, got {placements}")
    rendered_rect, rendered_matrix = placements[0]
    rendered_unrotated_corners = [
        (rendered_matrix.a * x + rendered_matrix.c * y + rendered_matrix.e,
         rendered_matrix.b * x + rendered_matrix.d * y + rendered_matrix.f)
        for x, y in normalized_top_left_corners
    ]
    render_corner_error_pt = max(
        math.dist(expected, actual)
        for expected, actual in zip(direct_unrotated_corners, rendered_unrotated_corners)
    )
    return {
        "content_stream_xrefs": contents,
        "content_streams_latin1": [stream.decode("latin1") for stream in streams],
        "content_stream_combined_latin1": content_text,
        "operators": {
            "cm_matrices": [list(matrix) for matrix in matrices],
            "Do_resource_names": names,
            "q_count": len(re.findall(r"(?:^|\s)q(?=\s|$)", content_text)),
            "Q_count": len(re.findall(r"(?:^|\s)Q(?=\s|$)", content_text)),
            "clipping_operators": clips,
        },
        "form_xobjects": forms,
        "image_resource_tuple": list(image),
        "image_xref": image_xref,
        "image_object": image_object,
        "image_width_px": extracted["width"],
        "image_height_px": extracted["height"],
        "image_extension": extracted["ext"],
        "image_sha256": sha256(extracted["image"]),
        "image_color_space": image[5],
        "image_bits_per_component": int(image[4]),
        "image_filter": image[8],
        "image_to_page_user_space_pdf_cm": list(matrices[0]),
        "pymupdf_rendered_image_rect_unrotated_pt": list(rendered_rect),
        "pymupdf_rendered_image_matrix_unrotated_pt": [rendered_matrix.a, rendered_matrix.b, rendered_matrix.c, rendered_matrix.d, rendered_matrix.e, rendered_matrix.f],
        "image_corner_render_matrix_max_difference_pt": render_corner_error_pt,
    }


def inspect_pair(fixture_id: str, author: str, stem: str, side: str) -> dict[str, Any]:
    suffix = "L" if side == "left" else "R"
    source_path = ROOT / "fixtures" / author / f"{stem}.pdf"
    crop_path = ROOT / "fixtures" / author / "crops" / f"{stem}-{suffix}.pdf"
    with pymupdf.open(source_path) as source_doc, pymupdf.open(crop_path) as crop_doc:
        source_page, crop_page = source_doc[0], crop_doc[0]
        source_page_record = _raw_page_record(source_doc, source_page)
        crop_page_record = _raw_page_record(crop_doc, crop_page)
        source_image = _page_image_record(source_doc, source_page)
        crop_image = _page_image_record(crop_doc, crop_page)
        width, height = source_image["image_width_px"], source_image["image_height_px"]
        if (width, height) != (crop_image["image_width_px"], crop_image["image_height_px"]):
            raise ValueError(f"embedded image dimensions differ in {crop_path}")
        if source_image["image_sha256"] != crop_image["image_sha256"]:
            raise ValueError(f"embedded JPEG bytes differ in {crop_path}")

        crop_box_top_left = crop_page.cropbox
        crop_media = crop_page.mediabox
        # PyMuPDF's page.cropbox is in unrotated top-left coordinates. The
        # content-stream CTM uses raw PDF user coordinates (bottom-left origin),
        # so convert it back before inversion; the raw /CropBox is recorded too.
        crop_box_pdf = _parse_pdf_rectangle(
            crop_doc.xref_get_key(crop_page.xref, "CropBox")[1]
        )
        cb_x0, cb_y0, cb_x1, cb_y1 = crop_box_pdf
        crop_box_pdf_corners = [
            [cb_x0, cb_y0],
            [cb_x1, cb_y0],
            [cb_x1, cb_y1],
            [cb_x0, cb_y1],
        ]
        crop_matrix = tuple(crop_image["image_to_page_user_space_pdf_cm"])
        source_matrix = tuple(source_image["image_to_page_user_space_pdf_cm"])
        crop_polygon_bl_br_tr_tl = [
            list(page_to_image_pixel(crop_matrix, width, height, x, y))
            for x, y in crop_box_pdf_corners
        ]
        crop_polygon_tl_tr_br_bl = [
            crop_polygon_bl_br_tr_tl[index] for index in (3, 2, 1, 0)
        ]
        roundtrip = [
            list(image_pixel_to_page(crop_matrix, width, height, x, y))
            for x, y in crop_polygon_bl_br_tr_tl
        ]
        roundtrip_error = max(
            math.dist(expected, actual)
            for expected, actual in zip(crop_box_pdf_corners, roundtrip)
        )

        # Carry the same source-image points through the original fixture's
        # image CTM and 90-degree page rotation into 144-DPI display pixels.
        source_media = source_page.mediabox
        production_polygon = []
        for x_image, y_image in crop_polygon_tl_tr_br_bl:
            x_pdf, y_pdf = image_pixel_to_page(source_matrix, width, height, x_image, y_image)
            # PyMuPDF first converts PDF bottom-left user coordinates to an
            # unrotated top-left frame, then /Rotate 90 maps display x to raw
            # PDF y and display y to raw PDF x (both relative to MediaBox).
            display_x_pt = y_pdf - source_media.y0
            display_y_pt = x_pdf - source_media.x0
            display_x_px = display_x_pt * DPI / 72
            display_y_px = display_y_pt * DPI / 72
            if side == "right":
                display_x_px -= SPLIT_X_PX
            production_polygon.append([display_x_px, display_y_px])

        deviations = polygon_edge_deviations(
            [(point[0], point[1]) for point in crop_polygon_tl_tr_br_bl]
        )
        # A 90-degree page rotation changes the corner order: image TL/TR/BR/BL
        # becomes displayed TR/BR/BL/TL. Reorder after mapping to the source
        # page's displayed raster, whose coordinates crop tooling uses.
        production_polygon = [production_polygon[index] for index in (3, 0, 1, 2)]
        production_deviations = polygon_edge_deviations(
            [(point[0], point[1]) for point in production_polygon]
        )
        bbox = polygon_bounds(crop_polygon_tl_tr_br_bl)
        prod_bbox = polygon_bounds([(p[0], p[1]) for p in production_polygon])
        # Earlier candidates were obtained by mapping CropBox bounds directly
        # into the original page's display coordinates, then making x local.
        factor = DPI / 72
        candidate = [
            (cb_y0 - source_media.y0) * factor,
            (cb_x0 - source_media.x0) * factor,
            (cb_y1 - source_media.y0) * factor,
            (cb_x1 - source_media.x0) * factor,
        ]
        if side == "right":
            candidate[0] -= SPLIT_X_PX
            candidate[2] -= SPLIT_X_PX

        source_affine = tuple(source_matrix)
        crop_affine = tuple(crop_matrix)
        scale = DPI / 72
        # Image-pixel to source spread raster at 144 DPI. The image-pixel
        # coordinates use top-left origin; PDF user-space points use bottom-left.
        source_pixel_to_pdf = [
            [source_affine[0] / width, -source_affine[2] / height, source_affine[2] + source_affine[4]],
            [source_affine[1] / width, -source_affine[3] / height, source_affine[3] + source_affine[5]],
            [0.0, 0.0, 1.0],
        ]
        source_pixel_to_spread = [
            [scale * source_pixel_to_pdf[1][0], scale * source_pixel_to_pdf[1][1], scale * (source_pixel_to_pdf[1][2] - source_page.mediabox.y0)],
            [scale * source_pixel_to_pdf[0][0], scale * source_pixel_to_pdf[0][1], scale * (source_pixel_to_pdf[0][2] - source_page.mediabox.x0)],
            [0.0, 0.0, 1.0],
        ]
        crop_pixel_to_page = [
            [scale * crop_affine[1] / width, -scale * crop_affine[3] / height, scale * (crop_affine[3] + crop_affine[5] - cb_y0)],
            [scale * crop_affine[0] / width, -scale * crop_affine[2] / height, scale * (crop_affine[2] + crop_affine[4] - cb_x0)],
            [0.0, 0.0, 1.0],
        ]
        source_to_crop_display = multiply_3x3(
            crop_pixel_to_page, invert_3x3_affine(source_pixel_to_spread)
        )
        raster_relative_rotation = math.degrees(
            math.atan2(source_to_crop_display[1][0], source_to_crop_display[0][0])
        )
        crop_pixmap = crop_page.get_pixmap(matrix=pymupdf.Matrix(scale, scale), alpha=False)
        source_pixmap = source_page.get_pixmap(matrix=pymupdf.Matrix(scale, scale), alpha=False)
        crop_display_corners = [
            [(y - cb_y0) * scale, (x - cb_x0) * scale]
            for x, y in crop_box_pdf_corners
        ]
        crop_display_dimensions = [crop_pixmap.width, crop_pixmap.height]
        # Report the matrix that carries a source-PDF point to its corresponding
        # crop-PDF point through their shared normalized image coordinate.
        # It is expressed in [a,b,c,d,e,f] PDF form.
        source_origin_in_crop = apply_pdf_matrix(
            crop_affine,
            *invert_pdf_matrix_point(source_affine, 0.0, 0.0),
        )
        source_x_in_crop = apply_pdf_matrix(
            crop_affine,
            *invert_pdf_matrix_point(source_affine, 1.0, 0.0),
        )
        source_y_in_crop = apply_pdf_matrix(
            crop_affine,
            *invert_pdf_matrix_point(source_affine, 0.0, 1.0),
        )
        relative_matrix = [
            source_x_in_crop[0] - source_origin_in_crop[0],
            source_x_in_crop[1] - source_origin_in_crop[1],
            source_y_in_crop[0] - source_origin_in_crop[0],
            source_y_in_crop[1] - source_origin_in_crop[1],
            source_origin_in_crop[0],
            source_origin_in_crop[1],
        ]
        relative_rotation = math.degrees(math.atan2(relative_matrix[1], relative_matrix[0]))
        same_ctm = max(abs(a - b) for a, b in zip(source_matrix, crop_matrix)) < 1e-5
        corners_image = [[0.0, 0.0], [float(width), 0.0], [float(width), float(height)], [0.0, float(height)]]
        source_image_corners_pdf = [
            list(image_pixel_to_page(source_matrix, width, height, x, y))
            for x, y in corners_image
        ]
        crop_image_corners_pdf = [
            list(image_pixel_to_page(crop_matrix, width, height, x, y))
            for x, y in corners_image
        ]

        return {
            "fixture_id": fixture_id,
            "side": side,
            "source_pdf": str(source_path.relative_to(ROOT)),
            "crop_pdf": str(crop_path.relative_to(ROOT)),
            "source_pdf_sha256": sha256(source_path.read_bytes()),
            "crop_pdf_sha256": sha256(crop_path.read_bytes()),
            "source_page": source_page_record,
            "crop_page": crop_page_record,
            "source_image": source_image,
            "crop_image": crop_image,
            "embedded_image_bytes_identical": True,
            "source_image_to_page_corner_positions_pdf_user_space": source_image_corners_pdf,
            "crop_image_to_page_corner_positions_pdf_user_space": crop_image_corners_pdf,
            "crop_visible_bounds_pdf_user_space": list(crop_box_pdf),
            "source_pdf_image_pixel_to_spread_raster_matrix_at_144dpi": source_pixel_to_spread,
            "crop_pdf_image_pixel_to_visible_raster_matrix_at_144dpi": crop_pixel_to_page,
            "source_spread_raster_to_crop_reference_raster_matrix": source_to_crop_display,
            "source_spread_to_crop_reference_rotation_degrees": raster_relative_rotation,
            "source_rendered_raster_dimensions_px": [source_pixmap.width, source_pixmap.height],
            "crop_reference_rendered_raster_dimensions_px": crop_display_dimensions,
            "crop_visible_corners_display_px_order_bl_br_tr_tl": crop_display_corners,
            "crop_visible_bounds_display_px_at_144dpi": candidate,
            "inverse_crop_ctm": {
                "matrix_convention": "PDF six-value [a,b,c,d,e,f], affine applied to normalized image coordinates",
                "source_image_crop_polygon_px_order_tl_tr_br_bl": crop_polygon_tl_tr_br_bl,
                "source_image_crop_polygon_bounds_px": bbox,
                "source_image_edge_deviations_px": deviations,
                "axis_aligned_in_source_image_pixels_within_0_5px": max(deviations.values()) <= 0.5,
                "crop_pdf_to_original_pdf_page_relative_matrix": relative_matrix,
                "crop_pdf_relative_rotation_degrees": relative_rotation,
                "source_and_crop_image_ctm_identical": same_ctm,
                "original_source_page_local_crop_polygon_at_144dpi_px_order_tl_tr_br_bl": production_polygon,
                "original_source_page_local_crop_bounds_at_144dpi_px": prod_bbox,
                "production_raster_edge_deviations_px": production_deviations,
                "cropbox_corner_roundtrip_max_error_pt": roundtrip_error,
            },
        }


def inspect_all() -> dict[str, Any]:
    pages = []
    for fixture_id, (author, stem) in FIXTURES.items():
        for side in ("left", "right"):
            pages.append(inspect_pair(fixture_id, author, stem, side))
    return {
        "schema": "page-crop-transform-forensics-v1",
        "method": {
            "authority": "PDF object/content-stream affine geometry; image-feature registration is not used for primary bounds",
            "production_dpi": DPI,
            "fixture_split_boundary_px": SPLIT_X_PX,
            "pixel_coordinates": "embedded JPEG pixels, top-left origin; image-space y is inverted into PDF's bottom-left normalized coordinates",
            "source_pixel_to_pdf_formula": "u=x/W; v=1-y/H; page=[a*u+c*v+e, b*u+d*v+f]",
            "crop_recovery": "Invert each crop PDF's direct image-placement CTM at all visible CropBox corners; identical XObject bytes identify the same JPEG sample coordinate system",
            "rotation_handling": "Apply source page /Rotate after carrying recovered image points through the original source PDF image CTM; reorder corners into display TL/TR/BR/BL after the 90-degree turn",
            "rounding": "No rounding in recovered evidence; production candidate values are shown at full precision",
        },
        "pages": pages,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path(__file__).with_name("results.json"))
    args = parser.parse_args()
    result = inspect_all()
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {len(result['pages'])} page-side records to {args.output}")


if __name__ == "__main__":
    main()
