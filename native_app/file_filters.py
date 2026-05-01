from __future__ import annotations


def image_filter(translator, *, include_gif: bool = False, all_files: bool = False) -> str:
    if include_gif:
        return translator.t("file_filter_images_gif")
    if all_files:
        return translator.t("file_filter_images_all")
    return translator.t("file_filter_images")


def png_filter(translator, *, all_files: bool = True) -> str:
    return translator.t("file_filter_png_all" if all_files else "file_filter_png")


def json_filter(translator) -> str:
    return translator.t("file_filter_json")


def config_filter(translator) -> str:
    return translator.t("file_filter_haintag_config")


def ttf_filter(translator) -> str:
    return translator.t("file_filter_ttf")


def python_filter(translator) -> str:
    return translator.t("file_filter_python")
