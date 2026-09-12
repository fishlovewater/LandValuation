"""Template row codes derived only from the supplied three-page blank form.

The catalogue intentionally contains labels and display order only.  It does not
contain formal weights, factor levels, ranges, or adjustment formulas.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class TemplateFactor:
    code: str
    group: str
    label: str
    f02_rf_y: float | None = None


TEMPLATE_FACTORS = (
    TemplateFactor("urban_plan_status", "LAND_USE_CONTROL", "都市計畫（內、外）", 711),
    TemplateFactor("land_use_zone", "LAND_USE_CONTROL", "使用分區（使用地類別）", 696),
    TemplateFactor("building_coverage_rate", "LAND_USE_CONTROL", "建蔽率", 682),
    TemplateFactor("floor_area_ratio", "LAND_USE_CONTROL", "容積率", 669),
    TemplateFactor("prohibited_building", "LAND_USE_CONTROL", "有無禁止建築", 656),
    TemplateFactor("restricted_building", "LAND_USE_CONTROL", "有無限制建築（整體開發、面積限制、高度限制……等）", 641),
    TemplateFactor("main_road_width", "TRANSPORT", "主要道路寬度", 619),
    TemplateFactor("average_road_width", "TRANSPORT", "區段內道路平均寬度", 606),
    TemplateFactor("mass_transit_proximity", "TRANSPORT", "接近大型車站之程度", 594),
    TemplateFactor("station_proximity", "TRANSPORT", "站牌之接近程度或密集程度", 581),
    TemplateFactor("interchange_proximity", "TRANSPORT", "交流道之有無及接近交流道之程度", 562),
    TemplateFactor("road_plan", "TRANSPORT", "區段內道路規劃及闢建程度", 546),
    TemplateFactor("drainage", "NATURAL", "排水之良否", 524),
    TemplateFactor("terrain", "NATURAL", "地勢", 511),
    TemplateFactor("market_proximity", "PUBLIC_FACILITY", "接近市場之程度（傳統市場、超級市場、超大型購物中心）", 484),
    TemplateFactor("park_proximity", "PUBLIC_FACILITY", "接近公園（里鄰公園、一般公園）、廣場、徒步區之程度", 469),
    TemplateFactor("tourist_facility_proximity", "PUBLIC_FACILITY", "接近觀光遊憩設施之程度", 456),
    TemplateFactor("parking_convenience", "PUBLIC_FACILITY", "停車場地之便利程度", 442),
    TemplateFactor("power_gas_facility", "SPECIAL_FACILITY", "電業設施及公用氣體燃料設施之有無及接近程度", 419),
    TemplateFactor("funeral_facility", "SPECIAL_FACILITY", "殯葬設施之有無及接近程度", 402),
    TemplateFactor("waste_facility", "SPECIAL_FACILITY", "廢棄物處理設施之有無及接近程度", 389),
    TemplateFactor("environmental_pollution", "POLLUTION", "水污染、噪音污染、廢氣污染、廢棄物污染等之有無及接近程度", 361),
    TemplateFactor("department_store", "COMMERCIAL_ACTIVITY", "百貨公司之有無、數量、接近程度", 334),
    TemplateFactor("financial_institution", "COMMERCIAL_ACTIVITY", "金融機構之有無、數量、接近程度", 317),
    TemplateFactor("entertainment_facility", "COMMERCIAL_ACTIVITY", "娛樂設施之有無、數量、接近程度", 301),
    TemplateFactor("exhibition_hotel", "COMMERCIAL_ACTIVITY", "大型展示中心或觀光飯店之有無、數量、接近程度", 283),
    TemplateFactor("pedestrian_flow", "COMMERCIAL_ACTIVITY", "顧客通行量之多寡", 264),
    TemplateFactor("vacancy_rate", "COMMERCIAL_ACTIVITY", "店舖之毗連狀態", 251),
    TemplateFactor("other", "OTHER", "其他影響因素", 228),
)

TEMPLATE_FACTOR_BY_CODE = {factor.code: factor for factor in TEMPLATE_FACTORS}
TEMPLATE_FACTOR_CODES = frozenset(TEMPLATE_FACTOR_BY_CODE)

DISTANCE_FACTOR_CODES = frozenset(
    {
        "mass_transit_proximity",
        "station_proximity",
        "interchange_proximity",
        "market_proximity",
        "park_proximity",
        "tourist_facility_proximity",
        "parking_convenience",
        "power_gas_facility",
        "funeral_facility",
        "waste_facility",
        "department_store",
        "financial_institution",
        "entertainment_facility",
        "exhibition_hotel",
    }
)


# Table 4 (F02) individual factors listed in the supplied official operating
# manual.  Codes are deliberately namespaced because several labels also
# appear in the regional-factor table with a different comparison scope.
INDIVIDUAL_FACTORS = (
    TemplateFactor("individual_area", "PARCEL", "面積"),
    TemplateFactor("individual_width", "PARCEL", "寬度"),
    TemplateFactor("individual_depth", "PARCEL", "深度"),
    TemplateFactor("individual_shape", "PARCEL", "形狀"),
    TemplateFactor("individual_street_frontage", "PARCEL", "臨街情形"),
    TemplateFactor("individual_terrain", "PARCEL", "地勢"),
    TemplateFactor("individual_road_type", "ROAD", "道路種類"),
    TemplateFactor("individual_front_road_width", "ROAD", "面前道路寬度"),
    TemplateFactor("individual_school_proximity", "ACCESS", "接近學校之程度"),
    TemplateFactor("individual_market_proximity", "ACCESS", "接近市場之程度"),
    TemplateFactor("individual_park_proximity", "ACCESS", "接近公園、廣場之程度"),
    TemplateFactor("individual_station_proximity", "ACCESS", "接近車站之程度"),
    TemplateFactor(
        "individual_commercial_district_proximity",
        "ACCESS",
        "接近商圈之程度",
    ),
    TemplateFactor(
        "individual_undesirable_facility",
        "ENVIRONMENT",
        "嫌惡設施之有無及接近程度",
    ),
    TemplateFactor(
        "individual_parking_convenience",
        "ENVIRONMENT",
        "停車方便性",
    ),
    TemplateFactor("individual_land_use", "ADMINISTRATION", "使用分區或編定用地"),
    TemplateFactor(
        "individual_building_coverage_rate",
        "ADMINISTRATION",
        "建蔽率",
    ),
    TemplateFactor("individual_floor_area_ratio", "ADMINISTRATION", "容積率"),
    TemplateFactor(
        "individual_building_restriction",
        "ADMINISTRATION",
        "有無禁限建",
    ),
    TemplateFactor("individual_other", "OTHER", "其他影響因素"),
)

INDIVIDUAL_FACTOR_BY_CODE = {factor.code: factor for factor in INDIVIDUAL_FACTORS}
INDIVIDUAL_FACTOR_CODES = frozenset(INDIVIDUAL_FACTOR_BY_CODE)
