from tools.workflow_installed_index import catalogue_rows, render_installed_index


def test_partial_installation_preserves_user_content_and_omits_uninstalled(tmp_path):
    source = "| `26-h3-world` | World |\n| [89-h14-reviewed](89-h14-reviewed/README.md) | H14 |\n"
    world = tmp_path / "26-h3-world"
    world.mkdir()
    (world / "saved.json").write_bytes(b'{"user-edited":true}')
    (world / "README.md").write_bytes(b'user instructions')
    (tmp_path / "README.md").write_bytes(b'original index')
    empty = tmp_path / "89-h14-reviewed"
    empty.mkdir()
    custom = tmp_path / "90-custom"
    custom.mkdir()
    (custom / "mine.json").write_bytes(b'{}')
    before = {p: p.read_bytes() for p in tmp_path.rglob('*') if p.is_file()}
    rendered = render_installed_index(source, tmp_path)
    assert "[26-h3-world](26-h3-world/README.md) | 1 | World" in rendered
    assert "89-h14-reviewed" not in rendered
    assert "[90-custom](90-custom/) | 1 | 本机自有分类" in rendered
    assert before == {p: p.read_bytes() for p in before}
    assert rendered == render_installed_index(source, tmp_path)
    (empty / "new.json").write_bytes(b'{}')
    assert "89-h14-reviewed" in render_installed_index(source, tmp_path)


def test_highlighted_and_legacy_category_rows_merge_without_losing_descriptions():
    rows = catalogue_rows("| `26-h3-world` | A |\n| [26-h3-world](26-h3-world/README.md) | B |\n| `26-h3-world` | A |")
    assert rows == {"26-h3-world": "A；B"}
