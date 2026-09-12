from fastapi import FastAPI
from fastapi.openapi.docs import (
    get_swagger_ui_html,
    get_swagger_ui_oauth2_redirect_html,
)
from fastapi.responses import HTMLResponse


INTAKE_JSON_EDITOR_MARKER = "land-valuation-intake-json-editor"

_INTAKE_JSON_EDITOR_STYLE = f"""
<style id="{INTAKE_JSON_EDITOR_MARKER}-style">
  .swagger-ui textarea.{INTAKE_JSON_EDITOR_MARKER} {{
    box-sizing: border-box;
    display: block;
    width: 100%;
    min-height: 22rem;
    padding: 0.9rem 1rem;
    resize: vertical;
    border: 2px solid #41444e;
    border-radius: 6px;
    background: #ffffff;
    color: #263238;
    font: 14px/1.55 ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas,
      "Liberation Mono", "Courier New", monospace;
    tab-size: 2;
    white-space: pre;
  }}

  .swagger-ui textarea.{INTAKE_JSON_EDITOR_MARKER}:focus {{
    border-color: #4990e2;
    outline: 2px solid rgba(73, 144, 226, 0.22);
    outline-offset: 1px;
  }}

  .swagger-ui .{INTAKE_JSON_EDITOR_MARKER}-hint {{
    margin: 0.4rem 0 0;
    color: #4d5b66;
    font-size: 12px;
  }}
</style>
"""

_INTAKE_JSON_EDITOR_SCRIPT = f"""
<script id="{INTAKE_JSON_EDITOR_MARKER}-script">
(() => {{
  const marker = "{INTAKE_JSON_EDITOR_MARKER}";
  const selector = 'input[placeholder="intake_manifest_json"]';
  const nativeValueSetter = Object.getOwnPropertyDescriptor(
    window.HTMLInputElement.prototype,
    "value"
  ).set;

  function enhance(input) {{
    if (input.dataset.intakeJsonEditorBound === "true") return;
    input.dataset.intakeJsonEditorBound = "true";

    const editor = document.createElement("textarea");
    editor.className = marker;
    editor.setAttribute("aria-label", "intake_manifest_json JSON editor");
    editor.setAttribute("rows", "18");
    editor.spellcheck = false;
    try {{
      editor.value = JSON.stringify(JSON.parse(input.value), null, 2);
    }} catch (_error) {{
      editor.value = input.value;
    }}

    const hint = document.createElement("p");
    hint.className = marker + "-hint";
    hint.textContent = "可直接編輯多行 JSON；右下角可拖曳調整高度。";

    editor.addEventListener("input", () => {{
      nativeValueSetter.call(input, editor.value);
      input.dispatchEvent(new Event("input", {{ bubbles: true }}));
      input.dispatchEvent(new Event("change", {{ bubbles: true }}));
    }});

    input.hidden = true;
    input.setAttribute("aria-hidden", "true");
    input.tabIndex = -1;
    input.parentElement.insertBefore(editor, input);
    input.parentElement.appendChild(hint);
  }}

  function enhanceAll() {{
    document.querySelectorAll(selector).forEach(enhance);
  }}

  new MutationObserver(enhanceAll).observe(document.body, {{
    childList: true,
    subtree: true,
  }});
  enhanceAll();
}})();
</script>
"""


def register_swagger_docs(application: FastAPI, *, title: str) -> None:
    @application.get("/docs", include_in_schema=False)
    async def custom_swagger_ui_html() -> HTMLResponse:
        response = get_swagger_ui_html(
            openapi_url=application.openapi_url,
            title=f"{title} - Swagger UI",
            oauth2_redirect_url=application.swagger_ui_oauth2_redirect_url,
            swagger_ui_parameters=application.swagger_ui_parameters,
        )
        content = response.body.decode("utf-8")
        content = content.replace(
            "</head>", f"{_INTAKE_JSON_EDITOR_STYLE}</head>", 1
        )
        content = content.replace(
            "</body>", f"{_INTAKE_JSON_EDITOR_SCRIPT}</body>", 1
        )
        return HTMLResponse(content=content)

    if application.swagger_ui_oauth2_redirect_url:
        @application.get(
            application.swagger_ui_oauth2_redirect_url,
            include_in_schema=False,
        )
        async def swagger_ui_redirect() -> HTMLResponse:
            return get_swagger_ui_oauth2_redirect_html()
