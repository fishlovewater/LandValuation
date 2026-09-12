# 估價表單 AI 欄位辨識規則

> 規則版本：`field-rules-md-v2`
>
> 本文件由目前專案採用的 6 份表單／欄位規格 Excel 整理而成，供 OCR 後的 AI 欄位辨識與 Codex 候選匯入共同使用。

## 使用範圍與資料來源

| 表單代碼 | 規格來源 | AI 辨識用途 |
|---|---|---|
| F01 | 買賣實例調查估價表_建物全部層數_AI_Coding欄位規格.xlsx | 實例資料、輸出欄位、技術欄位與建物全層數計算規則 |
| F02 | 比較法調查估價表.xlsx | 比較法調查估價表欄位與比較價格計算流程 |
| F02-RF | 影響地價區域因素分析明細表_商業用地.xlsx、計分表.pdf（新北市樹林區普通住宅用地） | 區域因素原文、住宅用地分級與後續比較法調整依據 |
| F03 | 比準地地價估計表.xlsx | 比準地地價估計表欄位、比準地價格與輸出規則 |
| F04 | 徵收土地宗地市價估計表.xlsx | 徵收土地宗地市價估計表、比準地與宗地欄位 |
| S01 | 地價區段勘查表.xlsx | 地價區段勘查欄位、選項、單位與區段資料來源 |

欄位 catalog 是系統送入 AI 的白名單。AI 只能從目前表單章節的 `field_name` 中選擇，不得建立新欄位。欄位說明同時提供語意、常見來源、擷取／計算方式、單位或檢核條件。

## 通用辨識規則

1. 先判斷 OCR 文字、表格工作表或段落所屬的正式表單與資料角色，再套用對應表單章節。
2. 可辨識簡稱、同義詞、非標準標題、表格欄位與段落敘述，但最後只能對應到本文件列出的 `field_name`。
3. `source_text` 必須是 OCR 文字中真實存在的連續或近乎連續原文，保留原始標點與換行；不可自創證據。
4. `extracted_value` 必須能在 `source_text` 中直接找到。不可自行改寫日期、補零、合併不連續儲存格，或把推算結果當作原文值。
5. 文件沒有提到的欄位不要回傳。缺少資料時保持空白，不要以常識、範例值、UUID 或其他案件資料補值。
6. 欄位描述標示「後端計算」或「系統產生」時，AI 不得輸出計算結果作為原始候選；只可擷取計算所需的輸入證據。
7. 欄位描述標示「人工確認／人工判斷」時，AI 可以提出有原文依據的候選，但必須保留候選狀態交由人員確認。
8. 同一 `field_name` 在不同文件或頁次出現不同值時，全部保留為候選，不可覆蓋；由人員選擇一筆，其餘拒絕。
9. `confidence` 必須介於 0 與 1；信心分數不得取代原文證據。
10. 百分比、金額、面積、距離、日期與地號保留原文單位和格式；標準化或正式計算由後端依規則處理。
11. F01 僅接受明確屬於買賣實例調查估價表、比較標的或比較實例的來源段落；不可使用徵收宗地、比準地、區域因素或其他表單資料。
12. F02-RF 可回傳自然語言觀察值或明確的 `L1`～`L7` 等級；自然語言到等級的轉換必須依發布中的規則版本處理。只有適用範圍、因素、單位與級距都能由來源原文直接確認時，才可依計分表導出等級；來源原文必須完整保留在 `source_text`，不可把推導等級當作 OCR 原文。
13. 輸出只能是合法 JSON：`{"candidates": [...]}`，不得輸出 Markdown、解釋文字或未列出的欄位。

## 跨表單資料角色

| 資料角色 | 主要表單 | 使用原則 |
|---|---|---|
| 買賣實例／比較標的 | F01 | 提供交易、土地、建物、成本、折舊與正常買賣價格的原始證據；F01 不得引用其他表單的宗地或比準地資料。 |
| 比較法計算 | F02 | 引用比較標的的正常單價、日期、區段及調整資料；精確計算由後端完成。 |
| 區域因素 | F02-RF | 使用商業或住宅用地的適用區域因素規則；保留觀察原文，正式等級／調整率由規則版本處理。 |
| 比準地 | F03 | 引用比準地資料、比較法結果及版本關聯；不可自行創造比準地價格。 |
| 徵收宗地 | F04 | 引用宗地、比準地及個別因素資料；差異率與市價由後端或人工確認。 |
| 地價區段勘查 | S01 | 引用行政、道路、公共設施、環境與特殊設施觀察；選項、距離、百分比及空白狀態依欄位說明處理。 |

## 跨表單候選欄位路由

以下路由是 AI 可將「已確認來源角色」的原文提出為另一張表單候選的唯一例外。未列於此表的跨表單搬值一律禁止；候選仍須保留原文件原文、頁碼並經人工確認。目標表單自己的正式表單區段，仍可使用該表單全部可辨識欄位。

| 來源角色 | 目標表單 | 允許 `field_name` | 使用條件 |
|---|---|---|---|
| `F01` | `F02` | `instance_no`, `transaction_date`, `normal_land_unit_price`, `price_zone_no` | 買賣實例表中須明確標示實例、交易日期、土地正常單價或同一區段號；僅作比較標的候選。 |
| `S01` | `F02` | `price_zone_no`, `valuation_base_date` | 地價區段勘查表中須有相同案件／區段的明確資料。 |
| `F02` | `F03` | `comparison_price`, `comparison_price_raw`, `valuation_base_date` | 比較法調查估價表須已有可核對的比較結果或估價基準日。 |
| `S01` | `F03` | `price_zone_no`, `district_name`, `valuation_base_date` | 僅引用同一區段的行政區、區段號或估價基準日。 |

## F01

本章節共有 26 個 AI 可辨識欄位。

| field_name | 欄位特徵、來源、輸入／計算與檢核 |
|---|---|
| `accumulated_depreciation_raw` | 累積折舊額精確值；重建成本、殘價率、耐用年數及已經歷年數；後端計算；保留精度 |
| `adoption_status_reason` | 案例是否採用及理由；查估人員；人工判斷；採用／僅供參考／不採用；不輸出原表欄位 |
| `approval_fields` | 填寫日期及簽章；簽核流程；流程產生；依原表5個表尾位置輸出 |
| `building_cost_total_raw` | 建物成本價格總價精確值；建物成本單價×扣除車位後計算面積；後端計算；全部層數範本使用 |
| `calculation_building_area` | 實例計算面積(扣除車位)；登記面積－車位面積；後端計算；不得為負；與建物成本總價計算一致 |
| `capital_components` | 各資金來源利率及比例；交易當月建築融資等資料；人工輸入；資金比例合計100% |
| `capital_interest_rate_raw` | 資本利息綜合利率精確值；Σ利率×資金比例；後端計算；保留精度；正式表輸出顯示值 |
| `case_and_instance_refs` | 年期、區段號、實例編號；案件、地價區段及案例編號規則；引用／編碼；年期7碼；同年期同區案例編號不可重複 |
| `construction_cost_standard_ref` | 營造施工費標準及版本；全聯會第4號公報或新北市適用標準；引用／查表；另存標準版本與適用地區 |
| `construction_period_years` | 建築工期；建照／使照及建管規定；計算後確認；供資本投入年數調整 |
| `construction_unit_adjustment` | 調整單價率及理由；時點、區位、基本資料及個案修正；人工判斷；原表備註應敘明 |
| `cost_components_raw` | 各成本費率與精確金額；適用標準、費率及計算結果；查表／後端計算；正式表輸出各費率與金額；內部保留未四捨五入值 |
| `depreciation_standard_ref` | 耐用年數及殘價率標準版本；全聯會第4號公報及個案實況；引用後人工確認；正式表只輸出年數、方法與殘價率 |
| `elapsed_years_raw` | 已經歷年數精確值；建築完成年月至交易日期；後端計算；正式表輸出顯示值 |
| `land_area` | 實例土地面積；土地登記資料；引用；全部層數版本分母 |
| `land_price_raw` | 實例土地價格精確值；正常買賣總價格－建物成本總價；後端計算；不得把車位重複扣除 |
| `normal_land_unit_price_raw` | 土地正常買賣單價精確值；實例土地價格÷土地面積；後端計算；供比較法後續計算 |
| `normal_total_price_raw` | 正常買賣總價格精確值；原始總價經各項修正；後端計算；未能有效掌握及量化時案例不採用 |
| `parking_area` | 車位面積；建物登記／交易資料；人工確認／計算；完成扣除車位計算所必需；不得增加到正式表 |
| `parking_price` | 車位價格；交易資料／市場拆分；人工確認；從房地價及建物成本範圍一致扣除 |
| `property_registry_fields` | 門牌、坐落、建號及樓層；土地及建物登記資料；引用後人工確認；多筆土地或建號以代表筆輸出，其餘寫入備註 |
| `registered_building_area` | 實例登記面積；建物登記資料；引用；M² |
| `source_document_versions` | 資料來源及版本；實價、地籍、標準與規則庫；系統記錄；供審查回溯 |
| `special_transaction_codes` | 第7、8條特殊情況代碼；案例訪查與法規判斷；人工判斷；每項須可對應正式修正說明與修正數 |
| `structure_type` | 主要構造種類；建物登記／現況調查；引用後人工確認；需對應適用營造施工費與耐用年數標準 |
| `transaction_total_price` | 原始買賣總價格；實價登錄、契約及訪查；引用後查證；須與交易資料相符 |

## F02

本章節共有 26 個 AI 可辨識欄位。

| field_name | 欄位特徵、來源、輸入／計算與檢核 |
|---|---|
| `absolute_adjustment_total` | 調整百分率絕對值加總；日期、區域、個別因素調整率；後端計算；逐項先取絕對值再相加 |
| `adjusted_unit_price_display` | 調整至估價基準日單價；精確值；後端格式化；不可用已顯示四捨五入值繼續後算 |
| `adjusted_unit_price_raw` | 調整後正常單價精確值；正常單價×(1+日期調整率)；後端計算；內部保留精度，顯示時再依表規則處理 |
| `approval_fields` | 簽章與填寫日期；簽核流程；流程產生；保存人員ID與時間 |
| `basic_description` | 基本資料；宗地清冊/實例表；引用；地址或土地標示 |
| `benchmark_comparison_price` | 比準地比較價格；精確加權值；後端計算；四捨五入至個位數 |
| `benchmark_comparison_price_raw` | 比準地比較價格精確值；Σ試算價格精確值×權重；後端計算；內部保留精度 |
| `case_no` | 案號；案件資料；引用；同案唯一 |
| `case_note` | 全案備註；查估人員；人工輸入；全案一格 |
| `comparison_weight` | 比較標的權重；可信度與相近程度；人工決定；使用中比較標的權重合計100% |
| `date_adjustment_rate` | 價格日期調整率；指數或市場資料；人工判斷/計算；保存指數來源與期間 |
| `individual_factor_condition` | 個別因素條件；宗地清冊/實例表；引用後確認；依原表25項及其他 |
| `individual_factor_rate` | 個別因素差異率；新北市個別因素評價基準；查表/人工確認；免修正用-；差異為零用0，兩者不同 |
| `individual_factor_total` | 個別因素合計；各個別因素差異率；後端計算；每比較標的一筆 |
| `instance_no` | 實例編號；買賣或收益實例；引用；比較標的1～3 |
| `normal_land_unit_price` | 土地正常單價；買賣實例調查估價表；引用；使用未四捨五入原值計算 |
| `parcel_serial_no` | 宗地流水號；宗地個別因素清冊；引用；特定公保地比準地可免填 |
| `price_zone_no` | 地價區段號；地價區段勘查表；引用；四個標的均有 |
| `regional_factor_rate` | 區域因素調整率；區域因素分析明細表；引用；與前表總修正數一致 |
| `similarity_level` | 價格形成因素相近程度；絕對值加總＋資料可信度；人工判斷；不能只依數字自動決定 |
| `subject_note` | 標的備註；查估人員；人工輸入；四個標的各一格 |
| `subject_role` | 標的角色；系統結構；系統產生；benchmark/c1/c2/c3 |
| `transaction_date` | 交易日期；買賣實例調查估價表；引用；不得晚於估價基準日 |
| `trial_price` | 試算價格；精確值；後端格式化；依表輸出 |
| `trial_price_raw` | 試算價格精確值；調整後正常單價×(1+區域因素率+個別因素合計)；後端計算；使用未四捨五入值 |
| `valuation_base_date` | 估價基準日；案件資料；引用；同案一致 |

## F02-RF

本章節共有 29 個 AI 可辨識欄位。

| 順序 | 分類 | 來源項目 | 欄位特徵／標籤 | 依據 |
|---:|---|---|---|---|
| 1 | 土地使用管制 | C1_01 | 都市計畫（內、外） | 土地徵收補償市價查估作業手冊／伍、五（手冊頁41-45、修正操作說明）；表5-2商業用地範本 |
| 2 | 土地使用管制 | C1_02 | 使用分區（使用地類別） | 土地徵收補償市價查估作業手冊／伍、五（手冊頁41-45、修正操作說明）；表5-2商業用地範本 |
| 3 | 土地使用管制 | C1_03 | 建蔽率 | 土地徵收補償市價查估作業手冊／伍、五（手冊頁41-45、修正操作說明）；表5-2商業用地範本 |
| 4 | 土地使用管制 | C1_04 | 容積率 | 土地徵收補償市價查估作業手冊／伍、五（手冊頁41-45、修正操作說明）；表5-2商業用地範本 |
| 5 | 土地使用管制 | C1_05 | 有無禁止建築 | 土地徵收補償市價查估作業手冊／伍、五（手冊頁41-45、修正操作說明）；表5-2商業用地範本 |
| 6 | 土地使用管制 | C1_06 | 有無限制建築（整體開發、面積限制、高度限制……等） | 土地徵收補償市價查估作業手冊／伍、五（手冊頁41-45、修正操作說明）；表5-2商業用地範本 |
| 7 | 交通運輸 | C2_01 | 主要道路寬度 | 土地徵收補償市價查估作業手冊／伍、五（手冊頁41-45、修正操作說明）；表5-2商業用地範本 |
| 8 | 交通運輸 | C2_02 | 區段內道路平均寬度 | 土地徵收補償市價查估作業手冊／伍、五（手冊頁41-45、修正操作說明）；表5-2商業用地範本 |
| 9 | 交通運輸 | C2_03 | 接近大型車站之程度 | 土地徵收補償市價查估作業手冊／伍、五（手冊頁41-45、修正操作說明）；表5-2商業用地範本 |
| 10 | 交通運輸 | C2_04 | 站牌之接近程度或密集程度 | 土地徵收補償市價查估作業手冊／伍、五（手冊頁41-45、修正操作說明）；表5-2商業用地範本 |
| 11 | 交通運輸 | C2_05 | 交流道之有無及接近交流道之程度 | 土地徵收補償市價查估作業手冊／伍、五（手冊頁41-45、修正操作說明）；表5-2商業用地範本 |
| 12 | 交通運輸 | C2_06 | 區段內道路規劃及闢建程度 | 土地徵收補償市價查估作業手冊／伍、五（手冊頁41-45、修正操作說明）；表5-2商業用地範本 |
| 13 | 自然條件 | C3_01 | 排水之良否 | 土地徵收補償市價查估作業手冊／伍、五（手冊頁41-45、修正操作說明）；表5-2商業用地範本 |
| 14 | 自然條件 | C3_02 | 地勢 | 土地徵收補償市價查估作業手冊／伍、五（手冊頁41-45、修正操作說明）；表5-2商業用地範本 |
| 15 | 公共建設 | C4_01 | 接近市場之程度（傳統市場、超級市場、超大型購物中心） | 土地徵收補償市價查估作業手冊／伍、五（手冊頁41-45、修正操作說明）；表5-2商業用地範本 |
| 16 | 公共建設 | C4_02 | 接近公園（里鄰公園、一般公園）、廣場、徒步區之程度 | 土地徵收補償市價查估作業手冊／伍、五（手冊頁41-45、修正操作說明）；表5-2商業用地範本 |
| 17 | 公共建設 | C4_03 | 接近觀光遊憩設施之程度 | 土地徵收補償市價查估作業手冊／伍、五（手冊頁41-45、修正操作說明）；表5-2商業用地範本 |
| 18 | 公共建設 | C4_04 | 停車場地之便利程度 | 土地徵收補償市價查估作業手冊／伍、五（手冊頁41-45、修正操作說明）；表5-2商業用地範本 |
| 19 | 特殊設施 | C5_01 | 電業設施及公用氣體燃料設施之有無及接近程度 | 土地徵收補償市價查估作業手冊／伍、五（手冊頁41-45、修正操作說明）；表5-2商業用地範本 |
| 20 | 特殊設施 | C5_02 | 殯葬設施之有無及接近程度 | 土地徵收補償市價查估作業手冊／伍、五（手冊頁41-45、修正操作說明）；表5-2商業用地範本 |
| 21 | 特殊設施 | C5_03 | 廢棄物處理設施之有無及接近程度 | 土地徵收補償市價查估作業手冊／伍、五（手冊頁41-45、修正操作說明）；表5-2商業用地範本 |
| 22 | 環境污染 | C6_01 | 水污染、噪音污染、廢氣污染、廢棄物污染等之有無及接近程度 | 土地徵收補償市價查估作業手冊／伍、五（手冊頁41-45、修正操作說明）；表5-2商業用地範本 |
| 23 | 工商活動 | C7_01 | 百貨公司之有無、數量、接近程度 | 土地徵收補償市價查估作業手冊／伍、五（手冊頁41-45、修正操作說明）；表5-2商業用地範本 |
| 24 | 工商活動 | C7_02 | 金融機構之有無、數量、接近程度 | 土地徵收補償市價查估作業手冊／伍、五（手冊頁41-45、修正操作說明）；表5-2商業用地範本 |
| 25 | 工商活動 | C7_03 | 娛樂設施之有無、數量、接近程度 | 土地徵收補償市價查估作業手冊／伍、五（手冊頁41-45、修正操作說明）；表5-2商業用地範本 |
| 26 | 工商活動 | C7_04 | 大型展示中心或觀光飯店之有無、數量、接近程度 | 土地徵收補償市價查估作業手冊／伍、五（手冊頁41-45、修正操作說明）；表5-2商業用地範本 |
| 27 | 工商活動 | C7_05 | 顧客通行量之多寡 | 土地徵收補償市價查估作業手冊／伍、五（手冊頁41-45、修正操作說明）；表5-2商業用地範本 |
| 28 | 工商活動 | C7_06 | 店舖之毗連狀態 | 土地徵收補償市價查估作業手冊／伍、五（手冊頁41-45、修正操作說明）；表5-2商業用地範本 |
| 29 | 其他影響因素 | C8_01 | 其他影響因素 | 土地徵收補償市價查估作業手冊／伍、五（手冊頁41-45、修正操作說明）；表5-2商業用地範本 |

F02-RF 的實際 AI `field_name` 由系統依 `TEMPLATE_FACTORS` 與本章來源項目順序配對產生；AI 必須回傳該配對後的代碼，不得回傳自訂名稱。

### F02-RF canonical `field_name` 對照表

以下是 F02-RF 唯一允許回傳的欄位名稱。`來源項目` 是文件中的項目代碼，`field_name` 是 API、資料庫與候選確認畫面使用的 canonical 名稱；兩者不可互換。

| 順序 | 來源項目 | canonical `field_name` |
|---:|---|---|
| 1 | `C1_01` | `urban_plan_status` |
| 2 | `C1_02` | `land_use_zone` |
| 3 | `C1_03` | `building_coverage_rate` |
| 4 | `C1_04` | `floor_area_ratio` |
| 5 | `C1_05` | `prohibited_building` |
| 6 | `C1_06` | `restricted_building` |
| 7 | `C2_01` | `main_road_width` |
| 8 | `C2_02` | `average_road_width` |
| 9 | `C2_03` | `mass_transit_proximity` |
| 10 | `C2_04` | `station_proximity` |
| 11 | `C2_05` | `interchange_proximity` |
| 12 | `C2_06` | `road_plan` |
| 13 | `C3_01` | `drainage` |
| 14 | `C3_02` | `terrain` |
| 15 | `C4_01` | `market_proximity` |
| 16 | `C4_02` | `park_proximity` |
| 17 | `C4_03` | `tourist_facility_proximity` |
| 18 | `C4_04` | `parking_convenience` |
| 19 | `C5_01` | `power_gas_facility` |
| 20 | `C5_02` | `funeral_facility` |
| 21 | `C5_03` | `waste_facility` |
| 22 | `C6_01` | `environmental_pollution` |
| 23 | `C7_01` | `department_store` |
| 24 | `C7_02` | `financial_institution` |
| 25 | `C7_03` | `entertainment_facility` |
| 26 | `C7_04` | `exhibition_hotel` |
| 27 | `C7_05` | `pedestrian_flow` |
| 28 | `C7_06` | `vacancy_rate` |
| 29 | `C8_01` | `other` |


### 住宅用地計分規則：新北市樹林區普通住宅用地

來源：計分表.pdf，頁碼 4-26 至 4-34，標題為「新北市樹林區普通住宅用地影響地價區域因素評價基準明細表」。本節只適用於 **案件土地用途為住宅用地**，且案件或來源原文可確認為 **新北市樹林區** 的普通住宅用地。不得將本節套用至商業用地、其他行政區或用途／地區未明的文件。

1. AI 先擷取可逐字核對的觀察原文、距離、百分比或設施名稱；source_text 不得含有 AI 改寫的級別或算式。
2. 僅當原文能無歧義落入下列級距時，F02-RF 候選的 extracted_value 可回傳推導等級。五級因素使用：L1=優、L2=稍優、L3=普通、L4=稍劣、L5=劣。二級因素使用 L1=優、L5=劣；三級因素使用 L1=優、L3=普通、L5=劣。七級「其他影響因素」使用 L1=極優 至 L7=極劣。
3. 若原文只說「附近」、「便利」、「良好」而未提供可比對的距離、數量、百分比或明確級別，不可推導 L 等級，須回傳原文觀察值並保留待人工確認。
4. 正式區域因素修正率以同一發布規則版本的「目標區段」與「比準／比較區段」等級矩陣計算；不得把單一區段的等級直接當作百分比。五級矩陣的相鄰級距依各因素規定之步距累加；正式計算由後端在比準地與比較標的均已確認後執行。

| F02-RF field_name | 對應 S01 觀察欄位 | 優／稍優／普通／稍劣／劣級距 | 相鄰級距（百分點） |
|---|---|---|---:|
| urban_plan_status | urban_plan_scope | 都市計畫內／都市計畫外（兩級） | 20 |
| land_use_zone | land_use_zone_category | 商業區、捷運用地（聯開）／住宅區、市場用地／甲建、乙建、特定專用區、多目標使用之其他公共設施用地／工業區、丙建、丁建／其他可建築用地 | 5 |
| building_coverage_rate | building_coverage_ratio | ≥80%／70%–<80%／60%–<70%／50%–<60%／<50% | 2.5 |
| floor_area_ratio | floor_area_ratio | ≥460%／360%–<460%／260%–<360%／180%–<260%／<180% | 6.25 |
| prohibited_building | building_prohibition_status | 無禁止建築／有禁止建築（兩級） | 50 |
| restricted_building | building_restriction_status、building_restriction_details | 無限制建築／部分限制（如高度或面積）／限制整體開發 | 25 |
| main_road_width | main_road_width_m | ≥28m／20–<28m／12–<20m／8–<12m／<8m | 3.75 |
| average_road_width | average_internal_road_width_m | ≥20m／15–<20m／10–<15m／8–<10m／<8m | 3 |
| mass_transit_proximity | major_station_location_scope、major_station_distance_m | 區段內或<500m／500–<1000m／1000–<1500m／1500–<2000m／≥2000m或無 | 2.5 |
| station_proximity | bus_stop_comparison_mode、bus_stop_location_scope、bus_stop_distance_m、bus_stop_density_level | 接近程度：區段內或<200m／200–<400m／400–<600m／600–<800m／≥800m或無；密集程度須依同案選定方式另行人工確認 | 1 |
| interchange_proximity | interchange_location_scope、interchange_distance_m | 區段內或<1000m／1000–<2000m／2000–<3000m／3000–<4000m／≥4000m或無 | 1 |
| road_plan | road_planning_development_level | 全部規劃及開闢／大部分規劃及開闢／部分規劃及開闢／砂石路／全無規劃及開闢 | 2.5 |
| drainage | drainage_level | 極完善／非常完善／普通完善／不良／極不良 | 2.5 |
| terrain | terrain_level | 極平坦堅硬／平坦／緩傾斜地／低地、濕地／地勢孤兀地 | 2.5 |
| market_proximity | public_facility_type、public_facility_location_scope、public_facility_distance_m | 區段內或<300m／300–<500m／500–<800m／800–<1000m／≥1000m或無 | 2 |
| park_proximity | public_facility_type、public_facility_location_scope、public_facility_distance_m | 區段內或<300m／300–<500m／500–<800m／800–<1000m／≥1000m或無 | 2 |
| tourist_facility_proximity | public_facility_type、public_facility_location_scope、public_facility_distance_m | 區段內或<500m／500–<1000m／1000–<1500m／1500–<2000m／≥2000m或無 | 1.5 |
| parking_convenience | public_facility_type、public_facility_location_scope、public_facility_distance_m | 區段內或<200m／200–<400m／400–<600m／600–<1000m／≥1000m或無 | 1.5 |
| power_gas_facility | special_facility_type、special_facility_location_scope、special_facility_distance_m | ≥2000m或無／1500–<2000m／1000–<1500m／500–<1000m／區段內或<500m | 2.5 |
| funeral_facility | special_facility_type、special_facility_location_scope、special_facility_distance_m | ≥2000m或無／1500–<2000m／1000–<1500m／500–<1000m／區段內或<500m | 2.5 |
| waste_facility | special_facility_type、special_facility_location_scope、special_facility_distance_m | ≥2000m或無／1500–<2000m／1000–<1500m／500–<1000m／區段內或<500m | 3.75 |
| environmental_pollution | pollution_type、pollution_location_scope、pollution_distance_m | ≥2000m或無／1500–<2000m／1000–<1500m／500–<1000m／區段內或<500m | 5 |
| other | other_factor_name、other_factor_description | 極優／優／稍優／普通／稍劣／劣／極劣；須具體說明因素、方向與依據 | 3.33 |

下列計分表因素目前尚未有獨立 F02-RF canonical field_name，AI 不得為它們創造欄位代碼；應先保留在相對應的 S01 原始觀察欄位，待住宅用地 F02-RF 範本欄位擴充後再納入正式區域因素計算：日照、景觀、傾斜度、建築基地改良、農地改良、學校接近程度、服務性設施接近程度、電力資源、產業用水及設施、污廢水及廢棄物處理設施、顧客通行量、店鋪毗連狀態、建築密度、建築型態與土地利用現況。

### 個別因素計分規則（F02，住宅用地）

計分表.pdf 第 4-31 至 4-34 另列宗地個別因素。AI 對 F02 只可擷取宗地／比較標的原文條件，正式差異率必須在比準地與比較標的均有確認值後依同一矩陣計算。主要級距如下：面積（≥600、400–<600、200–<400、50–<200、<50 平方公尺）；寬度（≥20、15–<20、8–<15、4–<8、<4 公尺）；深度（14–<30、30–<40、7–<14 或 40–<50、50–<60、<7 或 ≥60 公尺）；形狀（方形／梯形、不規則形／長條形）；臨街（≥3面、路角、雙面、單面、未臨街）；道路種類（主要道路、次要道路、巷道、農路、無）；面前道路寬度（≥20、12–<20、8–<12、5–<8、<5或無公尺）；接近校園、傳統市場、公園廣場、車站、商圈及嫌惡設施均依 PDF 指定距離區間；使用分區、建蔽率、容積率、禁限建與其他應依本節上方相同的住宅用地級距或 PDF 第 4-33、4-34 的個別因素矩陣判定。

## F03

本章節共有 24 個 AI 可辨識欄位。

| field_name | 欄位特徵、來源、輸入／計算與檢核 |
|---|---|
| `approval_fields` | 填寫日期及簽章；簽核流程；流程產生；正式輸出只顯示原表5個表尾位置 |
| `benchmark_land_id` | 比準地ID；系統關聯；系統產生；串接宗地、區段及兩種估價結果 |
| `benchmark_land_price` | 比準地地價；加權估值精確值依第21條進位；後端計算；無條件進位，不是四捨五入 |
| `case_no` | 案號；案件資料；引用；同案唯一 |
| `comparison_price` | 比較價格；比較法調查估價表結果；引用／格式化；元/M² |
| `comparison_price_raw` | 比較價格精確值；比較法調查估價表；引用；保存上游未提早進位值；若上游正式結果僅有整數，另保存其版本 |
| `comparison_result_version_id` | 比較法結果來源版本；比較法表版本；系統記錄；供回溯，不得輸出 |
| `comparison_weight` | 比較價格權重；估價人員綜合評估；人工決定；0%～100% |
| `decision_reason` | 決定理由；估價人員；人工輸入；須具體說明資料可信度、相近程度及權重 |
| `district_name` | 鄉鎮市區；宗地清冊／地籍資料；引用；不可只存顯示合併字串 |
| `income_method_status` | 收益法適用狀態；查估判斷；人工確認；適用／不適用／無足夠資料；不可只以0判斷 |
| `income_price` | 收益價格；收益法調查估價表結果；引用／格式化；未採收益法輸出－ |
| `income_price_raw` | 收益價格精確值；收益法調查估價表；引用；未採用時為null，不得存0冒充價格 |
| `income_result_version_id` | 收益法結果來源版本；收益法表版本；系統記錄；供回溯，不得輸出 |
| `income_weight` | 收益價格權重；估價人員綜合評估；人工決定；0%～100% |
| `land_no` | 地號；宗地清冊／地籍資料；引用；保留原始地號文字 |
| `parcel_serial_no` | 宗地流水號；宗地個別因素清冊；引用；公保地毗鄰非公保地區段選取之比準地得免編 |
| `price_zone_no` | 區段號；地價區段勘查表；引用；須與比準地所在區段一致 |
| `rounding_increment` | 尾數級距；查估辦法第21條；後端判定；1／10／100／1000元 |
| `rounding_rule_version` | 計算規則版本；法規規則庫；系統記錄；保存計算當時適用規則 |
| `section_subsection_name` | 段小段名稱；宗地清冊／地籍資料；引用；段與小段可分欄儲存、輸出時合併 |
| `valuation_base_date` | 估價基準日；案件資料；引用；同案一致 |
| `weight_total` | 權重合計；兩種方法權重；後端計算；必須等於100% |
| `weighted_value_raw` | 加權估值精確值；兩種估值×各自權重；後端計算；內部保留精度，不輸出 |

## F04

本章節共有 17 個 AI 可辨識欄位。

| field_name | 欄位特徵、來源、輸入／計算與檢核 |
|---|---|
| `approval_fields` | 填寫日期與簽章；簽核流程；流程產生；依原表5個位置輸出 |
| `benchmark_land_id` | 比準地關聯；比準地地價估計表／宗地清冊；引用；流水號、基本資料及價格均須一致 |
| `case_no` | 案號；案件資料；引用；同案唯一 |
| `case_note` | 全案備註；查估人員；人工輸入；免比較、通案容積率或其他規則 |
| `factor_condition_value` | 因素條件值；宗地個別因素清冊；引用後確認；20項；免比較項目保留狀態 |
| `factor_difference_rate` | 差異率；新北市個別因素評價基準；查表／人工確認；數值0與免修正－不可混用 |
| `factor_standard_version_id` | 差異率來源版本；評價基準版本；系統記錄；供回溯 |
| `page_parcel_serials` | 頁面宗地清單；分頁結果；系統產生；每頁最多5筆宗地 |
| `pagination` | 頁碼與總頁數；輸出引擎；系統產生；正式表每頁5筆宗地 |
| `parcel_id` | 宗地關聯；宗地個別因素清冊；引用；每筆宗地一筆，不受正式表5欄限制 |
| `parcel_market_price` | 宗地市價；試算精確值依第21條進位；後端計算；無條件進位，不是四捨五入 |
| `parcel_note` | 宗地個別備註；查估人員；人工輸入；說明分割前條件、特殊修正等 |
| `pre_split_conditions` | 分割前宗地條件；地籍沿革／需用土地人資料；人工確認；面積、形狀、臨街及寬深度評價需要時使用並於備註輸出 |
| `rounding_increment` | 尾數進位級距；查估辦法第21條；後端判定；1／10／100／1000元 |
| `source_and_rule_versions` | 來源快照與計算版本；清冊、比準地表、基準及規則庫；系統記錄；避免上游修改無紀錄 |
| `total_adjustment_rate_raw` | 總調整率精確值；各數值差異率；後端計算；免修正項目不參與加總 |
| `trial_price_raw` | 宗地市價試算精確值；比準地地價×(1＋總調整率)；後端計算；保留精度 |

## S01

本章節共有 77 個 AI 可辨識欄位。

| field_name | 欄位特徵、來源、輸入／計算與檢核 |
|---|---|
| `administrative_area` | 行政區；地價區段土地所屬直轄市及鄉鎮市區；文字/代碼；縣市＋鄉鎮市區代碼；案件/地籍資料；須為有效行政區代碼 |
| `agency_head_name` | 主任（局、處長）；機關首長或授權主管；人員參照；user_id＋顯示姓名；使用者/組織資料；應保存簽核時間與人員ID；估價師僅委託估價時必填 |
| `appraiser_name` | 不動產估價師；委託不動產估價師時之簽章人；人員參照；user_id＋顯示姓名；使用者/組織資料；應保存簽核時間與人員ID；估價師僅委託估價時必填 |
| `average_internal_road_width_m` | 區段內道路平均寬度；區段內已開闢道路寬度的算術平均；小數；公尺；道路清單；'＝已開闢道路總寬度÷已開闢道路條數；條數須大於0 |
| `building_coverage_ratio` | 建蔽率；法定建蔽率；百分比；0-100%；都市計畫或非都市土地使用管制規則；0至100；未實施或不適用須附原因 |
| `building_density_ratio` | 建築密度；已建築使用土地面積占區段總面積比例；百分比；0-100%；GIS/實地勘查；0至100%；應記錄計算或估計來源 |
| `building_prohibition_status` | 是否禁止建築；是否有禁止建築規定；布林；true/false；主管法規/計畫資料；不得空白 |
| `building_restriction_details` | 限制建築內容；記錄整體開發、面積限制、高度限制等具體規定；長文字/多選；整體開發、面積限制、高度限制、其他；主管法規/計畫資料；building_restriction_status=true時必填 |
| `building_restriction_status` | 是否限制建築；是否有整體開發、面積或高度等限制；布林；true/false；主管法規/計畫資料；為true時限制內容必填 |
| `building_site_improvement_other` | 其他改良說明；選擇其他時的具體內容；文字；無；實地勘查；type=其他時必填 |
| `building_site_improvement_type` | 改良項目；區段內已完成的建築基地改良項目；列舉；整平或填挖基地/開挖水溝/水土保持/舖築道路/埋設管道/修築駁嵌/其他；實地勘查；只記錄已完成項目 |
| `bus_stop_comparison_mode` | 站牌比較方式；同一徵收案擇一採接近程度或密集程度比較；列舉；proximity/density；查估作業設定；同案所有區段須一致 |
| `bus_stop_density_level` | 站牌密集程度；採密集程度比較時記錄非常密集、密集或不密集；列舉；very_dense/dense/not_dense；實地勘查；comparison_mode=density時必填 |
| `bus_stop_distance_m` | 站牌距離；區段中心點至區段外代表站牌距離；小數；公尺；GIS；location_scope=outside時必填 |
| `bus_stop_location_scope` | 位於區段內外；代表站牌在區段內或區段外；列舉；inside/outside；實勘/GIS；採接近程度時使用 |
| `bus_stop_name` | 站牌名稱；採接近程度時的代表站牌名稱；文字；無；實勘/GIS；comparison_mode=proximity時必填 |
| `commercial_facility_count` | 數量；同類設施數量；整數；家/處；實勘/GIS；整數>=0 |
| `commercial_facility_distance_m` | 距離；區段中心點至區段外商業設施距離；小數；公尺；實勘/GIS；location_scope=outside時必填且>=0 |
| `commercial_facility_location_scope` | 位於區段內外；商業設施位於區段內或外；列舉；inside/outside；實勘/GIS；有設施紀錄時必填 |
| `commercial_facility_name` | 商業設施名稱；商業設施名稱；文字；無；實勘/GIS；有設施紀錄時必填 |
| `commercial_facility_type` | 商業設施類型；工商活動設施固定類型；列舉；department_store/financial_institution/entertainment/exhibition_hotel；實勘/GIS；固定列舉 |
| `consumer_market_proximity` | 接近消費市場程度；區段中心點接近農產品消費市場的距離或對應等級；等級/小數；依新北市區域因素評價基準；消費市場可記公尺；實勘/GIS＋評價基準；優劣等級須符合當期新北市評價基準 |
| `current_land_use_other` | 其他土地利用說明；選擇其他時補充利用內容；文字；無；實地勘查；current_land_use_type=other時必填 |
| `current_land_use_type` | 主要土地利用；區段內一般土地利用現況；列舉＋其他；commercial/residential/industrial/residential_commercial/residential_industrial/agricultural/fishery_pastoral/vacant/public_facility/other；實地勘查；依原表單單選；若系統允許複選須另與主管機關確認 |
| `customer_traffic_level` | 顧客通行量；顧客通行量多寡之優劣等級；等級；依新北市區域因素評價基準；實地勘查＋評價基準；等級須符合當期基準 |
| `distribution_center_proximity_level` | 接近運銷中心程度；區段中心點接近農產品運銷中心程度；等級/小數；依新北市區域因素評價基準；消費市場可記公尺；實勘/GIS＋評價基準；優劣等級須符合當期新北市評價基準 |
| `dominant_building_type` | 建築型態；區段內多數建物的主要型態；列舉＋其他；apartment/high_rise/townhouse/other；實地勘查；單選主要型態；其他須補充 |
| `drainage_level` | 保（排）水之良否；保排水設施及狀況；等級/文字；依新北市區域因素評價基準；實地勘查＋評價基準；優劣等級須符合當期基準 |
| `electric_power_resource_level` | 電力資源影響程度；電力資源對地價影響程度；等級/文字；依評價基準/true-false；實地勘查/主管資料；依表單及評價基準 |
| `farmland_improvement_other` | 其他改良說明；選擇其他時的具體內容；文字；無；實地勘查；type=其他時必填 |
| `farmland_improvement_type` | 改良項目；區段內已完成的農地改良項目；列舉；耕地整理/水土保持/土壤改良/修築農路/灌溉/排水/防風/防砂/堤防/其他；實地勘查；只記錄已完成項目 |
| `floor_area_ratio` | 容積率；法定容積率；百分比；可大於100%；都市計畫或非都市土地使用管制規則；大於等於0；未實施須填原因 |
| `floor_area_ratio_note` | 容積率未實施原因；尚未實施容積率時記錄原因；長文字；無；管制規定；floor_area_ratio為空且尚未實施時必填 |
| `handler_name` | 承辦員；承辦填表人員；人員參照；user_id＋顯示姓名；使用者/組織資料；應保存簽核時間與人員ID；估價師僅委託估價時必填 |
| `industrial_water_facility_level` | 產業用水及設施影響程度；產業用水及設施對地價影響程度；等級/文字；依評價基準/true-false；實地勘查/主管資料；依表單及評價基準 |
| `interchange_distance_m` | 交流道距離；區段中心點至區段外交流道距離；小數；公尺；GIS；大於等於0 |
| `interchange_location_scope` | 位於區段內外；交流道在區段內或區段外；列舉；inside/outside；GIS/實勘；outside時distance_m必填 |
| `interchange_name` | 交流道名稱；鄰近交流道或匝道名稱；文字；無；實勘/GIS；有資料時與內外、距離成組 |
| `internal_road_is_opened` | 是否已開闢；決定道路是否納入平均寬度計算；布林；true/false；道路資料/實勘；只有true者納入公式 |
| `internal_road_width_m` | 道路寬度；供平均寬度計算的各已開闢道路寬度；小數；公尺；道路資料/實勘；大於0 |
| `land_use_zone_category` | 使用分區或使用地類別；都市計畫使用分區或非都市土地編定使用地類別；文字＋代碼；主管機關分類代碼；都市計畫/地籍資料；須與urban_plan_scope相容 |
| `landscape_level` | 景觀；景觀與視野狀況；等級/文字；依新北市區域因素評價基準；實地勘查＋評價基準；優劣等級須符合當期基準 |
| `main_road_name` | 主要道路名稱；區段內主要道路名稱；文字；無；實地勘查/道路資料；零星已建築用地填寫困難時得採鄰近同區段道路 |
| `main_road_width_m` | 主要道路寬度；主要道路寬度；小數；公尺；實地勘查/道路資料；大於0 |
| `major_station_distance_m` | 距離；區段中心點至區段外車站距離；小數；公尺；GIS；location_scope=outside時大於等於0 |
| `major_station_location_scope` | 位於區段內外；設施在本區段內或區段外；列舉；inside/outside；GIS/實勘；outside時distance_m必填 |
| `major_station_name` | 車站名稱；鄰近大型車站名稱；文字；無；實地勘查/GIS；有車站類型時必填 |
| `major_station_type` | 車站類型；高鐵、火車、客運或捷運站類型；列舉；high_speed_rail/rail/bus/metro；實地勘查/GIS；固定列舉 |
| `other_factor_description` | 因素說明；說明影響方向、範圍與判斷依據；長文字；無；實地勘查/專業判斷；有因素名稱時必填 |
| `other_factor_name` | 因素名稱；表內未列但足以影響區段地價的因素名稱；文字；無；實地勘查/專業判斷；不得重複既有固定因素 |
| `pollution_distance_m` | 距離；區段中心點至區段外污染源距離；小數；公尺；實勘/GIS/環保資料；location_scope=outside時必填且>=0 |
| `pollution_location_scope` | 位於區段內外；污染源位於區段內或外；列舉；inside/outside；實勘/GIS/環保資料；有污染紀錄時必填 |
| `pollution_source_name` | 污染源名稱；污染源名稱；無污染時可明示無；文字；無；實勘/GIS/環保資料；有污染紀錄時必填 |
| `pollution_type` | 污染類型；固定污染種類；列舉；water/noise/air/waste/other；實地勘查/環保資料；固定列舉 |
| `price_zone_no` | 區段編號；辨識地價區段的業務編號；文字；P＋母號3碼＋支號2碼；區段劃分結果；Regex ^P\d{3}-\d{2}$；同一案件內唯一 |
| `public_facility_distance_m` | 距離；區段中心點至區段外公共建設距離；小數；公尺；實勘/GIS；location_scope=outside時必填且>=0 |
| `public_facility_location_scope` | 位於區段內外；公共建設位於區段內或外；列舉；inside/outside；實勘/GIS；有設施紀錄時必填 |
| `public_facility_name` | 設施名稱；公共建設名稱；文字；無；實勘/GIS；有設施紀錄時必填 |
| `public_facility_type` | 設施類型；公共建設固定類型；列舉；elementary_school/junior_high/high_school/college/traditional_market/supermarket/shopping_center/neighborhood_park/general_park/plaza_pedestrian/tourism_recreation/parking/service_facility；實勘/GIS；固定列舉 |
| `road_planning_development_level` | 區段內道路規劃及闢建程度；區段內道路規劃及開闢情形；等級/小數；依新北市區域因素評價基準；消費市場可記公尺；實勘/GIS＋評價基準；優劣等級須符合當期新北市評價基準 |
| `section_chief_name` | 課（股）長；課股主管簽核人；人員參照；user_id＋顯示姓名；使用者/組織資料；應保存簽核時間與人員ID；估價師僅委託估價時必填 |
| `settlement_proximity_level` | 接近聚落程度；區段中心點接近聚落程度；等級/小數；依新北市區域因素評價基準；消費市場可記公尺；實勘/GIS＋評價基準；優劣等級須符合當期新北市評價基準 |
| `shop_contiguity_level` | 店舖毗連狀態；店舖連續或集中程度之優劣等級；等級/文字；依新北市區域因素評價基準；實地勘查＋評價基準；等級須符合當期基準 |
| `slope_level` | 傾斜度；坡度高低陡峭程度；等級/文字；依新北市區域因素評價基準；實地勘查＋評價基準；優劣等級須符合當期基準 |
| `soil_quality_level` | 土質；地質適宜使用程度；等級/文字；依新北市區域因素評價基準；實地勘查＋評價基準；優劣等級須符合當期基準 |
| `special_facility_distance_m` | 距離；區段中心點至區段外特殊設施距離；小數；公尺；實勘/GIS；location_scope=outside時必填且>=0 |
| `special_facility_location_scope` | 位於區段內外；特殊設施位於區段內或外；列舉；inside/outside；實勘/GIS；有設施紀錄時必填 |
| `special_facility_name` | 特殊設施名稱；特殊設施名稱；文字；無；實勘/GIS；有設施紀錄時必填 |
| `special_facility_type` | 特殊設施類型；固定類型的嫌惡或特殊設施；列舉；substation_high_voltage_tower/gas_oil_tank/cemetery/funeral_home/crematorium/columbarium/sewage_plant/landfill_incinerator；實勘/GIS；固定列舉 |
| `sunlight_level` | 日照；日照充足程度；等級/文字；依新北市區域因素評價基準；實地勘查＋評價基準；優劣等級須符合當期基準 |
| `survey_date` | 勘查日期；實際地價區段現場勘查日期；日期；ISO日期；輸出民國年月日；實地勘查紀錄；不得晚於文件核定日；可與估價基準日不同 |
| `terrain_level` | 地勢；高亢、平坦或低窪程度；等級/文字；依新北市區域因素評價基準；實地勘查＋評價基準；優劣等級須符合當期基準 |
| `urban_plan_scope` | 都市計畫內外；區分都市土地或非都市土地；列舉；inside/outside；都市計畫/非都市土地資料；inside=都市土地；outside=非都市土地 |
| `valuation_base_date` | 年期（估價基準日）；本次市價查估的估價基準日；表面以民國7碼顯示；日期；儲存ISO日期；輸出民國YYYMMDD；案件資料；必須為有效日期；同案各表應一致 |
| `wastewater_waste_facility_present` | 是否有污廢水及廢棄物處理設施；公共建設面向是否具備處理設施；布林；依評價基準/true-false；實地勘查/主管資料；依表單及評價基準 |
| `wind_condition_level` | 風勢；風勢方向或大小；等級/文字；依新北市區域因素評價基準；實地勘查＋評價基準；優劣等級須符合當期基準 |
| `zone_boundary_description` | 區段範圍；描述地段、小段或四至；公共設施保留地另載毗鄰非公保地區段號；長文字；無；地籍圖＋實地勘查；不可僅寫行政區；應足以辨識四至或地段範圍 |

## AI 輸出契約

每一筆候選必須包含：`field_name`、`extracted_value`、`confidence`（0 到 1）與 `source_text`。

```json
{"candidates":[{"field_name":"catalog 中的欄位代碼","extracted_value":"原文中的值","confidence":0.0,"source_text":"OCR 原文證據"}]}
```

若沒有可由原文支持的欄位，回傳空陣列：

```json
{"candidates":[]}
```

## 後端使用方式

- `field_analysis.py` 讀取本文件的通用規則與目前表單章節。
- JSON catalog 仍作為程式白名單與輸出 schema 的結構化來源；本 Markdown 是給 AI 閱讀的規則層。
- Bedrock 自動分析與 Codex 候選匯入使用同一套規則，不能繞過原文證據、表單白名單與人工確認流程。
