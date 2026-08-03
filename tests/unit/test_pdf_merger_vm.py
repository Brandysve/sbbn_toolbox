import time
from collections.abc import Iterator
from pathlib import Path

from PySide6.QtCore import QTimer
from pytestqt.qtbot import QtBot

from sbbn_toolbox.domain.pdf_page_item import PdfPageItem
from sbbn_toolbox.services.preview_service import PreviewService
from sbbn_toolbox.viewmodels.pdf_merger_vm import PdfMergerViewModel


def make_page(path: Path, index: int) -> PdfPageItem:
    return PdfPageItem(
        source_path=path,
        source_page_index=index,
        display_page_number=index + 1,
        source_display_name=path.name,
        width=100,
        height=200,
    )


def test_viewmodel_reorders_rotates_removes_and_clears(tmp_path: Path) -> None:
    first_source = (tmp_path / "un.pdf").resolve()
    second_source = (tmp_path / "deux.pdf").resolve()
    first = make_page(first_source, 0)
    second = make_page(second_source, 0)
    third = make_page(first_source, 1)
    viewmodel = PdfMergerViewModel()
    viewmodel.pages = [first, second, third]

    viewmodel.reorder([third.identifier, first.identifier, second.identifier])
    assert viewmodel.pages == [third, first, second]

    viewmodel.rotate_selected([first.identifier, second.identifier], 270)
    assert [page.rotation for page in viewmodel.pages] == [0, 270, 270]

    viewmodel.remove_selected([first.identifier])
    assert [page.identifier for page in viewmodel.pages] == [third.identifier, second.identifier]

    viewmodel.clear()
    assert viewmodel.pages == []
    assert viewmodel.preview_service.cache_size_bytes == 0


def test_loading_runs_off_ui_thread_and_interface_timer_remains_responsive(
    qtbot: QtBot,
    tmp_path: Path,
) -> None:
    class SlowPreviewService(PreviewService):
        def iter_document_pages(
            self,
            path: Path,
            *,
            is_cancelled: object = None,
        ) -> Iterator[PdfPageItem]:
            for index in range(4):
                time.sleep(0.02)
                yield make_page(path.resolve(), index)

    source = tmp_path / "volumineux.pdf"
    source.write_bytes(b"fixture controlled by fake service")
    viewmodel = PdfMergerViewModel(preview_service=SlowPreviewService())
    ui_was_responsive = False

    def mark_responsive() -> None:
        nonlocal ui_was_responsive
        ui_was_responsive = True

    QTimer.singleShot(0, mark_responsive)
    with qtbot.waitSignal(
        viewmodel.busy_changed,
        timeout=2_000,
        check_params_cb=lambda busy: not busy,
    ):
        viewmodel.import_files([source])

    assert ui_was_responsive
    assert len(viewmodel.pages) == 4
    viewmodel.shutdown()


def test_duplicate_pdf_is_not_loaded_twice(qtbot: QtBot, tmp_path: Path) -> None:
    class OnePageService(PreviewService):
        def iter_document_pages(
            self,
            path: Path,
            *,
            is_cancelled: object = None,
        ) -> Iterator[PdfPageItem]:
            del is_cancelled
            yield make_page(path.resolve(), 0)

    source = tmp_path / "double.pdf"
    source.write_bytes(b"fixture controlled by fake service")
    viewmodel = PdfMergerViewModel(preview_service=OnePageService())
    with qtbot.waitSignal(viewmodel.busy_changed, check_params_cb=lambda busy: not busy):
        viewmodel.import_files([source, source])

    assert len(viewmodel.pages) == 1
    viewmodel.shutdown()


def test_loading_can_be_cancelled_between_pages(qtbot: QtBot, tmp_path: Path) -> None:
    class CancellableService(PreviewService):
        def iter_document_pages(
            self,
            path: Path,
            *,
            is_cancelled: object = None,
        ) -> Iterator[PdfPageItem]:
            for index in range(20):
                time.sleep(0.01)
                if callable(is_cancelled) and is_cancelled():
                    from sbbn_toolbox.services.preview_service import PdfLoadCancelled

                    raise PdfLoadCancelled("annulé")
                yield make_page(path.resolve(), index)

    source = tmp_path / "annulable.pdf"
    source.write_bytes(b"fixture controlled by fake service")
    viewmodel = PdfMergerViewModel(preview_service=CancellableService())

    with (
        qtbot.waitSignal(viewmodel.operation_cancelled, timeout=2_000),
        qtbot.waitSignal(
            viewmodel.busy_changed,
            timeout=2_000,
            check_params_cb=lambda busy: not busy,
        ),
    ):
        viewmodel.import_files([source])
        QTimer.singleShot(25, viewmodel.cancel)

    assert len(viewmodel.pages) < 20
    viewmodel.shutdown()


def test_shutdown_cancels_loading_and_releases_workers(
    qtbot: QtBot,
    tmp_path: Path,
) -> None:
    class SlowService(PreviewService):
        def iter_document_pages(
            self,
            path: Path,
            *,
            is_cancelled: object = None,
        ) -> Iterator[PdfPageItem]:
            for index in range(50):
                time.sleep(0.01)
                if callable(is_cancelled) and is_cancelled():
                    return
                yield make_page(path.resolve(), index)

    source = tmp_path / "fermeture.pdf"
    source.write_bytes(b"fixture controlled by fake service")
    viewmodel = PdfMergerViewModel(preview_service=SlowService())

    with qtbot.waitSignal(viewmodel.page_added, timeout=1_000):
        viewmodel.import_files([source])

    viewmodel.shutdown()
    qtbot.waitUntil(lambda: not viewmodel.is_busy, timeout=1_000)

    assert len(viewmodel.pages) < 50
    assert viewmodel.preview_service.cache_size_bytes == 0
