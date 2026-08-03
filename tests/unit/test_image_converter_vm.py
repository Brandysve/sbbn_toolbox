from pathlib import Path

from PIL import Image
from PySide6.QtCore import QThread
from pytestqt.qtbot import QtBot

from sbbn_toolbox.services.image_to_pdf_service import ImagePdfOptions
from sbbn_toolbox.viewmodels.image_converter_vm import ImageConverterViewModel


def create_png(path: Path, size: tuple[int, int]) -> None:
    Image.new("RGB", size, "purple").save(path, format="PNG")


def test_viewmodel_reorders_rotates_removes_and_clears(tmp_path: Path) -> None:
    paths = [tmp_path / "un.png", tmp_path / "deux.png"]
    create_png(paths[0], (20, 10))
    create_png(paths[1], (10, 20))
    viewmodel = ImageConverterViewModel()
    viewmodel.import_files(paths)
    first, second = viewmodel.items

    viewmodel.reorder([second.identifier, first.identifier])
    assert [item.source_path for item in viewmodel.items] == [paths[1], paths[0]]

    viewmodel.rotate(first.identifier, 270)
    assert viewmodel.items[1].rotation == 270

    viewmodel.remove(second.identifier)
    assert [item.identifier for item in viewmodel.items] == [first.identifier]

    viewmodel.clear()
    assert viewmodel.items == []


def test_conversion_runs_in_worker_thread(qtbot: QtBot, tmp_path: Path) -> None:
    class FakeService:
        worker_thread: QThread | None = None

        def convert(
            self,
            items: object,
            destination: Path,
            options: object,
            **kwargs: object,
        ) -> Path:
            del items, options
            self.worker_thread = QThread.currentThread()
            progress = kwargs["progress"]
            progress(1, 1)  # type: ignore[operator]
            return destination

    source = tmp_path / "image.png"
    create_png(source, (20, 10))
    service = FakeService()
    viewmodel = ImageConverterViewModel(service=service)  # type: ignore[arg-type]
    viewmodel.import_files([source])

    with qtbot.waitSignal(
        viewmodel.busy_changed,
        timeout=2_000,
        check_params_cb=lambda busy: not busy,
    ):
        viewmodel.start_conversion(
            tmp_path / "sortie.pdf",
            ImagePdfOptions(),
            overwrite=False,
        )

    assert service.worker_thread is not None
    assert service.worker_thread is not QThread.currentThread()
