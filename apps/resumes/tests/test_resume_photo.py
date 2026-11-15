import io

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image

pytestmark = pytest.mark.django_db

PHOTO = "/api/v1/resumes/me/photo/"


@pytest.fixture(autouse=True)
def tmp_media(settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    return tmp_path


def image_bytes(fmt="PNG", size=(1200, 900), mode="RGBA", color=(200, 30, 30, 128)):
    buffer = io.BytesIO()
    Image.new(mode, size, color).save(buffer, format=fmt)
    return buffer.getvalue()


def upload(client, data, name="me.png", content_type="image/png"):
    return client.put(
        PHOTO, {"photo": SimpleUploadedFile(name, data, content_type)}, format="multipart"
    )


def test_upload_reencodes_resizes_and_hides_original_name(make_resume, auth_client, tmp_media):
    user, resume = make_resume()
    r = upload(auth_client(user), image_bytes(), name="../../evil name.png")
    assert r.status_code == 200 and r.json() == {"has_photo": True}
    resume.refresh_from_db()
    assert resume.photo.name.startswith("resume_photos/") and resume.photo.name.endswith(".jpg")
    assert "evil" not in resume.photo.name
    stored = Image.open(resume.photo.path)
    assert stored.format == "JPEG" and max(stored.size) <= 800


def test_get_photo_owner_only_with_private_headers(make_resume, auth_client):
    user, _ = make_resume()
    other, _ = make_resume()
    client = auth_client(user)
    assert client.get(PHOTO, HTTP_ACCEPT="image/*").status_code == 404  # none yet
    upload(client, image_bytes())
    r = client.get(PHOTO, HTTP_ACCEPT="image/*")
    assert r.status_code == 200 and r["Content-Type"] == "image/jpeg"
    assert r["Cache-Control"] == "private, no-store" and r["X-Content-Type-Options"] == "nosniff"
    assert Image.open(io.BytesIO(b"".join(r.streaming_content))).format == "JPEG"
    assert auth_client(other).get(PHOTO).status_code == 404  # sees only their own (none)


def test_photo_requires_login(api_client):
    assert api_client.get(PHOTO).status_code == 401
    assert api_client.put(PHOTO, {}, format="multipart").status_code == 401


def test_replace_photo_deletes_old_file(make_resume, auth_client, tmp_media):
    user, resume = make_resume()
    client = auth_client(user)
    upload(client, image_bytes())
    resume.refresh_from_db()
    first = resume.photo.path
    upload(client, image_bytes(color=(0, 0, 255, 255)))
    resume.refresh_from_db()
    import os

    assert not os.path.exists(first) and os.path.exists(resume.photo.path)


def test_delete_photo_removes_file(make_resume, auth_client):
    import os

    user, resume = make_resume()
    client = auth_client(user)
    upload(client, image_bytes())
    resume.refresh_from_db()
    path = resume.photo.path
    assert client.delete(PHOTO).status_code == 204
    resume.refresh_from_db()
    assert not resume.photo and not os.path.exists(path)
    assert client.get("/api/v1/resumes/me/").json()["has_photo"] is False


@pytest.mark.parametrize(
    ("data", "name"),
    [
        (b"<?php echo 1; ?>", "shell.png"),
        (b"just text", "photo.jpg"),
        (b"", "empty.png"),
        (b"GIF89a" + b"\x00" * 50, "anim.gif"),
    ],
)
def test_rejects_non_images_even_with_image_extension(make_resume, auth_client, data, name):
    user, resume = make_resume()
    r = upload(auth_client(user), data, name=name)
    assert r.status_code == 400 and "photo" in r.json()["error"]["details"]
    resume.refresh_from_db()
    assert not resume.photo


def test_rejects_unsupported_format_and_oversize(make_resume, auth_client):
    user, _ = make_resume()
    client = auth_client(user)
    assert upload(client, image_bytes("GIF", mode="P", color=1), name="a.gif").status_code == 400
    big = SimpleUploadedFile("big.png", b"\x89PNG" + b"0" * (2 * 1024 * 1024 + 10), "image/png")
    assert client.put(PHOTO, {"photo": big}, format="multipart").status_code == 400


def test_photo_requires_resume_first(make_seeker, auth_client):
    assert upload(auth_client(make_seeker()), image_bytes()).status_code == 404
