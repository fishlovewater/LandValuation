ALLOWED_TOOL_NAMES = {
    "get_case_summary",
    "get_form_requirements",
    "get_missing_items",
    "get_extracted_fields",
    "apply_confirmed_fields",
    "save_form_draft",
    "run_calculation",
    "run_validation",
    "generate_report_pdf",
    "get_nearest_facility",
}


BEDROCK_TOOL_CONFIG = [
    {
        "toolSpec": {
            "name": "get_case_summary",
            "description": "讀取目前案件摘要，不修改資料",
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {"case_id": {"type": "string"}},
                    "required": ["case_id"],
                }
            },
        }
    },
    {
        "toolSpec": {
            "name": "get_form_requirements",
            "description": "取得 F03 必填欄位與文件",
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {"form_type": {"const": "F03"}},
                    "required": ["form_type"],
                }
            },
        }
    },
    {
        "toolSpec": {
            "name": "get_missing_items",
            "description": "取得 F03 目前缺少的欄位與文件",
            "inputSchema": {
                "json": {"type": "object", "properties": {}}
            },
        }
    },
    {
        "toolSpec": {
            "name": "get_extracted_fields",
            "description": "取得 PDF 擷取候選欄位及確認狀態",
            "inputSchema": {
                "json": {"type": "object", "properties": {}}
            },
        }
    },
    {
        "toolSpec": {
            "name": "apply_confirmed_fields",
            "description": "將使用者明確確認的欄位寫入 F03 草稿",
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "fields": {"type": "object"},
                        "candidate_ids": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                    },
                }
            },
        }
    },
    {
        "toolSpec": {
            "name": "save_form_draft",
            "description": "儲存使用者明確確認的 F03 草稿欄位",
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {"fields": {"type": "object"}},
                }
            },
        }
    },
    {
        "toolSpec": {
            "name": "run_calculation",
            "description": "以後端固定 F03_WEIGHTED_PRICE_V1 規則執行計算並保存快照",
            "inputSchema": {"json": {"type": "object", "properties": {}}},
        }
    },
    {
        "toolSpec": {
            "name": "run_validation",
            "description": "執行後端固定 F03 MVP 製作前檢核並回傳修正提示",
            "inputSchema": {"json": {"type": "object", "properties": {}}},
        }
    },
    {
        "toolSpec": {
            "name": "generate_report_pdf",
            "description": "以通過檢核的後端資料產生固定 F03 PDF，不由模型重寫資料",
            "inputSchema": {"json": {"type": "object", "properties": {}}},
        }
    },
    {
        "toolSpec": {
            "name": "get_nearest_facility",
            "description": "依使用者已確認的結構化條件取得最短步行距離候選；不寫入表單",
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {}
                }
            },
        }
    },
]


OLLAMA_TOOL_CONFIG = [
    {
        "type": "function",
        "function": {
            "name": item["toolSpec"]["name"],
            "description": item["toolSpec"]["description"],
            "parameters": item["toolSpec"]["inputSchema"]["json"],
        },
    }
    for item in BEDROCK_TOOL_CONFIG
]
