import tempfile
import time
import unittest
from datetime import datetime
from pathlib import Path

from file_renamer import FolderRenamer, matches_extension, normalize_extensions, render_pattern


class PatternTests(unittest.TestCase):
    def test_normalize_extensions(self):
        self.assertEqual(normalize_extensions("png, .TIF pdf"), {".png", ".tif", ".pdf"})

    def test_extension_filter_is_case_insensitive_and_supports_all_files(self):
        self.assertTrue(matches_extension(Path("scan.PDF"), {".pdf"}, False))
        self.assertFalse(matches_extension(Path("scan.jpg"), {".pdf"}, False))
        self.assertTrue(matches_extension(Path("scan.anything"), set(), True))

    def test_pattern_file_information_tokens(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory) / "Inbox"
            folder.mkdir()
            source = folder / "anh mau.tif"
            source.write_bytes(b"1234")
            result = render_pattern(
                "<name>_<ext>_<parent>_<size>_<time:HH-mm-ss>",
                source,
                1,
                datetime(2026, 10, 27, 14, 5, 6),
            )
        self.assertEqual(result, "anh mau_tif_Inbox_4_14-05-06.tif")

    def test_render_pattern(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "anh mau.tif"
            result = render_pattern(
                "TaiLieu_<date:yyyy-MM-dd>_<Inc Nr:001>",
                source,
                7,
                datetime(2026, 10, 27, 14, 5),
            )
        self.assertEqual(result, "TaiLieu_2026-10-27_007.tif")

    def test_incrementing_number_width_and_start_value(self):
        source = Path("document.pdf")
        self.assertEqual(render_pattern("<Inc Nr:0001>", source, 12), "0012.pdf")
        self.assertEqual(render_pattern("<Inc Nr:00001>", source, 12), "00012.pdf")

    def test_reset_sequence_uses_selected_start_number(self):
        renamer = FolderRenamer(lambda _: None, lambda _: None)
        renamer._starting_number = 2026
        renamer._number = 2030
        renamer.reset_sequence()
        self.assertEqual(renamer._number, 2026)

    def test_explicit_extension_is_preserved(self):
        source = Path("document.pdf")
        self.assertEqual(render_pattern("<name>_backup.txt", source, 1), "document_backup.txt")

    def test_same_file_is_not_processed_twice_after_rename(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            source = folder / "incoming.txt"
            source.write_text("data", encoding="utf-8")
            renamer = FolderRenamer(lambda _: None, lambda _: None)
            renamer.folder = folder
            renamer.pattern = "Renamed_<Inc Nr:001>"
            renamer._process(source)
            renamed = folder / "Renamed_001.txt"
            renamer._process(renamed)
            self.assertTrue(renamed.exists())
            self.assertFalse((folder / "Renamed_002.txt").exists())

    def test_reused_source_name_is_processed_as_a_new_file(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            renamer = FolderRenamer(lambda _: None, lambda _: None)
            renamer.start(folder, {".png"}, False, "Renamed_<Inc Nr:001>")
            try:
                first = folder / "1.png"
                first.write_bytes(b"first")
                first_target = folder / "Renamed_001.png"
                self.assertTrue(self._wait_for(first_target), "File đầu tiên chưa được đổi tên")

                second = folder / "1.png"
                second.write_bytes(b"second")
                second_target = folder / "Renamed_002.png"
                self.assertTrue(self._wait_for(second_target), "File dùng lại tên cũ chưa được đổi tên")
            finally:
                renamer.stop()

    @staticmethod
    def _wait_for(path: Path, timeout: float = 5.0) -> bool:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if path.exists():
                return True
            time.sleep(0.1)
        return False

    def test_existing_file_is_ignored_and_wrong_extension_is_skipped(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            existing = folder / "existing.png"
            existing.write_bytes(b"existing")
            renamer = FolderRenamer(lambda _: None, lambda _: None)
            renamer.start(folder, {".png"}, False, "Renamed_<Inc Nr:001>")
            try:
                self.assertTrue(existing.exists())
                (folder / "ignored.jpg").write_bytes(b"ignored")
                new_file = folder / "new.png"
                new_file.write_bytes(b"new")
                self.assertTrue(self._wait_for(folder / "Renamed_001.png"))
                self.assertTrue((folder / "ignored.jpg").exists())
                self.assertTrue(existing.exists())
            finally:
                renamer.stop()

    def test_collision_reports_error_without_overwriting(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            source = folder / "incoming.png"
            target = folder / "Renamed_001.png"
            source.write_bytes(b"source")
            target.write_bytes(b"keep")
            errors: list[str] = []
            renamer = FolderRenamer(errors.append, lambda _: None)
            renamer.folder = folder
            renamer.pattern = "Renamed_<Inc Nr:001>"
            renamer._process(source)
            self.assertTrue(source.exists())
            self.assertEqual(target.read_bytes(), b"keep")
            self.assertEqual(len(errors), 1)

    def test_start_invalid_folder_is_rejected(self):
        renamer = FolderRenamer(lambda _: None, lambda _: None)
        with self.assertRaises(ValueError):
            renamer.start(Path("this-folder-does-not-exist"), {".png"}, False, "<name>")

    def test_start_twice_is_rejected_and_stop_is_safe(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            renamer = FolderRenamer(lambda _: None, lambda _: None)
            renamer.stop()
            renamer.start(folder, {".png"}, False, "<name>")
            try:
                with self.assertRaises(RuntimeError):
                    renamer.start(folder, {".png"}, False, "<name>")
            finally:
                renamer.stop()


if __name__ == "__main__":
    unittest.main()
