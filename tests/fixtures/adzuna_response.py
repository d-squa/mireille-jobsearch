"""Realistic fixture payloads shaped like Adzuna's documented API
response, used to test the connector without live HTTP calls."""

VALID_RESPONSE = {
    "results": [
        {
            "id": "129698749",
            "title": "Paid Media Manager",
            "company": {"display_name": "Acme Digital Ltd"},
            "location": {"display_name": "Manchester, Greater Manchester", "area": ["UK", "North West England"]},
            "created": "2026-07-08T18:07:39Z",
            "redirect_url": "https://www.adzuna.co.uk/jobs/land/ad/129698749",
            "description": "Great opportunity for a Paid Media Manager to join a growing agency.",
            "salary_min": 40000,
            "salary_max": 48000,
        },
        {
            "id": "126977586",
            "title": "Senior Developer Python",
            "company": {"display_name": "Tech Solutions Inc"},
            "location": {"display_name": "London", "area": ["UK", "London"]},
            "created": "2026-07-07T19:32:43Z",
            "redirect_url": "https://www.adzuna.co.uk/jobs/land/ad/126977586",
            "description": "Backend engineering role.",
        },
        {
            # Missing company display_name - should be skipped.
            "id": "111222333",
            "title": "Marketing Assistant",
            "company": {"display_name": ""},
            "location": {"display_name": "Bristol"},
            "created": "2026-07-05T00:00:00Z",
            "redirect_url": "https://www.adzuna.co.uk/jobs/land/ad/111222333",
            "description": "",
        },
    ],
    "count": 3,
}

EMPTY_RESPONSE = {"results": [], "count": 0}
