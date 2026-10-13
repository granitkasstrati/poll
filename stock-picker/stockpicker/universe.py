"""Default screening universes. Edit freely — or add tickers from the app sidebar.

Kept deliberately modest (~150 names) so a full screen finishes in a few
minutes on the free Yahoo feed without getting rate-limited.
"""

# Durable, mostly large-cap businesses: where long-term compounders tend to live.
QUALITY = [
    "AAPL", "MSFT", "GOOGL", "AMZN", "META", "NVDA", "AVGO", "ASML", "TSM", "ADBE",
    "V", "MA", "AXP", "BRK-B", "MCO", "SPGI", "MSCI", "ICE", "CME",
    "COST", "WMT", "HD", "LOW", "TJX", "ORLY", "AZO", "MCD", "SBUX", "CMG", "NKE",
    "KO", "PEP", "PG", "CL", "MDLZ", "HSY", "MO", "PM",
    "JNJ", "UNH", "LLY", "ABBV", "MRK", "PFE", "TMO", "DHR", "ISRG", "SYK", "ZTS", "IDXX",
    "UNP", "CSX", "CAT", "DE", "HON", "GD", "LMT", "RTX", "WM", "RSG", "CTAS", "FAST", "ROP",
    "ADP", "PAYX", "INTU", "ORCL", "CRM", "NOW", "TXN", "ADI", "KLAC", "LRCX", "AMAT",
    "BKNG", "CPRT", "VRSK", "TT", "SHW", "ECL", "LIN", "APD",
    "XOM", "CVX", "COP", "EOG", "JPM", "BAC", "WFC", "GS", "MS", "BLK",
]

# Liquid, mid-to-large caps with enough daily volume for swing trading.
SWING = [
    "AMD", "TSLA", "NFLX", "UBER", "ABNB", "SHOP", "XYZ", "PYPL", "COIN", "PLTR",
    "CRWD", "PANW", "ZS", "NET", "DDOG", "SNOW", "MDB", "TEAM", "ANET", "MU",
    "SMCI", "DELL", "ON", "MRVL", "QCOM", "INTC", "BA", "GE", "F", "GM",
    "DIS", "ROKU", "SPOT", "DKNG", "RCL", "CCL", "DAL", "UAL", "FCX", "NEM",
    "OXY", "SLB", "HAL", "DVN", "STLD", "CLF", "AA", "WBD", "TTD", "LULU",
]

# Small/speculative names where outcomes are wide — candidates for the high-risk tab.
SPECULATIVE = [
    "SOFI", "HOOD", "AFRM", "UPST", "RIVN", "LCID", "NIO", "XPEV", "CHPT", "PLUG",
    "RKLB", "ASTS", "LUNR", "JOBY", "ACHR", "IONQ", "RGTI", "QBTS", "SOUN", "BBAI",
    "MARA", "RIOT", "CLSK", "HUT", "MSTR", "OKLO", "SMR", "NNE", "LEU", "UEC",
    "CRSP", "BEAM", "NTLA", "EDIT", "RXRX", "DNA", "ARWR", "SRPT", "VKTX", "HIMS",
    "OPEN", "CVNA", "W", "FUBO", "PATH", "U", "RBLX", "SNAP", "PINS", "DUOL",
]

ALL = list(dict.fromkeys(QUALITY + SWING + SPECULATIVE))
