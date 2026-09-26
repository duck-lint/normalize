"""Focused invariants for recovering crop geometry from the PDF objects."""
from __future__ import annotations

import unittest

from run_forensics import inspect_all


class TransformForensicsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.pages = inspect_all()["pages"]
        cls.by_key = {(page["fixture_id"], page["side"]): page for page in cls.pages}

    def test_all_crop_pdfs_share_the_source_jpeg_bytes(self) -> None:
        self.assertEqual(len(self.pages), 12)
        for page in self.pages:
            self.assertTrue(page["embedded_image_bytes_identical"])
            self.assertEqual(page["source_image"]["image_sha256"], page["crop_image"]["image_sha256"])
            self.assertEqual(page["source_image"]["image_width_px"], 2550)
            self.assertEqual(page["source_image"]["image_height_px"], 3300)

    def test_direct_image_ctm_and_corner_inverse_round_trip(self) -> None:
        for page in self.pages:
            self.assertEqual(page["source_image"]["form_xobjects"], [])
            self.assertEqual(page["crop_image"]["form_xobjects"], [])
            self.assertEqual(page["source_image"]["operators"]["Do_resource_names"], ["Im0"])
            self.assertEqual(page["crop_image"]["operators"]["Do_resource_names"], ["Im0"])
            self.assertEqual(page["source_image"]["operators"]["clipping_operators"], [])
            self.assertEqual(page["crop_image"]["operators"]["clipping_operators"], [])
            error = page["inverse_crop_ctm"]["cropbox_corner_roundtrip_max_error_pt"]
            self.assertLess(error, 1e-8)
            # Independently compare direct PDF cm corner mappings with the
            # rendered placement matrix reported by PyMuPDF.
            for image_key in ("source_image", "crop_image"):
                self.assertLess(page[image_key]["image_corner_render_matrix_max_difference_pt"], 1e-4)

    def test_rotation_difference_enters_in_crop_page_cm(self) -> None:
        for fixture_id, expected in (
            ("relativity_pdf10_pp26-27", 0.986223),
            ("relativity_pdf23_pp52-53", 0.223811),
        ):
            for side in ("left", "right"):
                page = self.by_key[(fixture_id, side)]
                self.assertFalse(page["inverse_crop_ctm"]["source_and_crop_image_ctm_identical"])
                self.assertAlmostEqual(
                    page["source_spread_to_crop_reference_rotation_degrees"], expected, places=5
                )
        for fixture_id in (
            "relativity_pdf17_pp40-41",
            "stella_maris_pdf03_session-I",
            "stella_maris_pdf06_dense-dialogue",
        ):
            for side in ("left", "right"):
                page = self.by_key[(fixture_id, side)]
                self.assertTrue(page["inverse_crop_ctm"]["source_and_crop_image_ctm_identical"])
                polygon = page["inverse_crop_ctm"]["original_source_page_local_crop_polygon_at_144dpi_px_order_tl_tr_br_bl"]
                bounds = page["inverse_crop_ctm"]["original_source_page_local_crop_bounds_at_144dpi_px"]
                self.assertAlmostEqual(polygon[0][0], bounds[0], places=7)
                self.assertAlmostEqual(polygon[0][1], bounds[1], places=7)

    def test_boundary_shape_is_not_silently_replaced_with_its_bbox(self) -> None:
        for fixture_id in ("relativity_pdf10_pp26-27", "relativity_pdf23_pp52-53"):
            for side in ("left", "right"):
                page = self.by_key[(fixture_id, side)]
                edge_delta = page["inverse_crop_ctm"]["production_raster_edge_deviations_px"]
                self.assertGreater(max(edge_delta.values()), 2.0)
        for fixture_id in ("stella_maris_pdf18_session-II_p35",):
            for side in ("left", "right"):
                page = self.by_key[(fixture_id, side)]
                edge_delta = page["inverse_crop_ctm"]["production_raster_edge_deviations_px"]
                self.assertLess(max(edge_delta.values()), 0.3)


if __name__ == "__main__":
    unittest.main()
