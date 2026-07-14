"""Realistic fixture payloads shaped like Reed's documented API
response, used to test the connector without live HTTP calls."""

VALID_RESPONSE = {
    "results": [
        {
            "jobId": 55512345,
            "employerName": "Acme Media Group",
            "jobTitle": "Paid Media Manager",
            "locationName": "Manchester",
            "jobDescription": "Exciting opportunity for a Paid Media Manager to join our growing team.",
            "date": "10/07/2026",
            "jobUrl": "https://www.reed.co.uk/jobs/paid-media-manager/55512345",
            "minimumSalary": 40000,
            "maximumSalary": 48000,
        },
        {
            "jobId": 55567890,
            "employerName": "Bright Digital Agency",
            "jobTitle": "PPC Specialist",
            "locationName": "Leeds",
            "jobDescription": "Manage PPC campaigns across Google Ads and Microsoft Ads.",
            "date": "08/07/2026",
            "jobUrl": "https://www.reed.co.uk/jobs/ppc-specialist/55567890",
            "minimumSalary": 30000,
            "maximumSalary": 35000,
        },
        {
            # Missing employerName - should be skipped.
            "jobId": 55511111,
            "employerName": "",
            "jobTitle": "Junior Marketing Assistant",
            "locationName": "Bristol",
            "jobDescription": "",
            "date": "05/07/2026",
            "jobUrl": "https://www.reed.co.uk/jobs/junior-marketing/55511111",
        },
    ],
    "totalResults": 3,
}

EMPTY_RESPONSE = {"results": [], "totalResults": 0}

MALFORMED_DATE_RESPONSE = {
    "results": [
        {
            "jobId": 55599999,
            "employerName": "Test Co",
            "jobTitle": "Media Buyer",
            "locationName": "Birmingham",
            "jobDescription": "desc",
            "date": "not-a-date",
            "jobUrl": "https://www.reed.co.uk/jobs/media-buyer/55599999",
        }
    ],
    "totalResults": 1,
}
