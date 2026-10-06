from pathlib import Path

from manual_duplex.desktop import desktop_entry_content


def test_desktop_entry_uses_local_file_field_code_not_username_placeholder() -> None:
    content = desktop_entry_content(Path("/home/test/.local/bin/manual-duplex"))

    assert 'Exec="/home/test/.local/bin/manual-duplex" gui %f' in content
    assert "%u" not in content
    assert "MimeType=application/pdf;" in content
