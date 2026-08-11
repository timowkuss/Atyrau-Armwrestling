"""Cloudinary: delete-запросы должны затрагивать только файлы собственного
аккаунта (cloud name), а не произвольные URL.

Запуск: python -m pytest tests/security -q
"""

import unittest
from unittest.mock import patch

from app.services import cloudinary_photos


class CloudinaryPhotoScopeTest(unittest.TestCase):
    def setUp(self):
        cloudinary_photos._CLOUD_NAME = "atyrau-armsport"

    def test_own_cloud_public_id_extracted(self):
        url = (
            "https://res.cloudinary.com/atyrau-armsport/image/upload/"
            "v1699999999/coaches/photo2.jpg"
        )
        self.assertEqual(
            cloudinary_photos._extract_public_id(url), "coaches/photo2"
        )

    def test_foreign_cloud_rejected(self):
        # Чужой cloud name: даже с валидным sync-токеном нельзя удалить
        # файл из чужого аккаунта, «подсунув» его URL.
        url = (
            "https://res.cloudinary.com/someone-else/image/upload/"
            "v1699999999/coaches/photo2.jpg"
        )
        self.assertIsNone(cloudinary_photos._extract_public_id(url))

    def test_random_url_rejected(self):
        self.assertIsNone(cloudinary_photos._extract_public_id("https://example.com/x.jpg"))

    def test_no_upload_section_rejected(self):
        url = "https://res.cloudinary.com/atyrau-armsport/image/coaches/photo2.jpg"
        self.assertIsNone(cloudinary_photos._extract_public_id(url))

    def test_unconfigured_cloud_name_accepts_any_cloud(self):
        # Когда CLOUDINARY не настроен — destroy всё равно не вызывается
        # (delete_cloudinary_photo выходит по _configured), поэтому cloud
        # name не проверяется. Проверяем, что извлечение остаётся живым.
        cloudinary_photos._CLOUD_NAME = ""
        url = (
            "https://res.cloudinary.com/anyone/image/upload/v1/folder/f.jpg"
        )
        self.assertEqual(
            cloudinary_photos._extract_public_id(url), "folder/f"
        )

    @patch("cloudinary.uploader.destroy")
    def test_delete_calls_destroy_only_for_own_cloud(self, mock_destroy):
        cloudinary_photos._configured = True
        own = (
            "https://res.cloudinary.com/atyrau-armsport/image/upload/"
            "v1/coaches/a.jpg"
        )
        cloudinary_photos.delete_cloudinary_photo(own)
        mock_destroy.assert_called_once_with("coaches/a", invalidate=True)

        mock_destroy.reset_mock()
        foreign = (
            "https://res.cloudinary.com/other/image/upload/v1/coaches/b.jpg"
        )
        cloudinary_photos.delete_cloudinary_photo(foreign)
        mock_destroy.assert_not_called()


if __name__ == "__main__":
    unittest.main()
