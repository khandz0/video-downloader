import unittest

import clip


class ParseTimestampTests(unittest.TestCase):
    def test_minutes_and_hours(self):
        self.assertEqual(clip.parse_timestamp("2:02"), 122)
        self.assertEqual(clip.parse_timestamp("1:02:03"), 3723)

    def test_rejects_invalid_times(self):
        for text in ("2:60", "1:60:00", "noon", "2", "1:2:03"):
            with self.subTest(text=text):
                with self.assertRaises(ValueError):
                    clip.parse_timestamp(text)


class PartValidationTests(unittest.TestCase):
    def test_start_must_be_before_end(self):
        with self.assertRaises(ValueError):
            clip.validate_part("2:15", "2:02")
        with self.assertRaises(ValueError):
            clip.validate_part("2:02", "2:02")

    def test_accepts_ordered_range(self):
        clip.validate_part("2:02", "2:15")


class PrefixTests(unittest.TestCase):
    def test_rejects_path_pieces(self):
        for text in ("a/b", "a\\b", "..", "foo/../bar"):
            with self.subTest(text=text):
                with self.assertRaises(ValueError):
                    clip.sanitize_prefix(text)

    def test_blank_prefix_is_allowed(self):
        self.assertEqual(clip.sanitize_prefix("   "), "")

    def test_keeps_spaces(self):
        self.assertEqual(clip.sanitize_prefix("  Nghia Si  "), "Nghia Si")


class FilenameTests(unittest.TestCase):
    def test_part_filename(self):
        name = clip.clip_filename(
            "TNTT Doan VSL LBM 2014 - Nghia Si Modern Dance",
            1,
            "2:02",
            "2:15",
        )
        self.assertEqual(
            name,
            "TNTT Doan VSL LBM 2014 - Nghia Si Modern Dance - part 1 [2:02 - 2:15].mp4",
        )


class WholeVideoTests(unittest.TestCase):
    def test_full_filename(self):
        self.assertEqual(clip.full_filename("Nghia Si"), "Nghia Si.mp4")

    def test_whole_video_without_parts(self):
        url, prefix, parts, whole = clip.parse_request(
            {
                "url": "https://youtu.be/-BNGtv0R7ho",
                "prefix": "Nghia Si",
                "parts": [{"start": "", "end": ""}],
                "whole": True,
            }
        )
        self.assertEqual(url, "https://youtu.be/-BNGtv0R7ho")
        self.assertEqual(prefix, "Nghia Si")
        self.assertEqual(parts, [])
        self.assertTrue(whole)

    def test_parts_still_required_without_whole_video(self):
        with self.assertRaises(ValueError):
            clip.parse_request(
                {
                    "url": "https://youtu.be/-BNGtv0R7ho",
                    "prefix": "Nghia Si",
                    "parts": [{"start": "", "end": ""}],
                    "whole": False,
                }
            )

    def test_full_download_command_has_no_time_range(self):
        command = clip.download_command("https://youtu.be/-BNGtv0R7ho", "video.mp4")
        self.assertNotIn("--download-sections", command)
        self.assertIn("video.mp4", command)

    def test_section_download_command_keeps_time_range(self):
        command = clip.download_command(
            "https://youtu.be/-BNGtv0R7ho",
            "part.mp4",
            start="2:02",
            end="2:15",
        )
        self.assertIn("--download-sections", command)
        self.assertIn("*2:02-2:15", command)


class UrlTests(unittest.TestCase):
    def test_accepts_youtube_hosts(self):
        clip.validate_youtube_url("https://youtu.be/-BNGtv0R7ho")
        clip.validate_youtube_url("https://www.youtube.com/watch?v=-BNGtv0R7ho")
        clip.validate_youtube_url("https://m.youtube.com/watch?v=-BNGtv0R7ho")

    def test_rejects_other_hosts(self):
        with self.assertRaises(ValueError):
            clip.validate_youtube_url("https://example.com/watch?v=1")


if __name__ == "__main__":
    unittest.main()
