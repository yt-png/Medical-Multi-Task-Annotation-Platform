def _validate_field(field_name: str, value: str):
    if "/" in value or "\\" in value:
        raise ValueError(f"{field_name} 不得包含路径字符: {value}")

    if value.strip() == "":
        raise ValueError(f"{field_name} 不得为空字符串")

def build_sample_id(
    check_category: str,
    case_id: str,
    image_id: str,
    schema_version: str = "v1"
) -> str:
    if not all(isinstance(x, str) and x.strip() for x in [check_category, case_id, image_id]):
        raise ValueError("sample_id fields must be non-empty strings")

    if schema_version != "v1":
        raise ValueError("sample_id 仅支持 v1")

    check_category = check_category.strip()
    case_id = case_id.strip()
    image_id = image_id.strip()

    _validate_field("check_category", check_category)
    _validate_field("case_id", case_id)
    _validate_field("image_id", image_id)

    for field_name, value in [
        ("check_category", check_category),
        ("case_id", case_id),
        ("image_id", image_id),
    ]:
        if "/" in value or "\\" in value:
            raise ValueError(f"{field_name} 不得包含路径字符: {value}")

    return f"{check_category}_{case_id}_{image_id}"