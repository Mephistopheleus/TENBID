"""Evidence flow constants.

These names keep NOVA away from signal-vote thinking. Analyzer output is treated
as typed evidence with an explicit stage, tier and right to influence the matrix.
"""


class CardType:
    DATA = "DATA"
    ANALYSIS = "ANALYSIS"
    FORECAST = "FORECAST"
    STATE = "STATE"
    MATRIX_ZONE = "MATRIX_ZONE"
    VALIDATION = "VALIDATION"
    REVISION = "REVISION"
    RECHECK_REQUEST = "RECHECK_REQUEST"
    OUTCOME = "OUTCOME"
    TUNING = "TUNING"


class CardStage:
    RAW = "RAW"
    MATRIX_BUILD = "MATRIX_BUILD"
    VALIDATION = "VALIDATION"
    REVISION = "REVISION"
    RECHECK = "RECHECK"
    OUTCOME = "OUTCOME"
    TUNING = "TUNING"


class EvidenceTier:
    PRIMARY = "PRIMARY"
    META = "META"
    DERIVED = "DERIVED"


class MatrixLayer:
    PRIMARY = "PRIMARY"
    RECONCILED = "RECONCILED"
    VALIDATION = "VALIDATION"


class MatrixFieldRole:
    CORE = "CORE"
    HALO = "HALO"
    BRIDGE = "BRIDGE"
    TENSION = "TENSION"


class MatrixZoneStatus:
    ACTIVE = "ACTIVE"
    NEEDS_RECHECK = "NEEDS_RECHECK"
    STALE = "STALE"
    CONFIRMED = "CONFIRMED"
    WEAKENED = "WEAKENED"
    INVALIDATED = "INVALIDATED"
    EXPIRED = "EXPIRED"
