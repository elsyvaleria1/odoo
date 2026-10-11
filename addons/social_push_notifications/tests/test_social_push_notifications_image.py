import io

from PIL import Image

from odoo.tests.common import HttpCase


class SocialPushNotificationsImageCase(HttpCase):
    def test_push_image_is_accessible(self):
        pixel = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAIAAACQd1PeAAAADElEQVR4nGNgYGAAAAAEAAH2FzhVAAAAAElFTkSuQmCC"
        social_post = self.env["social.post"].create(
            {
                "message": "TestMessage",
                "post_method": "now",
                "push_notification_title": "PushNotificationTitle",
                "push_notification_image": pixel,
            }
        )

        response = self.url_open(
            "/social_push_notifications/social_post/%s/push_notification_image"
            % social_post.id
        )
        image = Image.open(io.BytesIO(response.content))
        width, _ = image.size
        self.assertTrue(width > 1)

        social_post.write({"state": "posted"})
        response = self.url_open(
            "/social_push_notifications/social_post/%s/push_notification_image"
            % social_post.id
        )
        image = Image.open(io.BytesIO(response.content))
        width, _ = image.size
        self.assertTrue(width == 1)
