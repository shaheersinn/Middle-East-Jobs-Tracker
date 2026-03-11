"""
Practice department taxonomy — tuned for US BigLaw Middle East offices.

Each department has:
  - keywords: single-word or short signals (weight 1.0)
  - phrases:  multi-word signals (weight 2.5× boost)

Departments reflect the dominant work streams in DIFC / ADGM / QFC practices.
"""

DEPARTMENTS = [
    {
        "name": "Corporate / M&A",
        "keywords": [
            "merger", "acquisition", "takeover", "amalgamation", "consolidation",
            "corporate", "governance", "shareholder", "buyout", "divestiture",
            "m&a", "transaction", "deal", "joint venture", "jv",
            "privatisation", "privatization", "going-private",
        ],
        "phrases": [
            "mergers and acquisitions", "business combination", "share purchase",
            "asset purchase", "joint venture", "corporate governance",
            "shareholder rights", "cross-border m&a", "public m&a",
            "private m&a", "strategic review", "board of directors",
            "sovereign wealth fund", "family office", "private company",
            "regional m&a", "gulf m&a", "middle east m&a",
        ],
    },
    {
        "name": "Banking & Finance",
        "keywords": [
            "banking", "finance", "loan", "credit", "lender", "borrower",
            "syndicated", "facility", "refinancing", "leverage", "debt",
            "acquisition finance", "structured finance", "mezzanine",
        ],
        "phrases": [
            "acquisition finance", "leveraged finance", "syndicated loan",
            "project finance", "structured finance", "debt capital",
            "banking and finance", "finance lawyer", "finance associate",
            "mezzanine finance", "real estate finance", "trade finance",
            "fund finance", "NAV lending", "subscription finance",
        ],
    },
    {
        "name": "Capital Markets",
        "keywords": [
            "securities", "ipo", "prospectus", "underwriting", "offering",
            "equity", "bond", "sukuk", "debenture", "convertible",
            "listing", "exchange", "dfm", "adx", "qe", "tadawul",
            "disclosure", "market abuse", "insider trading",
        ],
        "phrases": [
            "initial public offering", "capital markets", "public offering",
            "private placement", "bond issuance", "sukuk issuance",
            "equity offering", "securities regulation", "material disclosure",
            "debt capital markets", "equity capital markets",
            "DFSA regulated", "FSRA regulated", "listing rules",
            "dual listing", "GDR", "ADR",
        ],
    },
    {
        "name": "Project Finance & Infrastructure",
        "keywords": [
            "project", "infrastructure", "concession", "PPP", "PFI",
            "EPC", "contractor", "construction", "transportation",
            "renewable", "airport", "port", "utility",
        ],
        "phrases": [
            "project finance", "infrastructure finance", "project development",
            "public private partnership", "concession agreement",
            "EPC contract", "engineering procurement construction",
            "renewable energy project", "solar project", "wind farm",
            "desalination project", "transport infrastructure",
            "NEOM", "Saudi Vision 2030", "Abu Dhabi economic vision",
        ],
    },
    {
        "name": "Energy & Natural Resources",
        "keywords": [
            "energy", "oil", "gas", "petroleum", "LNG", "upstream",
            "downstream", "midstream", "pipeline", "refinery",
            "ADNOC", "aramco", "QatarEnergy", "DEWA", "TAQA",
            "renewable", "solar", "wind", "hydrogen",
        ],
        "phrases": [
            "oil and gas", "energy law", "energy transactions",
            "upstream transactions", "LNG project", "natural gas",
            "energy regulatory", "petroleum law", "energy arbitration",
            "clean energy", "energy transition", "decarbonisation",
            "carbon capture", "green hydrogen", "power purchase agreement",
            "off-take agreement", "concession agreement oil",
        ],
    },
    {
        "name": "Real Estate",
        "keywords": [
            "real estate", "property", "land", "lease", "landlord",
            "tenant", "development", "REIT", "hospitality", "retail",
            "residential", "commercial property", "DIFC property",
        ],
        "phrases": [
            "real estate law", "property development", "real estate finance",
            "real estate investment", "REIT formation", "sale and leaseback",
            "commercial leasing", "joint development", "master developer",
            "real estate regulatory", "RERA", "DLD", "title registration",
            "property acquisition", "hotel acquisition",
        ],
    },
    {
        "name": "Arbitration & Disputes",
        "keywords": [
            "arbitration", "dispute", "litigation", "DIFC court",
            "ADGM court", "ICC", "LCIA", "DIAC", "SIAC", "AAA",
            "enforcement", "award", "injunction", "interim relief",
            "mediation", "expert determination",
        ],
        "phrases": [
            "international arbitration", "commercial arbitration",
            "investment arbitration", "ICSID arbitration", "ICC arbitration",
            "LCIA arbitration", "DIAC arbitration", "DIFC courts",
            "arbitration associate", "disputes associate",
            "enforcement of awards", "New York Convention",
            "investor-state dispute", "treaty arbitration",
            "construction disputes", "energy disputes",
        ],
    },
    {
        "name": "Islamic Finance",
        "keywords": [
            "sukuk", "sharia", "islamic finance", "murabaha",
            "musharaka", "ijara", "istisna", "wakala", "takaful",
            "halal", "zakat",
        ],
        "phrases": [
            "islamic finance", "sharia compliant", "sukuk issuance",
            "sukuk structuring", "murabaha financing", "ijara leasing",
            "musharaka financing", "islamic banking", "takaful insurance",
            "sharia board", "sharia review", "sharia supervisory",
            "AAOIFI standards", "Islamic Development Bank",
        ],
    },
    {
        "name": "Private Equity & Funds",
        "keywords": [
            "private equity", "fund", "venture capital", "vc",
            "buyout", "portfolio", "GP", "LP", "carried interest",
            "co-invest", "secondary", "NAV", "SWF", "sovereign",
        ],
        "phrases": [
            "private equity fund", "fund formation", "fund structuring",
            "venture capital fund", "sovereign wealth fund",
            "limited partnership", "general partner", "carried interest",
            "co-investment", "secondary transaction", "private credit",
            "NAV lending", "continuation vehicle", "GP-led secondary",
            "Gulf PE", "Middle East PE", "GCC fund",
        ],
    },
    {
        "name": "Regulatory & Compliance",
        "keywords": [
            "regulatory", "compliance", "DFSA", "FSRA", "QFC", "CBUAE",
            "SCA", "CMA", "licensing", "authorisation", "AML", "KYC",
            "sanctions", "OFAC", "financial crime",
        ],
        "phrases": [
            "regulatory compliance", "DFSA regulatory",
            "financial services regulatory", "AML compliance",
            "sanctions compliance", "KYC requirements",
            "regulatory advisory", "financial regulation",
            "fintech regulatory", "crypto regulatory",
            "digital asset regulation", "regulatory licensing",
        ],
    },
    {
        "name": "Employment & Labour",
        "keywords": [
            "employment", "labour", "labor", "HR", "redundancy",
            "termination", "DIFC employment", "UAE labour", "expatriate",
            "visa", "work permit",
        ],
        "phrases": [
            "employment law", "labour law", "employment disputes",
            "UAE employment", "DIFC employment law",
            "expatriate employment", "HR advisory", "employment contracts",
            "redundancy process", "employment termination",
            "whistle-blower", "HR compliance",
        ],
    },
    {
        "name": "Data Privacy & Technology",
        "keywords": [
            "data", "privacy", "GDPR", "PDPL", "cybersecurity",
            "technology", "fintech", "AI", "blockchain",
            "digital", "tech transactions",
        ],
        "phrases": [
            "data privacy", "data protection", "cybersecurity law",
            "technology transactions", "fintech law",
            "AI regulation", "blockchain law", "digital assets",
            "UAE data protection", "PDPL compliance",
            "tech M&A", "software licensing", "IT contracts",
        ],
    },
    {
        "name": "Construction & Engineering",
        "keywords": [
            "construction", "engineering", "EPC", "FIDIC", "contractor",
            "subcontractor", "delay", "defect", "variation", "claim",
            "adjudication", "DAB",
        ],
        "phrases": [
            "construction law", "engineering disputes",
            "FIDIC contract", "construction arbitration",
            "construction claims", "delay claims", "defect claims",
            "construction associate", "construction finance",
            "NEC contract", "FIDIC 2017", "project disputes",
        ],
    },
    {
        "name": "Restructuring & Insolvency",
        "keywords": [
            "restructuring", "insolvency", "bankruptcy", "creditor",
            "debtor", "DIFC insolvency", "UAE bankruptcy", "workout",
            "receiver", "administrator", "scheme",
        ],
        "phrases": [
            "debt restructuring", "corporate restructuring",
            "insolvency proceedings", "UAE bankruptcy law",
            "DIFC insolvency", "creditor rights",
            "scheme of arrangement", "distressed assets",
            "financial restructuring", "out-of-court workout",
        ],
    },
]
