"""下载文件按作者归档的离线行为测试。"""
import tempfile
import unittest
import gc
from pathlib import Path

import db as database


class DownloadAuthorFolderTests(unittest.TestCase):
    """每条下载记录都应落在可安全创建的作者目录中。"""

    def test_uses_sanitized_nickname_and_douyin_id(self):
        """昵称或抖音号含 Windows 非法字符时，目录仍安全且可区分作者。"""
        from web.app import _author_download_directory

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            folder = _author_download_directory(
                root,
                {"author_name": "小/王", "author_douyin_id": "dy:100"},
            )

            self.assertEqual(folder, root / "小_王_dy_100")
            self.assertTrue(folder.is_dir())

    def test_falls_back_to_nickname_or_unknown_author(self):
        """缺少抖音号时用昵称；资料全缺失时归入未知作者。"""
        from web.app import _author_download_directory

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.assertEqual(
                _author_download_directory(root, {"author_name": "小王", "author_douyin_id": ""}),
                root / "小王",
            )
            self.assertEqual(_author_download_directory(root, {}), root / "未知作者")

    def test_loads_author_identity_for_every_download_source(self):
        """作者、话题、单作品三种下载项都要携带作者归档资料。"""
        from web.app import _load_download_items

        previous_db_path = database.DB_PATH
        with tempfile.TemporaryDirectory() as temporary:
            database.DB_PATH = Path(temporary) / "test.db"
            try:
                database.init_db()
                with database.get_db() as connection:
                    creator_id = connection.execute(
                        "INSERT INTO creators (name, sec_uid, nickname, douyin_id) VALUES (?, ?, ?, ?)",
                        ("导入名称", "sec-1", "作者甲", "dy-1"),
                    ).lastrowid
                    video_id = connection.execute(
                        "INSERT INTO videos (creator_id, video_id, title, video_url) VALUES (?, ?, ?, ?)",
                        (creator_id, "author-video", "作者作品", "https://example.com/author.mp4"),
                    ).lastrowid
                    connection.execute(
                        "INSERT INTO topic_results (topic, author_name, author_douyin_id, video_id, title, video_url) "
                        "VALUES (?, ?, ?, ?, ?, ?)",
                        ("测试话题", "作者乙", "dy-2", "topic-video", "话题作品", "https://example.com/topic.mp4"),
                    )
                    connection.execute(
                        "INSERT INTO single_video_results (author_name, author_douyin_id, video_id, title, video_url) "
                        "VALUES (?, ?, ?, ?, ?)",
                        ("作者丙", "dy-3", "single-video", "单作品", "https://example.com/single.mp4"),
                    )

                author_item = _load_download_items("author", [str(video_id)])[0]
                topic_item = _load_download_items("topic", ["topic-video"])[0]
                single_item = _load_download_items("single", ["single-video"])[0]

                self.assertEqual((author_item["author_name"], author_item["author_douyin_id"]), ("作者甲", "dy-1"))
                self.assertEqual((topic_item["author_name"], topic_item["author_douyin_id"]), ("作者乙", "dy-2"))
                self.assertEqual((single_item["author_name"], single_item["author_douyin_id"]), ("作者丙", "dy-3"))
            finally:
                connection = None
                database.DB_PATH = previous_db_path
                gc.collect()


if __name__ == "__main__":
    unittest.main()
