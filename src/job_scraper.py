import json
import re
from typing import Any
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup, Tag
from requests import RequestException


class JobScraperError(RuntimeError):
    """Raised when a job posting cannot be scraped from a URL."""


JOB_RESULT_SCHEMA = {
    "company": "",
    "title": "",
    "location": "",
    "job_description": "",
    "url": "",
}

REQUEST_TIMEOUT_SECONDS = 15
MIN_DESCRIPTION_LENGTH = 80

UNSUPPORTED_PLATFORMS = {"linkedin", "indeed", "handshake"}

PLATFORM_DISPLAY_NAMES = {
    "greenhouse": "Greenhouse",
    "lever": "Lever",
    "ashby": "Ashby",
    "workable": "Workable",
    "workday": "Workday",
    "smartrecruiters": "SmartRecruiters",
    "jobvite": "Jobvite",
    "bamboohr": "BambooHR",
    "icims": "iCIMS",
    "generic": "this job board",
    "linkedin": "LinkedIn",
    "indeed": "Indeed",
    "handshake": "Handshake",
}

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/125.0 Safari/537.36"
)

NOISE_TAGS = {
    "aside",
    "button",
    "canvas",
    "footer",
    "form",
    "header",
    "iframe",
    "nav",
    "noscript",
    "script",
    "style",
    "svg",
}

NOISE_ATTRIBUTE_PATTERN = re.compile(
    r"(nav|navbar|header|footer|sidebar|cookie|banner|modal|popup|"
    r"subscribe|newsletter|social|share|related|recommend|search|filter)",
    re.IGNORECASE,
)

LOCATION_LABEL_PATTERN = re.compile(
    r"(?:^|\n)\s*(?:location|office|workplace|job location)\s*:?\s*([^\n]{2,100})",
    re.IGNORECASE,
)


def scrape_job(url: str) -> dict[str, str]:
    """Scrape a job posting URL and return structured posting fields."""
    normalized_url = normalize_url(url)
    platform = detect_platform(normalized_url)
    if platform in UNSUPPORTED_PLATFORMS:
        raise JobScraperError(unsupported_platform_message(platform))

    html = fetch_html(normalized_url)
    soup = BeautifulSoup(html, "html.parser")
    parser = PLATFORM_PARSERS.get(platform, parse_generic)
    return parser(soup, normalized_url)


def parse_greenhouse(soup: BeautifulSoup, url: str) -> dict[str, str]:
    return parse_structured_job(soup, url, "greenhouse")


def parse_lever(soup: BeautifulSoup, url: str) -> dict[str, str]:
    return parse_structured_job(soup, url, "lever")


def parse_ashby(soup: BeautifulSoup, url: str) -> dict[str, str]:
    return parse_structured_job(soup, url, "ashby")


def parse_workable(soup: BeautifulSoup, url: str) -> dict[str, str]:
    return parse_structured_job(soup, url, "workable")


def parse_workday(soup: BeautifulSoup, url: str) -> dict[str, str]:
    return parse_structured_job(soup, url, "workday", require_structured_or_container=True)


def parse_smartrecruiters(soup: BeautifulSoup, url: str) -> dict[str, str]:
    return parse_structured_job(soup, url, "smartrecruiters")


def parse_jobvite(soup: BeautifulSoup, url: str) -> dict[str, str]:
    return parse_structured_job(soup, url, "jobvite", require_structured_or_container=True)


def parse_bamboohr(soup: BeautifulSoup, url: str) -> dict[str, str]:
    return parse_structured_job(soup, url, "bamboohr")


def parse_icims(soup: BeautifulSoup, url: str) -> dict[str, str]:
    return parse_structured_job(soup, url, "icims", require_structured_or_container=True)


def parse_generic(soup: BeautifulSoup, url: str) -> dict[str, str]:
    return parse_structured_job(soup, url, "generic")


PLATFORM_PARSERS = {
    "greenhouse": parse_greenhouse,
    "lever": parse_lever,
    "ashby": parse_ashby,
    "workable": parse_workable,
    "workday": parse_workday,
    "smartrecruiters": parse_smartrecruiters,
    "jobvite": parse_jobvite,
    "bamboohr": parse_bamboohr,
    "icims": parse_icims,
    "generic": parse_generic,
}


def parse_structured_job(
    soup: BeautifulSoup,
    url: str,
    platform: str,
    require_structured_or_container: bool = False,
) -> dict[str, str]:
    metadata = extract_metadata(soup, url)
    clean_soup = remove_irrelevant_content(soup)

    platform_description = extract_job_description(clean_soup, platform, include_generic=False)
    generic_description = "" if platform_description else extract_job_description(clean_soup, platform)
    description = metadata.get("description", "") or platform_description or generic_description
    if len(description) < MIN_DESCRIPTION_LENGTH:
        raise manual_paste_error(platform)

    if require_structured_or_container and not (platform_description or metadata.get("description")):
        raise manual_paste_error(platform)

    title = first_non_empty(
        metadata.get("title"),
        extract_platform_title(clean_soup, platform),
        infer_title_from_page(clean_soup),
    )
    company = first_non_empty(
        metadata.get("company"),
        extract_platform_company(clean_soup, platform),
        infer_company_from_title_tag(clean_soup, title),
        infer_company_from_domain(url),
    )
    location = first_non_empty(
        metadata.get("location"),
        extract_platform_location(clean_soup, platform),
        infer_location_from_text(description),
    )

    return {
        "company": clean_inline_text(company),
        "title": clean_inline_text(title),
        "location": clean_inline_text(location),
        "job_description": description,
        "url": url,
    }


def normalize_url(url: str) -> str:
    cleaned_url = clean_inline_text(url)
    if not cleaned_url:
        raise JobScraperError("Please provide a job URL.")

    parsed = urlparse(cleaned_url)
    if not parsed.scheme:
        cleaned_url = f"https://{cleaned_url}"
        parsed = urlparse(cleaned_url)

    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise JobScraperError("Please provide a valid http or https job URL.")

    return cleaned_url


def fetch_html(url: str) -> str:
    try:
        response = requests.get(
            url,
            headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml"},
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
    except RequestException as exc:
        raise JobScraperError(f"Could not fetch the job page: {exc}") from exc

    content_type = response.headers.get("content-type", "")
    if "html" not in content_type.lower() and response.text.lstrip()[:1] != "<":
        raise JobScraperError("The URL did not return an HTML page.")

    return response.text


def manual_paste_error(platform: str) -> JobScraperError:
    platform_name = PLATFORM_DISPLAY_NAMES.get(platform, platform)
    return JobScraperError(
        f"Could not reliably scrape this {platform_name} job page. "
        "Please paste the job description manually."
    )


def unsupported_platform_message(platform: str) -> str:
    platform_name = PLATFORM_DISPLAY_NAMES.get(platform, platform)
    return (
        f"{platform_name} scraping is not supported yet and may require authenticated "
        "or browser-based ingestion later. Please paste the job description manually."
    )


def detect_platform(url: str) -> str:
    host = urlparse(url).netloc.lower()
    path = urlparse(url).path.lower()

    # TODO: LinkedIn may require authenticated or browser-based ingestion later.
    if "linkedin.com" in host:
        return "linkedin"

    # TODO: Indeed may require authenticated or browser-based ingestion later.
    if "indeed.com" in host:
        return "indeed"

    # TODO: Handshake may require authenticated or browser-based ingestion later.
    if "joinhandshake.com" in host or "handshake.com" in host:
        return "handshake"

    if "greenhouse.io" in host or "greenhouse" in path:
        return "greenhouse"
    if "lever.co" in host or "jobs.lever.co" in host:
        return "lever"
    if "ashbyhq.com" in host or "jobs.ashbyhq.com" in host or "ashby" in path:
        return "ashby"
    if "workable.com" in host or "workable" in path:
        return "workable"
    if "myworkdayjobs.com" in host or "workdayjobs.com" in host or "workday" in host:
        return "workday"
    if "smartrecruiters.com" in host:
        return "smartrecruiters"
    if "jobvite.com" in host:
        return "jobvite"
    if "bamboohr.com" in host:
        return "bamboohr"
    if "icims.com" in host or "icims" in host:
        return "icims"

    return "generic"


def remove_irrelevant_content(soup: BeautifulSoup) -> BeautifulSoup:
    clean_soup = BeautifulSoup(str(soup), "html.parser")

    for tag in clean_soup.find_all(NOISE_TAGS):
        tag.decompose()

    for tag in clean_soup.find_all(True):
        if not isinstance(tag, Tag):
            continue

        attributes = " ".join(
            str(value)
            for key in ("id", "class", "role", "aria-label")
            for value in ([tag.get(key)] if not isinstance(tag.get(key), list) else tag.get(key))
            if value
        )
        if attributes and NOISE_ATTRIBUTE_PATTERN.search(attributes):
            tag.decompose()

    return clean_soup


def extract_job_description(soup: BeautifulSoup, platform: str, include_generic: bool = True) -> str:
    selectors = platform_description_selectors(platform)
    if include_generic:
        selectors += [
            "main",
            "article",
            "[role='main']",
            ".job-description",
            ".description",
            ".content",
            "body",
        ]

    candidates: list[str] = []
    for selector in selectors:
        for element in soup.select(selector):
            text = clean_multiline_text(element.get_text("\n", strip=True))
            if len(text) >= MIN_DESCRIPTION_LENGTH:
                candidates.append(text)

    if not candidates:
        return ""

    return max(candidates, key=len)


def platform_description_selectors(platform: str) -> list[str]:
    if platform == "greenhouse":
        return [
            "#content",
            "#app_body",
            ".opening",
            ".job-post",
            ".job__description",
            "[data-qa='job-description']",
        ]

    if platform == "lever":
        return [
            ".posting-page",
            ".posting",
            ".posting-description",
            ".section-wrapper",
            ".content-wrapper",
        ]

    if platform == "ashby":
        return [
            "[data-testid='job-posting']",
            "[data-testid='job-description']",
            ".ashby-job-posting",
            ".ashby-job-posting-content",
            ".job-posting",
        ]

    if platform == "workable":
        return [
            "[data-ui='job-description']",
            "[data-testid='job-description']",
            ".job-preview",
            ".job-description",
            ".section--text",
            "main",
        ]

    if platform == "workday":
        return [
            "[data-automation-id='jobPostingDescription']",
            "[data-automation-id='jobPostingPage']",
            "[data-automation-id='job-posting-details']",
            ".jobPostingDescription",
            "main",
        ]

    if platform == "smartrecruiters":
        return [
            "[itemprop='description']",
            ".job-description",
            ".description",
            ".job-sections",
            "section.job-description",
        ]

    if platform == "jobvite":
        return [
            ".jv-job-detail-description",
            ".jv-job-detail",
            "#jv-job-detail",
            ".job-description",
            "[itemprop='description']",
        ]

    if platform == "bamboohr":
        return [
            "#jobDescription",
            ".BambooHR-ATS-Job-Description",
            ".jobDescription",
            ".ResAts__description",
            "[itemprop='description']",
        ]

    if platform == "icims":
        return [
            ".iCIMS_JobContent",
            ".iCIMS_JobHeaderGroup",
            ".iCIMS_InfoMsg",
            "[data-testid='job-description']",
            "[itemprop='description']",
        ]

    return []


def extract_metadata(soup: BeautifulSoup, url: str) -> dict[str, str]:
    metadata = extract_json_ld_job_posting(soup)
    embedded_metadata = extract_embedded_job_metadata(soup)
    metadata = merge_metadata(metadata, embedded_metadata)

    title = first_non_empty(
        metadata.get("title"),
        get_meta_content(soup, "property", "og:title"),
        get_meta_content(soup, "name", "twitter:title"),
    )
    description = first_non_empty(
        metadata.get("description"),
        get_meta_content(soup, "name", "description"),
        get_meta_content(soup, "property", "og:description"),
    )

    if description and not metadata.get("location"):
        metadata["location"] = infer_location_from_text(description)

    if title and not metadata.get("title"):
        parsed_title, parsed_company = split_title_company(title)
        metadata["title"] = parsed_title
        metadata["company"] = first_non_empty(metadata.get("company"), parsed_company)

    if not metadata.get("company"):
        metadata["company"] = infer_company_from_domain(url)

    return metadata


def merge_metadata(primary: dict[str, str], secondary: dict[str, str]) -> dict[str, str]:
    merged = dict(primary)
    for key, value in secondary.items():
        if not merged.get(key) and value:
            merged[key] = value

    return merged


def extract_json_ld_job_posting(soup: BeautifulSoup) -> dict[str, str]:
    for script in soup.find_all("script", {"type": "application/ld+json"}):
        content = script.string or script.get_text(strip=True)
        if not content:
            continue

        for item in flatten_json_ld(load_json_safely(content)):
            if not is_job_posting(item):
                continue

            return {
                "company": extract_hiring_organization(item),
                "title": clean_inline_text(item.get("title")),
                "location": extract_job_location(item),
                "description": clean_multiline_text(BeautifulSoup(str(item.get("description", "")), "html.parser").get_text("\n")),
            }

    return {}


def extract_embedded_job_metadata(soup: BeautifulSoup) -> dict[str, str]:
    candidates: list[dict[str, str]] = []
    for script in soup.find_all("script"):
        script_type = clean_inline_text(script.get("type")).lower()
        script_id = clean_inline_text(script.get("id")).lower()
        if script_type and "json" not in script_type and script_id != "__next_data__":
            continue

        content = script.string or script.get_text(strip=True)
        if not content or "description" not in content.lower():
            continue

        value = load_json_safely(content)
        if value is None:
            continue

        for item in flatten_dicts(value):
            candidate = metadata_from_dict(item)
            if candidate.get("description"):
                candidates.append(candidate)

    if not candidates:
        return {}

    return max(candidates, key=lambda candidate: len(candidate.get("description", "")))


def flatten_dicts(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, dict):
        items = [value]
        for nested_value in value.values():
            items.extend(flatten_dicts(nested_value))
        return items

    if isinstance(value, list):
        items = []
        for item in value:
            items.extend(flatten_dicts(item))
        return items

    return []


def metadata_from_dict(item: dict[str, Any]) -> dict[str, str]:
    raw_description = first_value_for_keys(item, ["description", "jobDescription", "job_description", "body"])
    description = clean_multiline_text(BeautifulSoup(str(raw_description), "html.parser").get_text("\n"))
    if len(description) < MIN_DESCRIPTION_LENGTH:
        return {}

    return {
        "company": clean_inline_text(
            first_value_for_keys(item, ["company", "companyName", "organization", "department"])
        ),
        "title": clean_inline_text(first_value_for_keys(item, ["title", "jobTitle", "job_title", "name"])),
        "location": clean_inline_text(first_value_for_keys(item, ["location", "jobLocation", "locations"])),
        "description": description,
    }


def first_value_for_keys(item: dict[str, Any], keys: list[str]) -> Any:
    for key in keys:
        value = item.get(key)
        if isinstance(value, str):
            return value
        if isinstance(value, dict):
            parsed_value = first_value_for_keys(value, ["name", "label", "title"])
            if parsed_value:
                return parsed_value
        if isinstance(value, list):
            parsed_values = [clean_inline_text(first_value_from_list_item(list_item)) for list_item in value]
            parsed_values = [parsed_value for parsed_value in parsed_values if parsed_value]
            if parsed_values:
                return ", ".join(parsed_values)

    return ""


def first_value_from_list_item(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        return first_value_for_keys(value, ["name", "label", "title", "city", "location"])
    return ""


def load_json_safely(content: str) -> Any:
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        return None


def flatten_json_ld(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, dict):
        items = []
        if "@graph" in value:
            items.extend(flatten_json_ld(value["@graph"]))
        items.append(value)
        return items

    if isinstance(value, list):
        items = []
        for item in value:
            items.extend(flatten_json_ld(item))
        return items

    return []


def is_job_posting(item: dict[str, Any]) -> bool:
    item_type = item.get("@type")
    if isinstance(item_type, list):
        return any(str(value).lower() == "jobposting" for value in item_type)

    return str(item_type).lower() == "jobposting"


def extract_hiring_organization(item: dict[str, Any]) -> str:
    organization = item.get("hiringOrganization")
    if isinstance(organization, dict):
        return clean_inline_text(organization.get("name"))

    return clean_inline_text(organization)


def extract_job_location(item: dict[str, Any]) -> str:
    locations = item.get("jobLocation") or item.get("applicantLocationRequirements")
    if not locations:
        return ""

    location_items = locations if isinstance(locations, list) else [locations]
    parsed_locations = [parse_location(location) for location in location_items]
    return ", ".join(location for location in parsed_locations if location)


def parse_location(location: Any) -> str:
    if isinstance(location, str):
        return clean_inline_text(location)

    if not isinstance(location, dict):
        return ""

    address = location.get("address", location)
    if isinstance(address, str):
        return clean_inline_text(address)

    if not isinstance(address, dict):
        return ""

    parts = [
        address.get("addressLocality"),
        address.get("addressRegion"),
        address.get("addressCountry"),
    ]
    return clean_inline_text(", ".join(str(part) for part in parts if part))


def get_meta_content(soup: BeautifulSoup, attribute: str, value: str) -> str:
    tag = soup.find("meta", attrs={attribute: value})
    if not tag:
        return ""

    return clean_inline_text(tag.get("content"))


def extract_platform_title(soup: BeautifulSoup, platform: str) -> str:
    selectors = {
        "greenhouse": ["h1", ".app-title", "[data-qa='job-title']"],
        "lever": [".posting-headline h2", "h2", "h1"],
        "ashby": ["[data-testid='posting-title']", "h1"],
        "workable": ["[data-ui='job-title']", "[data-testid='job-title']", "h1"],
        "workday": ["[data-automation-id='jobPostingHeader'] h1", "[data-automation-id='jobPostingHeader']", "h1"],
        "smartrecruiters": ["[itemprop='title']", ".job-title", "h1"],
        "jobvite": [".jv-job-detail-title", ".jv-header h2", "h1"],
        "bamboohr": [".BambooHR-ATS-Job-Title", ".ResAts__title", "h1"],
        "icims": [".iCIMS_JobHeaderGroup h1", ".iCIMS_Header", "h1"],
        "generic": ["h1"],
    }
    return text_from_first_selector(soup, selectors.get(platform, selectors["generic"]))


def extract_platform_company(soup: BeautifulSoup, platform: str) -> str:
    selectors = {
        "greenhouse": [".company-name", ".app-title .company", "[data-qa='company-name']"],
        "lever": [".main-header-logo img", ".posting-company", ".company-name"],
        "ashby": ["[data-testid='company-name']", ".company-name"],
        "workable": ["[data-ui='company-name']", "[data-testid='company-name']", ".company-name"],
        "workday": ["[data-automation-id='company']", "[data-automation-id='jobPostingCompany']", ".company"],
        "smartrecruiters": [".company-name", "[itemprop='hiringOrganization']", ".job-company"],
        "jobvite": [".jv-company-name", ".jv-header img", ".company-name"],
        "bamboohr": [".BambooHR-ATS-board-title", ".company-name", "[itemprop='hiringOrganization']"],
        "icims": [".iCIMS_CompanyName", "[itemprop='hiringOrganization']", ".company-name"],
        "generic": [".company-name", "[data-company]", "[itemprop='hiringOrganization']"],
    }

    for selector in selectors.get(platform, selectors["generic"]):
        element = soup.select_one(selector)
        if not element:
            continue

        if element.name == "img":
            text = clean_inline_text(element.get("alt"))
        else:
            text = clean_inline_text(element.get_text(" ", strip=True))
        if text:
            return text

    return ""


def extract_platform_location(soup: BeautifulSoup, platform: str) -> str:
    selectors = {
        "greenhouse": [".location", "[data-qa='job-location']", ".job-location"],
        "lever": [".posting-categories .location", ".posting-location", ".location"],
        "ashby": ["[data-testid='job-location']", ".job-location", ".location"],
        "workable": ["[data-ui='job-location']", "[data-testid='job-location']", ".job-location", ".location"],
        "workday": ["[data-automation-id='locations']", "[data-automation-id='jobPostingLocation']", ".job-location"],
        "smartrecruiters": ["[itemprop='jobLocation']", ".job-location", ".location"],
        "jobvite": [".jv-job-detail-meta", ".jv-job-detail-location", ".location"],
        "bamboohr": [".BambooHR-ATS-Location", ".ResAts__location", ".location"],
        "icims": [".iCIMS_JobHeaderGroup .iCIMS_InfoMsg", "[itemprop='jobLocation']", ".location"],
        "generic": [".job-location", ".location", "[itemprop='jobLocation']"],
    }
    return text_from_first_selector(soup, selectors.get(platform, selectors["generic"]))


def infer_title_from_page(soup: BeautifulSoup) -> str:
    h1 = soup.find("h1")
    if h1:
        return clean_inline_text(h1.get_text(" ", strip=True))

    if soup.title and soup.title.string:
        return split_title_company(soup.title.string)[0]

    return ""


def infer_company_from_title_tag(soup: BeautifulSoup, title: str) -> str:
    if not soup.title or not soup.title.string:
        return ""

    page_title = clean_inline_text(soup.title.string)
    parsed_title, parsed_company = split_title_company(page_title)
    if parsed_company and (not title or parsed_title.lower() == title.lower()):
        return parsed_company

    return parsed_company


def infer_company_from_domain(url: str) -> str:
    host = urlparse(url).netloc.lower()
    host = host.removeprefix("www.").removeprefix("jobs.").removeprefix("careers.")

    parts = host.split(".")
    if not parts:
        return ""

    company = parts[0]
    if company in {"boards", "job-boards", "jobs", "careers"} and len(parts) > 1:
        company = parts[1]

    return clean_inline_text(company.replace("-", " ").replace("_", " ").title())


def infer_location_from_text(text: str) -> str:
    match = LOCATION_LABEL_PATTERN.search(text)
    if not match:
        return ""

    location = match.group(1)
    location = re.split(r"\s{2,}|[|•]", location, maxsplit=1)[0]
    return clean_inline_text(location)


def split_title_company(value: str) -> tuple[str, str]:
    text = clean_inline_text(value)
    if not text:
        return "", ""

    separators = [" at ", " @ ", " - ", " | ", " – ", " — "]
    for separator in separators:
        if separator in text:
            left, right = text.split(separator, 1)
            left = clean_inline_text(left)
            right = clean_inline_text(right)
            if separator.strip() in {"at", "@"}:
                return left, right
            return left, right

    return text, ""


def text_from_first_selector(soup: BeautifulSoup, selectors: list[str]) -> str:
    for selector in selectors:
        element = soup.select_one(selector)
        if element:
            return clean_inline_text(element.get_text(" ", strip=True))

    return ""


def clean_inline_text(value: Any) -> str:
    if value is None:
        return ""

    return " ".join(str(value).replace("\r\n", "\n").replace("\r", "\n").split()).strip()


def clean_multiline_text(value: Any) -> str:
    if value is None:
        return ""

    lines = [clean_inline_text(line) for line in str(value).replace("\r\n", "\n").replace("\r", "\n").split("\n")]
    cleaned_lines = []
    previous_line = ""
    for line in lines:
        if not line or line == previous_line:
            continue

        cleaned_lines.append(line)
        previous_line = line

    return "\n".join(cleaned_lines).strip()


def first_non_empty(*values: Any) -> str:
    for value in values:
        cleaned_value = clean_inline_text(value)
        if cleaned_value:
            return cleaned_value

    return ""
