"""Realistic fixture payloads shaped exactly like Jooble's documented
API response, used to test the connector without live HTTP calls."""

VALID_RESPONSE = {
    "totalCount": 3,
    "jobs": [
        {
            "title": "Paid Media Manager",
            "location": "London, UK",
            "snippet": "Join our team as a Paid Media Manager overseeing PPC budgets...",
            "salary": "45,000 - 55,000 GBP",
            "source": "jooble",
            "type": "Full-time",
            "link": "https://jooble.org/jdp/123456/Paid-Media-Manager",
            "company": "Acme Real Estate Ltd",
            "updated": "2026-07-08 10:15:00",
            "id": "123456",
        },
        {
            "title": "Senior Media Buyer - Remote",
            "location": "Remote - EMEA",
            "snippet": "We are looking for an experienced media buyer...",
            "salary": "",
            "source": "jooble",
            "type": "Full-time",
            "link": "https://jooble.org/jdp/789012/Senior-Media-Buyer",
            "company": "GrowthCo Agency",
            "updated": "2026-07-07 08:00:00",
            "id": "789012",
        },
        {
            # Missing company - should be skipped by the connector, not crash it.
            "title": "Marketing Intern",
            "location": "Berlin, Germany",
            "snippet": "Entry level marketing role.",
            "salary": "",
            "source": "jooble",
            "type": "Internship",
            "link": "https://jooble.org/jdp/000111/Marketing-Intern",
            "company": "",
            "updated": "2026-07-06 09:00:00",
            "id": "000111",
        },
    ],
}

EMPTY_RESPONSE = {"totalCount": 0, "jobs": []}

MALFORMED_DATE_RESPONSE = {
    "totalCount": 1,
    "jobs": [
        {
            "title": "PPC Specialist",
            "location": "Paris, France",
            "snippet": "PPC role.",
            "salary": "",
            "source": "jooble",
            "type": "Full-time",
            "link": "https://jooble.org/jdp/222333/PPC-Specialist",
            "company": "MediaWorks",
            "updated": "not-a-real-date",
            "id": "222333",
        }
    ],
}
