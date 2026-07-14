"""Realistic fixture payloads shaped like each ATS platform's
documented API response, used to test connectors without live calls."""

GREENHOUSE_VALID_RESPONSE = {
    "jobs": [
        {
            "id": 44444,
            "title": "Paid Media Manager",
            "updated_at": "2026-07-05T19:39:23Z",
            "location": {"name": "Dubai, UAE"},
            "absolute_url": "https://boards.greenhouse.io/acme/jobs/44444",
            "content": "<p>Join our <b>growth team</b> as a Paid Media Manager.</p>",
        },
        {
            "id": 55555,
            "title": "Software Engineer",
            "updated_at": "2026-07-04T10:00:00Z",
            "location": {"name": "Remote"},
            "absolute_url": "https://boards.greenhouse.io/acme/jobs/55555",
            "content": "<p>Backend engineering role.</p>",
        },
        {
            # Missing absolute_url - should be skipped.
            "id": 66666,
            "title": "Intern",
            "updated_at": "2026-07-03T10:00:00Z",
            "location": {"name": "NYC"},
            "absolute_url": "",
            "content": "",
        },
    ],
    "meta": {"total": 3},
}

GREENHOUSE_EMPTY_RESPONSE = {"jobs": [], "meta": {"total": 0}}

LEVER_VALID_RESPONSE = [
    {
        "id": "a1b2c3d4",
        "text": "Media Buyer",
        "hostedUrl": "https://jobs.lever.co/acme/a1b2c3d4",
        "applyUrl": "https://jobs.lever.co/acme/a1b2c3d4/apply",
        "categories": {"team": "Marketing", "location": "London", "commitment": "Full-time"},
        "createdAt": 1783123200000,  # 2026-07-01T00:00:00Z-ish
        "descriptionPlain": "We need a media buyer to manage our programmatic budgets.",
        "workplaceType": "hybrid",
    },
    {
        "id": "e5f6g7h8",
        "text": "Account Executive",
        "hostedUrl": "https://jobs.lever.co/acme/e5f6g7h8",
        "applyUrl": "https://jobs.lever.co/acme/e5f6g7h8/apply",
        "categories": {"team": "Sales", "location": "Berlin", "commitment": "Full-time"},
        "createdAt": 1783036800000,
        "descriptionPlain": "Sales role.",
        "workplaceType": "on-site",
    },
    {
        # Missing text (title) - should be skipped.
        "id": "i9j0k1l2",
        "text": "",
        "hostedUrl": "https://jobs.lever.co/acme/i9j0k1l2",
        "categories": {},
        "createdAt": 1783036800000,
        "descriptionPlain": "",
    },
]

LEVER_EMPTY_RESPONSE: list = []

ASHBY_VALID_RESPONSE = {
    "apiVersion": "1",
    "jobs": [
        {
            "title": "Performance Marketing Manager",
            "location": "Doha, Qatar",
            "department": "Marketing",
            "team": "Growth",
            "isRemote": False,
            "workplaceType": "OnSite",
            "descriptionPlain": "Own our performance marketing budget across paid channels.",
            "publishedAt": "2026-07-06T16:21:55.393+00:00",
            "employmentType": "FullTime",
            "jobUrl": "https://jobs.ashbyhq.com/acme/perf-marketing-mgr",
            "applyUrl": "https://jobs.ashbyhq.com/acme/perf-marketing-mgr/apply",
            "compensation": {
                "compensationTierSummary": "$81K - $87K - Offers Bonus",
                "scrapeableCompensationSalarySummary": "$81K - $87K",
            },
        },
        {
            "title": "Product Designer",
            "location": "Remote",
            "department": "Design",
            "team": "Product",
            "isRemote": True,
            "workplaceType": "Remote",
            "descriptionPlain": "Design role.",
            "publishedAt": "2026-07-05T12:00:00.000+00:00",
            "employmentType": "FullTime",
            "jobUrl": "https://jobs.ashbyhq.com/acme/product-designer",
            "applyUrl": "https://jobs.ashbyhq.com/acme/product-designer/apply",
        },
        {
            # Missing title - should be skipped.
            "title": "",
            "location": "Unknown",
            "jobUrl": "https://jobs.ashbyhq.com/acme/blank",
            "publishedAt": "2026-07-01T00:00:00.000+00:00",
        },
    ],
}

ASHBY_EMPTY_RESPONSE = {"apiVersion": "1", "jobs": []}
