import ast
from pathlib import Path

from app.services.ai.client import MIN_RESPONSES_OUTPUT_TOKENS


def test_all_responses_api_literal_token_limits_respect_minimum():
    root=Path(__file__).resolve().parents[1]/"app"
    checked=0
    for path in root.rglob("*.py"):
        tree=ast.parse(path.read_text(encoding="utf-8"))
        for call in (node for node in ast.walk(tree) if isinstance(node,ast.Call)):
            function=call.func
            if not isinstance(function,ast.Attribute) or function.attr not in {"create","parse"}:continue
            for keyword in call.keywords:
                if keyword.arg not in {"max_output_tokens","max_tokens","max_completion_tokens"}:continue
                checked+=1
                value=keyword.value
                if isinstance(value,ast.Constant) and isinstance(value.value,int):
                    assert value.value>=16,f"{path}: {keyword.arg}={value.value} is below the Responses API minimum"
                elif isinstance(value,ast.Name):
                    assert value.id=="MIN_RESPONSES_OUTPUT_TOKENS"
    assert checked==1
    assert MIN_RESPONSES_OUTPUT_TOKENS==16
