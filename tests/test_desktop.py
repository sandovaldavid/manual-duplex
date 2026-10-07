from pathlib import Path

from manual_duplex.desktop import desktop_entry_content, install_desktop_entry


def test_desktop_entry_uses_local_file_field_code_not_username_placeholder() -> None:
    content = desktop_entry_content(Path("/home/test/.local/bin/manual-duplex"))

    assert 'Exec="/home/test/.local/bin/manual-duplex" gui %f' in content
    assert "%u" not in content
    assert "MimeType=application/pdf;" in content


def test_desktop_entry_exposes_graphical_actions_and_app_icon() -> None:
    content = desktop_entry_content(Path("/home/test/.local/bin/manual-duplex"))

    assert "Icon=manual-duplex" in content
    assert "Actions=Configure;Help;" in content
    assert "Name=Configurar impresora" in content
    assert 'Exec="/home/test/.local/bin/manual-duplex" gui --configure' in content
    assert "Name=Ayuda y solución de problemas" in content
    assert 'Exec="/home/test/.local/bin/manual-duplex" gui --troubleshoot' in content


def test_install_desktop_entry_copies_packaged_icon(tmp_path: Path) -> None:
    destination = install_desktop_entry(
        executable=Path("/home/test/.local/bin/manual-duplex"),
        data_home=tmp_path,
    )

    icon = tmp_path / "icons" / "hicolor" / "scalable" / "apps" / "manual-duplex.svg"
    assert destination == tmp_path / "applications" / "manual-duplex.desktop"
    assert destination.is_file()
    assert icon.is_file()
    assert "<svg" in icon.read_text(encoding="utf-8")
