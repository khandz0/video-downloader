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
