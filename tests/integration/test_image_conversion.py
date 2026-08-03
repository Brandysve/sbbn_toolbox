import re
import stat
from pathlib import Path

import pytest
from PIL import Image
from pypdf import PdfReader

from sbbn_toolbox.services import image_to_pdf_service
from sbbn_toolbox.services.image_to_pdf_service import (
    DestinationExistsError,
    ImageConversionCancelled,
    ImageConversionError,
    ImagePdfOptions,
    ImageToPdfService,
    PageMode,
    PageOrientation,
)
from sbbn_toolbox.services.validation_service import (
    ImageValidationError,
    ImageValidationService,
)


def create_image(path: Path, image_format: str, size: tuple[int, int] = (120, 80)) -> bytes:
    Image.new("RGB", size, (90, 30, 180)).save(path, format=image_format)
    return path.read_bytes()


def assert_no_partial_files(path: Path) -> None:
    assert not list(path.glob(".*.sbbn-partial-*.pdf"))


def page_size(path: Path, index: int = 0) -> tuple[float, float]:
    page = PdfReader(path).pages[index]
    return float(page.mediabox.width), float(page.mediabox.height)


@pytest.mark.parametrize(
    ("suffix", "image_format"),
    ((".jpg", "JPEG"), (".jpeg", "JPEG"), (".png", "PNG"), (".bmp", "BMP")),
)
def test_each_supported_format_produces_a_pdf(
    tmp_path: Path,
    suffix: str,
    image_format: str,
) -> None:
    source = tmp_path / f"image été{suffix}"
    original = create_image(source, image_format)
    item = ImageValidationService().validate(source)
    destination = tmp_path / f"résultat {image_format}.pdf"

    ImageToPdfService().convert([item], destination, ImagePdfOptions())

    assert len(PdfReader(destination).pages) == 1
    assert source.read_bytes() == original
    assert_no_partial_files(tmp_path)


def test_unrotated_jpeg_uses_direct_img2pdf_path(tmp_path: Path) -> None:
    source = tmp_path / "jpeg direct.jpg"
    create_image(source, "JPEG")
    item = ImageValidationService().validate(source)
    service = ImageToPdfService()

    def forbid_normalization(unused_item: object) -> bytes:
        del unused_item
        raise AssertionError("Pillow ne doit pas normaliser ce JPEG")

    service._normalized_image = forbid_normalization  # type: ignore[method-assign]

    service.convert([item], tmp_path / "direct.pdf", ImagePdfOptions())

    assert (tmp_path / "direct.pdf").exists()
    assert_no_partial_files(tmp_path)


def test_mixed_formats_keep_reordered_sequence(tmp_path: Path) -> None:
    validator = ImageValidationService()
    sources = [
        (tmp_path / "large.jpg", "JPEG", (180, 60)),
        (tmp_path / "haute.png", "PNG", (60, 180)),
        (tmp_path / "carrée.bmp", "BMP", (100, 100)),
    ]
    items = []
    originals = {}
    for path, image_format, size in sources:
        originals[path] = create_image(path, image_format, size)
        items.append(validator.validate(path))
    reordered = [items[1], items[2], items[0]]
    destination = tmp_path / "mélange ordonné.pdf"

    ImageToPdfService().convert(reordered, destination, ImagePdfOptions())

    sizes = [page_size(destination, index) for index in range(3)]
    assert sizes[0][1] > sizes[0][0]
    assert sizes[1][0] == pytest.approx(sizes[1][1])
    assert sizes[2][0] > sizes[2][1]
    assert all(path.read_bytes() == content for path, content in originals.items())
    assert_no_partial_files(tmp_path)


@pytest.mark.parametrize("rotation", (90, 180, 270))
def test_rotations_are_applied_without_modifying_source(tmp_path: Path, rotation: int) -> None:
    source = tmp_path / "rotation.png"
    original = create_image(source, "PNG", (160, 80))
    item = ImageValidationService().validate(source).rotated(rotation)
    destination = tmp_path / f"rotation-{rotation}.pdf"

    ImageToPdfService().convert([item], destination, ImagePdfOptions())

    width, height = page_size(destination)
    if rotation in {90, 270}:
        assert height > width
    else:
        assert width > height
    assert source.read_bytes() == original
    assert_no_partial_files(tmp_path)


def test_a4_orientation_margins_and_ratio_are_respected(tmp_path: Path) -> None:
    source = tmp_path / "paysage.png"
    create_image(source, "PNG", (300, 100))
    item = ImageValidationService().validate(source)
    destination = tmp_path / "a4 paysage.pdf"

    ImageToPdfService().convert(
        [item],
        destination,
        ImagePdfOptions(
            page_mode=PageMode.A4,
            orientation=PageOrientation.LANDSCAPE,
            margin_mm=10,
        ),
    )

    width, height = page_size(destination)
    assert width == pytest.approx(841.89, abs=0.1)
    assert height == pytest.approx(595.28, abs=0.1)
    content = PdfReader(destination).pages[0].get_contents().get_data().decode("ascii")
    matrix = [float(value) for value in re.findall(r"[-\d.]+", content.split(" cm")[0])[-6:]]
    drawn_width, drawn_height, offset_x, offset_y = matrix[0], matrix[3], matrix[4], matrix[5]
    assert drawn_width / drawn_height == pytest.approx(3.0, rel=0.01)
    assert offset_x >= 28
    assert offset_y >= 28
    assert offset_x + drawn_width <= width - 28
    assert offset_y + drawn_height <= height - 28


@pytest.mark.parametrize(
    ("orientation", "landscape"),
    ((PageOrientation.AUTO, True), (PageOrientation.PORTRAIT, False)),
)
def test_a4_auto_and_portrait_orientation(
    tmp_path: Path,
    orientation: PageOrientation,
    landscape: bool,
) -> None:
    source = tmp_path / f"{orientation}.jpg"
    create_image(source, "JPEG", (200, 80))
    destination = tmp_path / f"{orientation}.pdf"

    ImageToPdfService().convert(
        [ImageValidationService().validate(source)],
        destination,
        ImagePdfOptions(page_mode=PageMode.A4, orientation=orientation),
    )

    width, height = page_size(destination)
    assert (width > height) is landscape


def test_corrupt_and_deceptive_images_are_rejected(tmp_path: Path) -> None:
    corrupt = tmp_path / "corrompue.jpg"
    corrupt.write_bytes(b"not an image")
    deceptive = tmp_path / "trompeuse.jpg"
    create_image(deceptive, "PNG")
    invalid_extension = tmp_path / "image.gif"
    create_image(invalid_extension, "GIF")
    validator = ImageValidationService()

    with pytest.raises(ImageValidationError, match="corrompu"):
        validator.validate(corrupt)
    with pytest.raises(ImageValidationError, match="extension"):
        validator.validate(deceptive)
    with pytest.raises(ImageValidationError, match="Extension"):
        validator.validate(invalid_extension)


def test_existing_destination_requires_explicit_overwrite(tmp_path: Path) -> None:
    source = tmp_path / "image.jpg"
    create_image(source, "JPEG")
    item = ImageValidationService().validate(source)
    destination = tmp_path / "existant.pdf"
    destination.write_bytes(b"ancien")
    service = ImageToPdfService()

    with pytest.raises(DestinationExistsError):
        service.convert([item], destination, ImagePdfOptions())
    assert destination.read_bytes() == b"ancien"
    assert_no_partial_files(tmp_path)

    service.convert([item], destination, ImagePdfOptions(), overwrite=True)

    assert destination.read_bytes().startswith(b"%PDF")
    assert_no_partial_files(tmp_path)


def test_cancellation_removes_partial_and_does_not_create_result(tmp_path: Path) -> None:
    validator = ImageValidationService()
    items = []
    for index in range(3):
        source = tmp_path / f"image-{index}.png"
        create_image(source, "PNG")
        items.append(validator.validate(source))
    destination = tmp_path / "annulé.pdf"
    cancelled = False

    def progress(current: int, total: int) -> None:
        nonlocal cancelled
        del total
        cancelled = current == 1

    with pytest.raises(ImageConversionCancelled):
        ImageToPdfService().convert(
            items,
            destination,
            ImagePdfOptions(),
            progress=progress,
            is_cancelled=lambda: cancelled,
        )

    assert not destination.exists()
    assert_no_partial_files(tmp_path)


def test_simulated_error_and_missing_source_leave_no_residue(tmp_path: Path) -> None:
    source = tmp_path / "disparue.bmp"
    create_image(source, "BMP")
    item = ImageValidationService().validate(source)
    source.unlink()
    destination = tmp_path / "erreur.pdf"

    with pytest.raises(ImageConversionError, match="inaccessible"):
        ImageToPdfService().convert([item], destination, ImagePdfOptions())

    assert not destination.exists()
    assert_no_partial_files(tmp_path)


def test_read_only_destination_is_rejected_without_residue(tmp_path: Path) -> None:
    source = tmp_path / "image.png"
    create_image(source, "PNG")
    item = ImageValidationService().validate(source)
    destination_dir = tmp_path / "lecture-seule"
    destination_dir.mkdir()
    destination_dir.chmod(stat.S_IRUSR | stat.S_IXUSR)
    try:
        with pytest.raises(ImageConversionError, match="lecture seule"):
            ImageToPdfService().convert([item], destination_dir / "sortie.pdf", ImagePdfOptions())
    finally:
        destination_dir.chmod(stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR)

    assert_no_partial_files(destination_dir)


def test_atomic_replace_failure_preserves_existing_result_and_cleans_partial(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "image.jpg"
    create_image(source, "JPEG")
    item = ImageValidationService().validate(source)
    destination = tmp_path / "sortie existante.pdf"
    previous_result = "résultat précédent".encode()
    destination.write_bytes(previous_result)

    def fail_replace(source_path: Path, destination_path: Path) -> None:
        raise OSError(f"échec simulé {source_path.name} {destination_path.name}")

    monkeypatch.setattr(image_to_pdf_service.os, "replace", fail_replace)

    with pytest.raises(ImageConversionError, match="conversion a échoué"):
        ImageToPdfService().convert([item], destination, ImagePdfOptions(), overwrite=True)

    assert destination.read_bytes() == previous_result
    assert_no_partial_files(tmp_path)
