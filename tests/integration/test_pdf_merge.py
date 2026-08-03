import stat
from pathlib import Path

import pytest
from pypdf import PdfReader, PdfWriter

from sbbn_toolbox.services import pdf_merge_service
from sbbn_toolbox.services.pdf_merge_service import (
    PdfDestinationExistsError,
    PdfMergeCancelled,
    PdfMergeError,
    PdfMergeService,
)
from sbbn_toolbox.services.preview_service import PdfLoadError, PreviewService


def create_pdf(
    path: Path,
    page_sizes: list[tuple[float, float]],
    *,
    password: str | None = None,
) -> bytes:
    writer = PdfWriter()
    for width, height in page_sizes:
        writer.add_blank_page(width=width, height=height)
    if password is not None:
        writer.encrypt(password)
    with path.open("wb") as stream:
        writer.write(stream)
    return path.read_bytes()


def load_pages(path: Path) -> list:
    return list(PreviewService().iter_document_pages(path))


def assert_no_partial(path: Path) -> None:
    assert not list(path.glob(".*.sbbn-partial-*.pdf"))


def windows_safe_long_folder(root: Path, filename: str) -> Path:
    """Créer un chemin long et Unicode sans dépendre des chemins étendus Windows."""
    maximum_full_length = 235
    available = maximum_full_length - len(str(root)) - len(filename) - 2
    fragment = "dossier PDF long avec espaces et accents é 文件 "
    folder_name = (fragment * 8)[:available].rstrip()
    assert len(folder_name) >= 40
    folder = root / folder_name
    folder.mkdir()
    full_path = folder / filename
    assert len(str(full_path)) >= 180
    assert len(str(full_path)) <= maximum_full_length
    assert "é" in str(full_path) and "文件" in str(full_path)
    return folder


def output_sizes(path: Path) -> list[tuple[float, float]]:
    return [
        (float(page.mediabox.width), float(page.mediabox.height)) for page in PdfReader(path).pages
    ]


def test_merge_multiple_sources_in_exact_reordered_sequence(tmp_path: Path) -> None:
    first = tmp_path / "premier été.pdf"
    second = tmp_path / "deuxième 文件.pdf"
    original_first = create_pdf(first, [(100, 200), (200, 100)])
    original_second = create_pdf(second, [(300, 400), (400, 300)])
    first_pages = load_pages(first)
    second_pages = load_pages(second)
    ordered = [second_pages[1], first_pages[0], second_pages[0], first_pages[1]]
    destination = tmp_path / "fusion ordonnée.pdf"

    PdfMergeService().merge(ordered, destination)

    assert output_sizes(destination) == [
        (400, 300),
        (100, 200),
        (300, 400),
        (200, 100),
    ]
    assert first.read_bytes() == original_first
    assert second.read_bytes() == original_second
    assert_no_partial(tmp_path)


def test_single_page_pdf_and_page_removal(tmp_path: Path) -> None:
    source = tmp_path / "source.pdf"
    create_pdf(source, [(100, 100), (200, 200), (300, 300)])
    pages = load_pages(source)
    destination = tmp_path / "une page.pdf"

    PdfMergeService().merge([pages[1]], destination)

    assert output_sizes(destination) == [(200, 200)]
    assert_no_partial(tmp_path)


@pytest.mark.parametrize("rotation", (90, 180, 270))
def test_page_rotations_are_written(tmp_path: Path, rotation: int) -> None:
    source = tmp_path / "rotation.pdf"
    create_pdf(source, [(100, 200)])
    page = load_pages(source)[0].rotated(rotation)
    destination = tmp_path / f"rotation-{rotation}.pdf"

    PdfMergeService().merge([page], destination)

    assert PdfReader(destination).pages[0].rotation == rotation
    assert_no_partial(tmp_path)


def test_corrupt_empty_and_protected_pdfs_are_rejected(tmp_path: Path) -> None:
    corrupt = tmp_path / "corrompu.pdf"
    corrupt.write_bytes(b"not a pdf")
    empty = tmp_path / "vide.pdf"
    create_pdf(empty, [])
    protected = tmp_path / "protégé.pdf"
    create_pdf(protected, [(100, 100)], password="secret")
    service = PreviewService()

    with pytest.raises(PdfLoadError, match="corrompu"):
        list(service.iter_document_pages(corrupt))
    with pytest.raises(PdfLoadError, match="vide"):
        list(service.iter_document_pages(empty))
    with pytest.raises(PdfLoadError, match="protégés"):
        list(service.iter_document_pages(protected))


def test_source_deleted_after_import_fails_without_residue(tmp_path: Path) -> None:
    source = tmp_path / "supprimé.pdf"
    create_pdf(source, [(100, 100)])
    page = load_pages(source)[0]
    source.unlink()
    destination = tmp_path / "résultat.pdf"

    with pytest.raises(PdfMergeError, match="inaccessible"):
        PdfMergeService().merge([page], destination)

    assert not destination.exists()
    assert_no_partial(tmp_path)


def test_source_deleted_during_merge_leaves_no_result(tmp_path: Path) -> None:
    first = tmp_path / "premier.pdf"
    second = tmp_path / "supprimé pendant fusion.pdf"
    first_original = create_pdf(first, [(100, 100)])
    create_pdf(second, [(200, 200)])
    pages = [*load_pages(first), *load_pages(second)]
    destination = tmp_path / "incomplet.pdf"

    def remove_next_source(current: int, total: int) -> None:
        del total
        if current == 1:
            second.unlink()

    with pytest.raises(PdfMergeError, match="inaccessible"):
        PdfMergeService().merge(pages, destination, progress=remove_next_source)

    assert first.read_bytes() == first_original
    assert not destination.exists()
    assert_no_partial(tmp_path)


def test_existing_destination_refused_then_accepted(tmp_path: Path) -> None:
    source = tmp_path / "source.pdf"
    create_pdf(source, [(100, 100)])
    destination = tmp_path / "existant.pdf"
    destination.write_bytes(b"ancien")
    page = load_pages(source)[0]
    service = PdfMergeService()

    with pytest.raises(PdfDestinationExistsError):
        service.merge([page], destination)
    assert destination.read_bytes() == b"ancien"

    service.merge([page], destination, overwrite=True)

    assert destination.read_bytes().startswith(b"%PDF")
    assert_no_partial(tmp_path)


def test_cancellation_between_pages_leaves_no_result(tmp_path: Path) -> None:
    source = tmp_path / "source.pdf"
    create_pdf(source, [(100, 100)] * 4)
    pages = load_pages(source)
    cancelled = False

    def progress(current: int, total: int) -> None:
        nonlocal cancelled
        del total
        cancelled = current == 1

    destination = tmp_path / "annulé.pdf"
    with pytest.raises(PdfMergeCancelled):
        PdfMergeService().merge(
            pages,
            destination,
            progress=progress,
            is_cancelled=lambda: cancelled,
        )

    assert not destination.exists()
    assert_no_partial(tmp_path)


def test_atomic_error_preserves_previous_result_and_cleans_partial(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "source.pdf"
    create_pdf(source, [(100, 100)])
    destination = tmp_path / "résultat existant.pdf"
    previous = b"previous result"
    destination.write_bytes(previous)

    def fail_replace(source_path: Path, destination_path: Path) -> None:
        raise OSError(f"échec {source_path.name} {destination_path.name}")

    monkeypatch.setattr(pdf_merge_service.os, "replace", fail_replace)

    with pytest.raises(PdfMergeError, match="fusion a échoué"):
        PdfMergeService().merge(load_pages(source), destination, overwrite=True)

    assert destination.read_bytes() == previous
    assert_no_partial(tmp_path)


def test_read_only_destination_is_rejected(tmp_path: Path) -> None:
    source = tmp_path / "source.pdf"
    create_pdf(source, [(100, 100)])
    destination_dir = tmp_path / "lecture seule"
    destination_dir.mkdir()
    destination_dir.chmod(stat.S_IRUSR | stat.S_IXUSR)
    try:
        with pytest.raises(PdfMergeError, match="lecture seule"):
            PdfMergeService().merge(load_pages(source), destination_dir / "sortie.pdf")
    finally:
        destination_dir.chmod(stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR)

    assert_no_partial(destination_dir)


def test_preview_cache_is_bounded_and_released_by_source(tmp_path: Path) -> None:
    source = tmp_path / "aperçus.pdf"
    create_pdf(source, [(400, 600)] * 8)
    pages = load_pages(source)
    probe = PreviewService()
    one_thumbnail_size = len(probe.render_thumbnail(pages[0], width=120))
    probe.clear()
    cache_limit = one_thumbnail_size * 2
    service = PreviewService(max_cache_bytes=cache_limit)

    for page in pages:
        service.render_thumbnail(page, width=120)

    assert service.cache_size_bytes <= cache_limit
    assert service.cache_entry_count <= 2
    service.clear_source(source.resolve())
    assert service.cache_size_bytes == 0
    assert service.cache_entry_count == 0


def test_long_unicode_paths_and_identical_pdf_names_from_different_folders(
    tmp_path: Path,
) -> None:
    filename = "document identique.pdf"
    first_folder = windows_safe_long_folder(tmp_path, filename)
    second_folder = tmp_path / "deuxième dossier 文件"
    second_folder.mkdir()
    first = first_folder / filename
    second = second_folder / filename
    first_original = create_pdf(first, [(100, 200)])
    second_original = create_pdf(second, [(300, 400)])
    destination = tmp_path / "fusion Unicode finale.pdf"

    PdfMergeService().merge([*load_pages(second), *load_pages(first)], destination)

    assert output_sizes(destination) == [(300, 400), (100, 200)]
    assert first.read_bytes() == first_original
    assert second.read_bytes() == second_original
    assert_no_partial(tmp_path)
