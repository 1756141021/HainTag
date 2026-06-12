"""更新器纯逻辑：版本比较、资产选取、更新源目录探测、SHA256 校验（0.10.5）。"""
import hashlib

from native_app.updater import (
    _expected_sha256_for_url,
    _file_sha256,
    _find_update_source,
    _is_zip_download_url,
    _macos_download_url,
    _parse_sha256_block,
    _parse_version,
    _windows_download_url,
)

SAMPLE_HASH = "a" * 64
SAMPLE_BODY = f"""### Fixed
- something

### SHA256
```
{SAMPLE_HASH}  HainTag-v0.10.5.zip
{'b' * 64}  HainTag-v0.10.5.dmg
```
"""


class TestParseVersion:
    def test_v_prefix_normalized(self):
        assert _parse_version("v0.10.0") == _parse_version("0.10.0")

    def test_minor_double_digit_sorts_above_patch(self):
        assert _parse_version("0.10.0") > _parse_version("0.9.11")

    def test_release_sorts_above_prerelease(self):
        assert _parse_version("1.2.3") > _parse_version("1.2.3-rc4")

    def test_later_prerelease_sorts_higher(self):
        assert _parse_version("1.2.3-rc5") > _parse_version("1.2.3-rc4")

    def test_build_metadata_ignored(self):
        assert _parse_version("1.2.3+build7") == _parse_version("1.2.3")

    def test_trailing_zero_segment_equal(self):
        assert _parse_version("1.2.3.0") == _parse_version("1.2.3")

    def test_garbage_is_lowest(self):
        assert _parse_version("abc") < _parse_version("0.0.1")


class TestIsZipDownloadUrl:
    def test_zip(self):
        assert _is_zip_download_url("https://x/HainTag.zip")

    def test_zip_with_query(self):
        assert _is_zip_download_url("https://x/HainTag.ZIP?token=abc")

    def test_dmg_routes_away_from_auto_install(self):
        assert not _is_zip_download_url("https://x/HainTag.dmg")

    def test_empty_and_none(self):
        assert not _is_zip_download_url("")
        assert not _is_zip_download_url(None)


def _asset(name):
    return {"name": name, "browser_download_url": f"https://github.com/r/{name}"}


class TestAssetSelection:
    def test_windows_zip_preferred_over_macos(self):
        assets = [_asset("HainTag-macos.zip"), _asset("HainTag-windows-x64.zip")]
        assert "windows-x64" in _windows_download_url(assets)

    def test_generic_haintag_zip_accepted(self):
        assets = [_asset("HainTag-0.10.0.zip")]
        assert "HainTag-0.10.0.zip" in _windows_download_url(assets)

    def test_other_platform_only_falls_back_to_releases_page(self):
        assets = [_asset("HainTag-macos-arm64.zip")]
        assert _windows_download_url(assets).endswith("/releases")

    def test_macos_picks_dmg(self):
        assets = [_asset("HainTag-windows.zip"), _asset("HainTag.dmg")]
        assert _macos_download_url(assets).endswith("HainTag.dmg")

    def test_macos_no_dmg_falls_back(self):
        assert _macos_download_url([_asset("HainTag-windows.zip")]).endswith("/releases")

    def test_malformed_assets_ignored(self):
        assert _windows_download_url(["junk", None, 42]).endswith("/releases")


class TestFindUpdateSource:
    def test_exe_at_root(self, tmp_path):
        (tmp_path / "HainTag.exe").write_bytes(b"x")
        assert _find_update_source(str(tmp_path)) == str(tmp_path)

    def test_exe_in_subfolder(self, tmp_path):
        sub = tmp_path / "SomeFolderName"
        sub.mkdir()
        (sub / "HainTag.exe").write_bytes(b"x")
        assert _find_update_source(str(tmp_path)) == str(sub)

    def test_case_insensitive(self, tmp_path):
        (tmp_path / "haintag.EXE").write_bytes(b"x")
        assert _find_update_source(str(tmp_path)) == str(tmp_path)

    def test_missing_exe_returns_none(self, tmp_path):
        (tmp_path / "readme.txt").write_bytes(b"x")
        assert _find_update_source(str(tmp_path)) is None

    def test_missing_dir_returns_none(self, tmp_path):
        assert _find_update_source(str(tmp_path / "nope")) is None


class TestParseSha256Block:
    def test_parses_filenames_and_hashes(self):
        parsed = _parse_sha256_block(SAMPLE_BODY)
        assert parsed["haintag-v0.10.5.zip"] == SAMPLE_HASH
        assert len(parsed) == 2

    def test_no_block_returns_empty(self):
        assert _parse_sha256_block("### Fixed\n- stuff") == {}
        assert _parse_sha256_block("") == {}
        assert _parse_sha256_block(None) == {}

    def test_uppercase_hex_normalized(self):
        body = f"### SHA256\n{'A' * 64}  File.ZIP\n"
        assert _parse_sha256_block(body)["file.zip"] == "a" * 64

    def test_non_hash_lines_ignored(self):
        body = "### SHA256\nnot a hash line\nshort123  file.zip\n"
        assert _parse_sha256_block(body) == {}


class TestExpectedSha256ForUrl:
    def test_matches_url_basename(self):
        url = "https://github.com/r/releases/download/v0.10.5/HainTag-v0.10.5.zip"
        assert _expected_sha256_for_url(SAMPLE_BODY, url) == SAMPLE_HASH

    def test_query_string_stripped(self):
        url = "https://x/HainTag-v0.10.5.zip?token=abc"
        assert _expected_sha256_for_url(SAMPLE_BODY, url) == SAMPLE_HASH

    def test_unknown_file_returns_none(self):
        assert _expected_sha256_for_url(SAMPLE_BODY, "https://x/other.zip") is None

    def test_body_without_block_returns_none(self):
        assert _expected_sha256_for_url("notes only", "https://x/HainTag-v0.10.5.zip") is None

    def test_empty_url_returns_none(self):
        assert _expected_sha256_for_url(SAMPLE_BODY, "") is None


class TestFileSha256:
    def test_matches_hashlib(self, tmp_path):
        f = tmp_path / "blob.bin"
        f.write_bytes(b"hello haintag" * 1000)
        assert _file_sha256(str(f)) == hashlib.sha256(f.read_bytes()).hexdigest()
