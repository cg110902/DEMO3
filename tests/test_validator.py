"""mini schema 校验器的行为边界：报错要带路径、要能抓住结构违规。"""
from engine import validator


def test_basic_types_and_required():
    schema = {"type": "object", "required": ["a", "b"],
              "properties": {"a": {"type": "integer"}, "b": {"type": "string"}}}
    assert validator.validate({"a": 1, "b": "x"}, schema) == []
    errs = validator.validate({"a": "no", "b": 3}, schema)
    assert any("$.a" in e and "integer" in e for e in errs)
    assert any("$.b" in e for e in errs)
    errs = validator.validate({"a": 1}, schema)
    assert any("缺少必填字段 b" in e for e in errs)


def test_bool_is_not_integer_enum_pattern():
    schema = {"properties": {"n": {"type": "integer"}, "s": {"enum": ["x", "y"]}, "c": {"pattern": r"ch_\d{3,}"}}}
    errs = validator.validate({"n": True, "s": "z", "c": "ch_12"}, schema)
    assert any("integer" in e for e in errs)
    assert any("∈" in e for e in errs)
    assert any("ch_\\d" in e or "不匹配" in e for e in errs)


def test_array_items_and_additional_properties():
    schema = {"type": "array", "items": {"type": "object", "required": ["id"],
                                         "additionalProperties": False,
                                         "properties": {"id": {"type": "string"}}}}
    assert validator.validate([{"id": "a"}], schema) == []
    errs = validator.validate([{"id": 1, "oops": 2}], schema)
    assert any("[0].id" in e for e in errs)
    assert any("不允许的字段 oops" in e for e in errs)


def test_nested_additional_properties_schema():
    schema = {"type": "object", "additionalProperties": {"type": "integer"}}
    assert validator.validate({"a": 1, "b": 2}, schema) == []
    assert len(validator.validate({"a": 1, "b": "x"}, schema)) == 1
