from app.services.style_taxonomy import match_style_taxonomy, get_style_taxonomy


def test_match_style_taxonomy_anime_family():
    taxonomy = get_style_taxonomy()
    assert taxonomy.get("families"), "style taxonomy should load families"

    design = {
        "style_name": "史诗悲壮英雄主义动漫风",
        "visual_approach": "传统历史英雄叙事与现代视觉冲击力融合",
    }

    matched = match_style_taxonomy(design)
    assert matched is not None, "should map intelligent style to taxonomy entry"
    assert matched.get("family_key")
    assert matched.get("substyle_key")
    assert isinstance(matched.get("positive_tokens"), list)


def test_match_style_taxonomy_handles_missing_fields():
    design = {"style_description": "极简抽象几何图形"}

    matched = match_style_taxonomy(design)
    assert matched is not None
    assert matched["family_key"]
