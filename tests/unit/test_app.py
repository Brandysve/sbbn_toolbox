from PySide6.QtWidgets import QApplication

from sbbn_toolbox.app import create_application
from sbbn_toolbox.constants import APPLICATION_NAME
from sbbn_toolbox.ui.theme import load_stylesheet


def test_create_application_sets_name_and_theme(qapp: QApplication) -> None:
    application = create_application([])

    assert application is qapp
    assert application.applicationName() == APPLICATION_NAME
    assert application.styleSheet() == load_stylesheet()


def test_stylesheet_resolves_tokens_and_interaction_states() -> None:
    stylesheet = load_stylesheet()

    assert "@" not in stylesheet
    assert "#361C3E" in stylesheet
    assert "#4B2754" in stylesheet
    assert "#EDE3F0" in stylesheet
    assert "#FFFEF9" in stylesheet
    assert "#F6F4F7" in stylesheet
    assert "#E6E2E9" in stylesheet
    assert "#1B1420" in stylesheet
    assert "#5C5563" in stylesheet
    assert ":hover" in stylesheet
    assert ":focus" in stylesheet
    assert ":checked" in stylesheet
    assert ":disabled" in stylesheet
    assert "gradient" not in stylesheet.lower()
