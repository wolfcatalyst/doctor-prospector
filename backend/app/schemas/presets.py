"""Built-in device market profile presets.

These ship with the app and cannot be deleted by users.
They can be cloned and customized.
"""

from .device_profile import DeviceMarketFilters

TAVR_FILTERS = DeviceMarketFilters(
    hcpcs_codes=[
        "33361",  # TAVR, percutaneous femoral artery approach
        "33362",  # TAVR, open femoral artery approach
        "33363",  # TAVR, percutaneous axillary artery approach
        "33364",  # TAVR, open axillary artery approach
        "33365",  # TAVR, transaortic approach
        "33366",  # TAVR, transapical approach
        "33367",  # TAVR, cardiopulmonary bypass support
        "33368",  # TAVR, percutaneous transcaval approach
        "33369",  # TAVR, other approaches
    ],
    manufacturers={
        "heartflow": ["HeartFlow", "HeartFlow Inc", "HeartFlow, Inc."],
        "edwards": [
            "Edwards Lifesciences",
            "Edwards Lifesciences LLC",
            "Edwards Lifesciences Corporation",
        ],
        "medtronic": [
            "Medtronic",
            "Medtronic Inc",
            "Medtronic, Inc.",
            "Medtronic USA",
        ],
        "abbott": [
            "Abbott",
            "Abbott Laboratories",
            "Abbott Vascular",
            "St. Jude Medical",
        ],
        "boston_scientific": [
            "Boston Scientific",
            "Boston Scientific Corporation",
        ],
    },
    taxonomies=[
        "Interventional Cardiology",
        "Thoracic Surgery (Cardiothoracic Vascular Surgery)",
        "Adult Congenital Heart Disease",
    ],
    trial_search_terms=[
        "TAVR",
        "TAVI",
        "transcatheter aortic valve replacement",
        "transcatheter aortic valve implantation",
    ],
    trial_statuses=[
        "RECRUITING",
        "ACTIVE_NOT_RECRUITING",
        "ENROLLING_BY_INVITATION",
    ],
    drg_codes=[
        "266",  # Endovascular cardiac valve replacement with MCC
        "267",  # Endovascular cardiac valve replacement without MCC
    ],
    modules=["tavr"],
    procedure_label="TAVR",
)

ROBOTIC_SURGERY_FILTERS = DeviceMarketFilters(
    hcpcs_codes=[
        "55866",  # Robotic-assisted radical prostatectomy
        "S2900",  # Surgical techniques requiring robotic system
        "58571",  # TLH, uterus 250g or less, with robotic assistance
        "58572",  # TLH, uterus > 250g, with robotic assistance
        "58573",  # TLH with removal of tube(s)/ovary(ies), robotic
        "44204",  # Lap-assisted colectomy, partial, with anastomosis
        "44205",  # Lap colectomy, partial, with removal of terminal ileum
        "44207",  # Lap colectomy with coloproctostomy
        "44208",  # Lap colectomy with coloproctostomy and colostomy
        "44210",  # Lap total proctocolectomy
        "44213",  # Lap mobilization of splenic flexure
        "27447",  # Total knee arthroplasty (Mako robotic)
        "27130",  # Total hip arthroplasty (Mako robotic)
        "22551",  # Anterior cervical fusion (ROSA/ExcelsiusGPS)
        "22612",  # Posterior lumbar fusion (robotic-assisted)
        "22630",  # Posterior lumbar interbody fusion (PLIF/TLIF)
    ],
    manufacturers={
        "intuitive_surgical": [
            "Intuitive Surgical",
            "Intuitive Surgical Inc",
            "Intuitive Surgical, Inc.",
            "Intuitive Surgical Operations",
        ],
        "medtronic": [
            "Medtronic",
            "Medtronic Inc",
            "Medtronic, Inc.",
            "Medtronic USA",
        ],
        "stryker": [
            "Stryker",
            "Stryker Corporation",
            "Stryker Corp",
            "MAKO Surgical",
        ],
        "zimmer_biomet": [
            "Zimmer Biomet",
            "Zimmer Biomet Holdings",
            "Biomet",
        ],
        "globus_medical": [
            "Globus Medical",
            "Globus Medical Inc",
            "Globus Medical, Inc.",
        ],
        "johnson_and_johnson": [
            "Johnson & Johnson",
            "Ethicon",
            "Ethicon Inc",
            "Ethicon Endo-Surgery",
            "DePuy Synthes",
        ],
        "cmr_surgical": [
            "CMR Surgical",
            "CMR Surgical Ltd",
        ],
    },
    taxonomies=[
        "General Surgery",
        "Urology",
        "Gynecological Oncology",
        "Gynecology",
        "Orthopedic Surgery",
        "Thoracic Surgery (Cardiothoracic Vascular Surgery)",
        "Colorectal Surgery",
        "Neurological Surgery",
    ],
    trial_search_terms=[
        "robotic surgery",
        "robot-assisted surgery",
        "da Vinci",
        "surgical robotics",
        "computer-assisted surgery",
        "AI-assisted surgery",
        "robotic-assisted laparoscopy",
        "robotic",
    ],
    trial_statuses=[
        "RECRUITING",
        "ACTIVE_NOT_RECRUITING",
        "ENROLLING_BY_INVITATION",
    ],
    drg_codes=[
        "710",  # Penis procedures with CC/MCC
        "714",  # Transurethral prostatectomy with CC/MCC
        "715",  # Transurethral prostatectomy without CC/MCC
        "716",  # Other male reproductive system OR proc for malignancy with CC/MCC
        "717",  # Other male reproductive system OR proc for malignancy without CC/MCC
        "734",  # Pelvic evisceration, radical hysterectomy & radical vulvectomy with CC/MCC
        "735",  # Pelvic evisceration, radical hysterectomy & radical vulvectomy without CC/MCC
        "736",  # Uterine & adnexa proc for ovarian or adnexal malignancy with MCC
        "737",  # Uterine & adnexa proc for ovarian or adnexal malignancy with CC
        "738",  # Uterine & adnexa proc for ovarian or adnexal malignancy without CC/MCC
        "329",  # Major small & large bowel procedures with MCC
        "330",  # Major small & large bowel procedures with CC
        "331",  # Major small & large bowel procedures without CC/MCC
        "469",  # Major hip and knee joint replacement with MCC or total ankle replacement
        "470",  # Major hip and knee joint replacement without MCC
    ],
    modules=[],
    procedure_label="Robotic Surgery",
)

PRESET_PROFILES = {
    "TAVR": {
        "description": "Transcatheter Aortic Valve Replacement — heart valve device market",
        "filters": TAVR_FILTERS,
    },
    "Robotic Surgery": {
        "description": "Robotic & AI-assisted surgery — da Vinci, Mako, Hugo, ROSA platforms",
        "filters": ROBOTIC_SURGERY_FILTERS,
    },
}
